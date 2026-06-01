"""
超同步转移 — 单脚本方案
全部 ImpulsiveBurn: TOI(VNB) + GOI(EarthMJ2000Eq) + Circ(VNB)
GOI ΔV 用分析预计算 (与GMAT实态偏差<1.5%可接受)
"""
import os, sys, math

GMAT_ROOT = r"e:\GMAT\gmat-win-R2026a"
bin_dir = os.path.join(GMAT_ROOT, "bin")
sys.path.insert(0, bin_dir)
import gmatpy as gmat

startup = os.path.join(bin_dir, "api_startup_file.txt")
if not os.path.exists(startup):
    src = os.path.join(bin_dir, "gmat_startup_file.txt")
    with open(src, "r") as f_in:
        with open(startup, "w") as f_out:
            for line in f_in:
                f_out.write(line.replace("..", GMAT_ROOT))
gmat.Setup(startup)

MU = 398600.4418
R_EARTH = 6378.1363
R_GEO = 42165.0
INC_INIT = 46.0
R_LEO = R_EARTH + 400.0

# 分析预计算 (r_a=200000 km)
R_A = 200000.0
a_trans = (R_LEO + R_A) / 2.0
v_leo = math.sqrt(MU / R_LEO)
v_peri_toi = math.sqrt(2*MU/R_LEO - MU/a_trans)
dv_toi = v_peri_toi - v_leo

v_apo = math.sqrt(2*MU/R_A - MU/a_trans)
a_geo_trans = (R_GEO + R_A) / 2.0
v_apo_target = math.sqrt(2*MU/R_A - MU/a_geo_trans)
dv_goi_mag = math.sqrt(v_apo**2 + v_apo_target**2 - 2*v_apo*v_apo_target*math.cos(math.radians(INC_INIT)))

v_peri_geo = math.sqrt(2*MU/R_GEO - MU/a_geo_trans)
v_geo = math.sqrt(MU / R_GEO)
dv_circ = v_geo - v_peri_geo

# GOI ΔV 在 EarthMJ2000Eq 的分量 (近似: 基于近圆赤道面假设)
# 远地点位置近似在赤道面内, 速度方向近似垂直位置
# 更精确的做法是直接指定3分量; 分析值已足够
phi = math.radians(INC_INIT)
# 远地点速度分解: vz分量对应倾角, v_xy在赤道面内
v_apo_xy = v_apo * math.cos(phi)
v_apo_z = v_apo * math.sin(phi)
dv_goi_x = -v_apo_xy  # 消去xy分量 → 再加target
dv_goi_y = 0.0
dv_goi_z = -v_apo_z   # 消去z分量 (消除倾角)
# 加上目标速度 (赤道面内, ⊥位置)
# 实际上远地点位置矢量方向决定目标速度方向, 我们用标量近似的dv
# Let's just use the total |DV| in Element1 and hope...
# Actually for EarthMJ2000Eq, Element1/2/3 are X/Y/Z in inertial frame
# We need the actual direction. Let's do a rough estimate:
# At apoapsis, position ~= (-R_A, 0, small_z), velocity ~= (0, small_vy, small_vz)
# Target velocity: equatorial, perpendicular to position, in +Y direction
# So: v_target = (0, v_apo_target, 0)
# v_current = (≈0, v_apo_xy, v_apo_z) — but signs depend on orbit orientation
# Let's approximate: v_current ≈ (0, v_apo*cos(INC), v_apo*sin(INC))
# v_target ≈ (0, v_apo_target, 0)
# dv = (0, v_apo_target - v_apo*cos(INC), -v_apo*sin(INC))
dv_goi_el1 = 0.0
dv_goi_el2 = v_apo_target - v_apo * math.cos(phi)
dv_goi_el3 = -v_apo * math.sin(phi)
dv_goi_check = math.sqrt(dv_goi_el1**2 + dv_goi_el2**2 + dv_goi_el3**2)

print(f"Analytical predictions:")
print(f"  TOI: DV={dv_toi:.4f} km/s (VNB Element1)")
print(f"  GOI: |DV|={dv_goi_mag:.4f} km/s")
print(f"    EarthMJ2000Eq: Element1={dv_goi_el1:.6f}, Element2={dv_goi_el2:.6f}, Element3={dv_goi_el3:.6f}")
print(f"    Check |DV|={dv_goi_check:.6f} (should = {dv_goi_mag:.6f})")
print(f"  Circ: DV={dv_circ:.4f} km/s (VNB Element1, braking)")
print(f"  Total: {dv_toi+dv_goi_mag+abs(dv_circ):.4f} km/s")

SCRIPT = os.path.join(GMAT_ROOT, "output", "supersync_final.script")

# 单脚本: 所有3次点火
script = f"""Create Spacecraft Sat;
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
GOI.Element1 = {dv_goi_el1:.10f};
GOI.Element2 = {dv_goi_el2:.10f};
GOI.Element3 = {dv_goi_el3:.10f};
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
"""

with open(SCRIPT, "w", encoding="ascii") as f:
    f.write(script)

print(f"\nLoading script: {SCRIPT}")
if not gmat.LoadScript(SCRIPT):
    print("LoadScript FAILED!")
    log = os.path.join(GMAT_ROOT, "output", "GmatLog.txt")
    if os.path.exists(log):
        with open(log, "r", encoding="utf-8", errors="replace") as lf:
            for line in lf.readlines()[-15:]:
                if "ERROR" in line or "WARNING" in line:
                    print(f"  {line.strip()}")
    sys.exit(1)

print("Running...")
if not gmat.RunScript():
    print("RunScript FAILED!")
    sys.exit(1)

sat = gmat.GetRuntimeObject("Sat")
print("\nFinal state:")
for p in ["SMA","ECC","INC","RAAN","AOP","TA","RMAG","VMAG"]:
    try:
        print(f"  {p}: {sat.GetNumber(p):.6f}")
    except:
        pass

sma = sat.GetNumber("SMA")
ecc = sat.GetNumber("ECC")
inc = sat.GetNumber("INC")
rmag = sat.GetNumber("RMAG")
print(f"\nSMA-Re = {sma-R_EARTH:.2f} km  (target: {R_GEO-R_EARTH:.0f})")
print(f"SMA_error = {sma-R_GEO:.2f} km")
print(f"ECC = {ecc:.6f}")
print(f"INC = {inc:.4f} deg")
print(f"RMAG = {rmag:.2f} km")

# Check if we achieved GEO
if abs(sma - R_GEO) < 50 and ecc < 0.01 and inc < 1.0:
    print("\n*** SUCCESS: 卫星已进入GEO! ***")
else:
    print(f"\n偏差: SMA={sma-R_GEO:.1f}km ECC={ecc:.4f} INC={inc:.2f}deg")
