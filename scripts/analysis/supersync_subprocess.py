"""
超同步转移 — 子进程隔离方案
每个步骤在独立 Python 进程中初始化 GMAT，避免沙盒状态冲突。
"""
import subprocess, json, math, os, sys, tempfile

MU = 398600.4418
R_EARTH = 6378.1363
R_GEO = 42165.0
R_LEO = R_EARTH + 400.0
INC_INIT = 46.0
R_A = 200000.0

GMAT_ROOT = r"e:\GMAT\gmat-win-R2026a"
OUTPUT = os.path.join(GMAT_ROOT, "output")

def gmat_step(script_file, object_names):
    """在新进程中运行 GMAT 脚本，读取对象状态返回 JSON"""
    runner = os.path.join(os.path.dirname(__file__), "..", "runner", "python_runner.py")
    cmd = [
        sys.executable, runner,
        "--gmat-root", GMAT_ROOT,
        "--script", script_file,
        "--objects", ",".join(object_names),
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=300,
                          cwd=os.path.dirname(runner))
    stdout = proc.stdout.decode("utf-8", errors="replace")
    try:
        return json.loads(stdout)
    except:
        print(f"  Raw output: {stdout[:500]}")
        print(f"  Stderr: {proc.stderr.decode('utf-8', errors='replace')[:300]}")
        raise

def write_script(path, content):
    with open(path, "w", encoding="ascii") as f:
        f.write(content)

# ====== 分析计算 TOI ======
a_trans = (R_LEO + R_A) / 2.0
v_leo = math.sqrt(MU / R_LEO)
v_peri_toi = math.sqrt(2*MU/R_LEO - MU/a_trans)
dv_toi = v_peri_toi - v_leo
print(f"TOI DV (VNB Element1): {dv_toi:.4f} km/s")

# ====== Step 1: TOI → 远地点 ======
print("\n=== Step 1: TOI → Apoapsis ===")
s1_path = os.path.join(OUTPUT, "s1_toi.script")
write_script(s1_path, f"""Create Spacecraft Sat;
Sat.DateFormat = UTCGregorian;
Sat.Epoch = '01 Jun 2026 00:00:00.000';
Sat.CoordinateSystem = EarthMJ2000Eq;
Sat.DisplayStateType = Keplerian;
Sat.SMA = {R_LEO:.6f};
Sat.ECC = 0.0001;
Sat.INC = {INC_INIT};
Sat.RAAN = 0;
Sat.AOP = 0;
Sat.TA = 0;

Create ForceModel FM;
FM.CentralBody = Earth;

Create Propagator Prop;
Prop.FM = FM;
Prop.Type = PrinceDormand78;
Prop.InitialStepSize = 60;
Prop.Accuracy = 1.0e-11;

Create ImpulsiveBurn TOI;
TOI.CoordinateSystem = Local;
TOI.Origin = Earth;
TOI.Axes = VNB;
TOI.Element1 = {dv_toi:.10f};
TOI.Element2 = 0.0;
TOI.Element3 = 0.0;
TOI.DecrementMass = false;

BeginMissionSequence;
Maneuver TOI(Sat);
Propagate Prop(Sat) {{Sat.Earth.Apoapsis}};
""")

result1 = gmat_step(s1_path, ["Sat"])
if not result1.get("success"):
    print(f"Step 1 FAILED: {result1}")
    sys.exit(1)

s1 = result1["objects"]["Sat"]
print(f"  SMA={s1['SMA']:.1f}, ECC={s1['ECC']:.4f}, INC={s1['INC']:.2f}")
print(f"  Perigee={s1['SMA']*(1-s1['ECC'])-R_EARTH:.0f} km, Apogee={s1['SMA']*(1+s1['ECC'])-R_EARTH:.0f} km")
print(f"  X={s1['X']:.1f}, Y={s1['Y']:.1f}, Z={s1['Z']:.1f}")
print(f"  VX={s1['VX']:.4f}, VY={s1['VY']:.4f}, VZ={s1['VZ']:.4f}")

# ====== 从 GMAT 实态计算 GOI EarthMJ2000Eq ΔV ======
print("\n=== Computing GOI Delta-V in EarthMJ2000Eq ===")
rx, ry, rz = s1["X"], s1["Y"], s1["Z"]
vx, vy, vz = s1["VX"], s1["VY"], s1["VZ"]
rmag = math.sqrt(rx**2 + ry**2 + rz**2)
r_xy = math.sqrt(rx**2 + ry**2)
vmag = math.sqrt(vx**2 + vy**2 + vz**2)

# 目标: 赤道面内圆轨道, 速度⊥位置, |v| 对应 GEO 转移
a_geo_trans = (R_GEO + rmag) / 2.0
v_target_mag = math.sqrt(2*MU/rmag - MU/a_geo_trans)

# 赤道面内, 垂直位置矢量 (逆时针方向)
vtx = v_target_mag * (-ry / r_xy)
vty = v_target_mag * (rx / r_xy)
vtz = 0.0

dv_x = vtx - vx
dv_y = vty - vy
dv_z = vtz - vz
dv_mag = math.sqrt(dv_x**2 + dv_y**2 + dv_z**2)

print(f"  r=({rx:.1f}, {ry:.1f}, {rz:.1f}), |r|={rmag:.1f}")
print(f"  v=({vx:.4f}, {vy:.4f}, {vz:.4f}), |v|={vmag:.4f}")
print(f"  v_target=({vtx:.4f}, {vty:.4f}, {vtz:.4f}), |vt|={v_target_mag:.4f}")
print(f"  DV_GOI=({dv_x:.4f}, {dv_y:.4f}, {dv_z:.4f}), |DV|={dv_mag:.4f} km/s")

# ====== Step 2: TOI + GOI → 近地点 ======
print("\n=== Step 2: TOI + GOI → Periapsis ===")
s2_path = os.path.join(OUTPUT, "s2_goi.script")
write_script(s2_path, f"""Create Spacecraft Sat;
Sat.DateFormat = UTCGregorian;
Sat.Epoch = '01 Jun 2026 00:00:00.000';
Sat.CoordinateSystem = EarthMJ2000Eq;
Sat.DisplayStateType = Keplerian;
Sat.SMA = {R_LEO:.6f};
Sat.ECC = 0.0001;
Sat.INC = {INC_INIT};
Sat.RAAN = 0;
Sat.AOP = 0;
Sat.TA = 0;

Create ForceModel FM;
FM.CentralBody = Earth;

Create Propagator Prop;
Prop.FM = FM;
Prop.Type = PrinceDormand78;
Prop.InitialStepSize = 60;
Prop.Accuracy = 1.0e-11;

Create ImpulsiveBurn TOI;
TOI.CoordinateSystem = Local;
TOI.Origin = Earth;
TOI.Axes = VNB;
TOI.Element1 = {dv_toi:.10f};
TOI.Element2 = 0.0;
TOI.Element3 = 0.0;
TOI.DecrementMass = false;

Create ImpulsiveBurn GOI;
GOI.CoordinateSystem = EarthMJ2000Eq;
GOI.Origin = Earth;
GOI.Axes = MJ2000Eq;
GOI.Element1 = {dv_x:.10f};
GOI.Element2 = {dv_y:.10f};
GOI.Element3 = {dv_z:.10f};
GOI.DecrementMass = false;

BeginMissionSequence;
Maneuver TOI(Sat);
Propagate Prop(Sat) {{Sat.Earth.Apoapsis}};
Maneuver GOI(Sat);
Propagate Prop(Sat) {{Sat.Earth.Periapsis}};
""")

result2 = gmat_step(s2_path, ["Sat"])
if not result2.get("success"):
    print(f"Step 2 FAILED: {result2}")
    # 提取错误
    if result2.get("details"):
        for d in result2["details"][:5]:
            print(f"  Line {d.get('line','?')}: {d.get('message','?')}")
    print(f"  Error: {result2.get('error','?')}")
    sys.exit(1)

s2 = result2["objects"]["Sat"]
print(f"  SMA={s2['SMA']:.1f}, ECC={s2['ECC']:.4f}, INC={s2['INC']:.2f}")
print(f"  Perigee={s2['SMA']*(1-s2['ECC'])-R_EARTH:.0f} km, Apogee={s2['SMA']*(1+s2['ECC'])-R_EARTH:.0f} km")

# ====== 计算 Circ ΔV ======
print("\n=== Computing Circ Delta-V ===")
v_peri = math.sqrt(s2["VX"]**2 + s2["VY"]**2 + s2["VZ"]**2)
v_geo_target = math.sqrt(MU / R_GEO)
dv_circ = v_geo_target - v_peri
print(f"  |v|={v_peri:.4f}, target={v_geo_target:.4f}, DV_Circ={dv_circ:.4f} km/s")

# ====== Step 3: 完整执行 TOI + GOI + Circ ======
print("\n=== Step 3: Full TOI + GOI + Circ ===")
s3_path = os.path.join(OUTPUT, "s3_circ.script")
write_script(s3_path, f"""Create Spacecraft Sat;
Sat.DateFormat = UTCGregorian;
Sat.Epoch = '01 Jun 2026 00:00:00.000';
Sat.CoordinateSystem = EarthMJ2000Eq;
Sat.DisplayStateType = Keplerian;
Sat.SMA = {R_LEO:.6f};
Sat.ECC = 0.0001;
Sat.INC = {INC_INIT};
Sat.RAAN = 0;
Sat.AOP = 0;
Sat.TA = 0;

Create ForceModel FM;
FM.CentralBody = Earth;

Create Propagator Prop;
Prop.FM = FM;
Prop.Type = PrinceDormand78;
Prop.InitialStepSize = 60;
Prop.Accuracy = 1.0e-11;

Create ImpulsiveBurn TOI;
TOI.CoordinateSystem = Local;
TOI.Origin = Earth;
TOI.Axes = VNB;
TOI.Element1 = {dv_toi:.10f};
TOI.Element2 = 0.0;
TOI.Element3 = 0.0;
TOI.DecrementMass = false;

Create ImpulsiveBurn GOI;
GOI.CoordinateSystem = EarthMJ2000Eq;
GOI.Origin = Earth;
GOI.Axes = MJ2000Eq;
GOI.Element1 = {dv_x:.10f};
GOI.Element2 = {dv_y:.10f};
GOI.Element3 = {dv_z:.10f};
GOI.DecrementMass = false;

Create ImpulsiveBurn Circ;
Circ.CoordinateSystem = Local;
Circ.Origin = Earth;
Circ.Axes = VNB;
Circ.Element1 = {dv_circ:.10f};
Circ.Element2 = 0.0;
Circ.Element3 = 0.0;
Circ.DecrementMass = false;

BeginMissionSequence;
Maneuver TOI(Sat);
Propagate Prop(Sat) {{Sat.Earth.Apoapsis}};
Maneuver GOI(Sat);
Propagate Prop(Sat) {{Sat.Earth.Periapsis}};
Maneuver Circ(Sat);
Propagate Prop(Sat) {{Sat.ElapsedDays = 1.0}};
""")

result3 = gmat_step(s3_path, ["Sat"])
if not result3.get("success"):
    print(f"Step 3 FAILED: {result3}")
    sys.exit(1)

s3 = result3["objects"]["Sat"]
sma = s3["SMA"]
ecc = s3["ECC"]
inc = s3["INC"]
print(f"  SMA={sma:.2f} (alt={sma-R_EARTH:.2f})")
print(f"  ECC={ecc:.6f}")
print(f"  INC={inc:.4f} deg")
print(f"  RMAG={s3['RMAG']:.2f}")
print(f"  Perigee={sma*(1-ecc)-R_EARTH:.2f} km")
print(f"  Apogee={sma*(1+ecc)-R_EARTH:.2f} km")

# ====== Summary ======
total_dv = dv_toi + dv_mag + abs(dv_circ)
print(f"\n{'='*50}")
print(f"SUMMARY")
print(f"{'='*50}")
print(f"TOI (VNB):     {dv_toi:.4f} km/s")
print(f"GOI (MJ2000Eq): {dv_mag:.4f} km/s")
print(f"Circ (VNB):    {abs(dv_circ):.4f} km/s")
print(f"Total:         {total_dv:.4f} km/s")
print(f"SMA-Re:        {sma-R_EARTH:.1f} km  (target: {R_GEO-R_EARTH:.0f})")
print(f"SMA error:     {sma-R_GEO:.1f} km")
print(f"ECC:           {ecc:.6f}")
print(f"INC:           {inc:.4f} deg")

if abs(sma - R_GEO) < 100 and ecc < 0.01 and abs(inc) < 1.0:
    print("\n*** SUCCESS: 卫星成功进入 GEO! ***")
else:
    issues = []
    if abs(sma - R_GEO) >= 100: issues.append(f"SMA偏差 {sma-R_GEO:.0f}km")
    if ecc >= 0.01: issues.append(f"ECC={ecc:.4f}")
    if abs(inc) >= 1.0: issues.append(f"INC={inc:.2f}deg")
    print(f"\n待优化: {', '.join(issues)}")
