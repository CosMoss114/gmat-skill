"""
超同步转移轨道 — Stepwise 执行脚本
400km/46deg LEO → 超同步远地点 → GEO 定点东经40°

策略:
  TOI: VNB ImpulsiveBurn (LEO近圆, VNB可靠)
  GOI: EarthMJ2000Eq ImpulsiveBurn (高ECC远地点, 避免VNB)
  Circ: VNB ImpulsiveBurn (GEO近圆)

每步从GMAT实态计算ΔV, 不依赖二体公式预计算。
"""
import math
import os
import sys
import json

# GMAT 初始化
GMAT_ROOT = r"e:\GMAT\gmat-win-R2026a"
bin_dir = os.path.join(GMAT_ROOT, "bin")
sys.path.insert(0, bin_dir)

import gmatpy as gmat

startup = os.path.join(bin_dir, "api_startup_file.txt")
if not os.path.exists(startup):
    # 自动生成
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

OUTPUT_DIR = os.path.join(GMAT_ROOT, "output")
SCRIPT = os.path.join(OUTPUT_DIR, "supersync_step.script")

def run_script(script_content, desc=""):
    """写入脚本、加载、执行、返回是否成功"""
    # 清除上一次运行残留的对象
    for name in ["Sat", "TOI", "GOI", "Circ", "FM", "Prop", "DC"]:
        try:
            gmat.Clear(name)
        except:
            pass
    
    with open(SCRIPT, "w", encoding="ascii") as f:
        f.write(script_content)
    print(f"[{desc}] Loading...")
    if not gmat.LoadScript(SCRIPT):
        # 检查 GmatLog 获取详细错误
        log_path = os.path.join(GMAT_ROOT, "output", "GmatLog.txt")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                lines = lf.readlines()
                for line in lines[-10:]:
                    if "ERROR" in line or "error" in line.lower():
                        print(f"  GmatLog: {line.strip()}")
        print(f"  FAIL: LoadScript returned False")
        return False
    print(f"  Running...")
    if not gmat.RunScript():
        print(f"  FAIL: RunScript returned False")
        return False
    print(f"  OK")
    return True

def get_obj(obj_name):
    """读取运行时对象状态"""
    obj = gmat.GetRuntimeObject(obj_name)
    if obj is None:
        return None
    state = {}
    for p in ["X","Y","Z","VX","VY","VZ","SMA","ECC","INC","RAAN","AOP","TA","RMAG","VMAG","ElapsedSecs","ElapsedDays"]:
        try:
            state[p] = obj.GetNumber(p)
        except:
            pass
    return state

def keplerian_summary(state, label=""):
    if not state or state.get("SMA") is None:
        return f"{label}: N/A"
    sma = state["SMA"]
    ecc = state.get("ECC", 0)
    inc = state.get("INC", 0)
    return (f"{label}: SMA={sma:.2f} (alt={sma-R_EARTH:.1f}), "
            f"ECC={ecc:.6f}, INC={inc:.4f}, Perigee={sma*(1-ecc)-R_EARTH:.1f}, "
            f"Apogee={sma*(1+ecc)-R_EARTH:.1f}")

# ===========================================================================
# Step 1: 构建 TOI 脚本 (VNB, LEO近圆) 并执行
# ===========================================================================
print("=" * 60)
print("Step 1: TOI — VNB ImpulsiveBurn at LEO")
print("=" * 60)

header = """Create Spacecraft Sat;
Sat.DateFormat = UTCGregorian;
Sat.Epoch = '01 Jun 2026 00:00:00.000';
Sat.CoordinateSystem = EarthMJ2000Eq;
Sat.DisplayStateType = Keplerian;
Sat.SMA = """ + str(R_LEO) + """;
Sat.ECC = 0.0001;
Sat.INC = """ + str(INC_INIT) + """;
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
TOI.Element1 = """ + f"{2.9972:.6f}" + """;
TOI.Element2 = 0.0;
TOI.Element3 = 0.0;
TOI.DecrementMass = false;

BeginMissionSequence;
Maneuver TOI(Sat);
"""

script_step1 = header + "Propagate Prop(Sat) {Sat.Earth.Apoapsis};"
if not run_script(script_step1, "TOI+Propagate to Apoapsis"):
    print("FATAL: Step 1 failed")
    sys.exit(1)

state_apo = get_obj("Sat")
print(keplerian_summary(state_apo, "At Apoapsis"))

# ===========================================================================
# Step 2: GOI — EarthMJ2000Eq ImpulsiveBurn
# ===========================================================================
print()
print("=" * 60)
print("Step 2: GOI — EarthMJ2000Eq ImpulsiveBurn at Apoapsis")
print("=" * 60)

rx, ry, rz = state_apo["X"], state_apo["Y"], state_apo["Z"]
vx, vy, vz = state_apo["VX"], state_apo["VY"], state_apo["VZ"]
rmag = math.sqrt(rx**2 + ry**2 + rz**2)
vmag = math.sqrt(vx**2 + vy**2 + vz**2)
r_xy = math.sqrt(rx**2 + ry**2)

print(f"  Position: ({rx:.1f}, {ry:.1f}, {rz:.1f}), |r|={rmag:.1f}")
print(f"  Velocity: ({vx:.4f}, {vy:.4f}, {vz:.4f}), |v|={vmag:.4f}")

# 目标: 赤道面内 (vz_target=0), 速度矢量 ⊥ 位置矢量, 近地点=R_GEO
# 新转移轨道: 近地点=R_GEO, 远地点=当前rmag
a_geo_trans = (R_GEO + rmag) / 2.0
v_target_mag = math.sqrt(2*MU/rmag - MU/a_geo_trans)
print(f"  a_geo_trans={a_geo_trans:.1f}, v_target_mag={v_target_mag:.4f}")

# 赤道面内垂直位置的速度方向
vtx = v_target_mag * (-ry / r_xy)
vty = v_target_mag * (rx / r_xy)
vtz = 0.0

dv_x = vtx - vx
dv_y = vty - vy
dv_z = vtz - vz
dv_mag = math.sqrt(dv_x**2 + dv_y**2 + dv_z**2)
print(f"  Target V: ({vtx:.4f}, {vty:.4f}, {vtz:.4f})")
print(f"  Delta-V: ({dv_x:.4f}, {dv_y:.4f}, {dv_z:.4f}), |DV|={dv_mag:.4f}")

script_goi = header + f"""Maneuver TOI(Sat);
Propagate Prop(Sat) {{Sat.Earth.Apoapsis}};

Create ImpulsiveBurn GOI;
GOI.CoordinateSystem = EarthMJ2000Eq;
GOI.Origin = Earth;
GOI.Axes = MJ2000Eq;
GOI.Element1 = {dv_x:.10f};
GOI.Element2 = {dv_y:.10f};
GOI.Element3 = {dv_z:.10f};
GOI.DecrementMass = false;

Maneuver GOI(Sat);
Propagate Prop(Sat) {{Sat.Earth.Periapsis}};
"""

if not run_script(script_goi, "Re-run TOI + GOI + Propagate to Periapsis"):
    print("FATAL: Step 2 failed")
    sys.exit(1)

state_peri = get_obj("Sat")
print(keplerian_summary(state_peri, "After GOI at Periapsis"))

# ===========================================================================
# Step 3: Circ — VNB ImpulsiveBurn at GEO Perigee
# ===========================================================================
print()
print("=" * 60)
print("Step 3: Circ — VNB ImpulsiveBurn at Perigee (near-GEO)")
print("=" * 60)

# 当前近地点速度
v_peri = math.sqrt(state_peri["VX"]**2 + state_peri["VY"]**2 + state_peri["VZ"]**2)
v_geo_target = math.sqrt(MU / R_GEO)
dv_circ = v_geo_target - v_peri  # 应为负(减速)
print(f"  Current |v|={v_peri:.4f}, Target |v|={v_geo_target:.4f}, DV_circ={dv_circ:.4f}")

# 注意: 当前轨道近地点应该在 GEO 附近, VNB 可用
script_circ = header + f"""Maneuver TOI(Sat);
Propagate Prop(Sat) {{Sat.Earth.Apoapsis}};

Create ImpulsiveBurn GOI;
GOI.CoordinateSystem = EarthMJ2000Eq;
GOI.Origin = Earth;
GOI.Axes = MJ2000Eq;
GOI.Element1 = {dv_x:.10f};
GOI.Element2 = {dv_y:.10f};
GOI.Element3 = {dv_z:.10f};
GOI.DecrementMass = false;

Maneuver GOI(Sat);
Propagate Prop(Sat) {{Sat.Earth.Periapsis}};

Create ImpulsiveBurn Circ;
Circ.CoordinateSystem = Local;
Circ.Origin = Earth;
Circ.Axes = VNB;
Circ.Element1 = {dv_circ:.10f};
Circ.Element2 = 0.0;
Circ.Element3 = 0.0;
Circ.DecrementMass = false;

Maneuver Circ(Sat);
Propagate Prop(Sat) {{Sat.ElapsedDays = 1.0}};
"""

if not run_script(script_circ, "TOI + GOI + Circ + 1-day propagation"):
    print("FATAL: Step 3 failed")
    sys.exit(1)

state_final = get_obj("Sat")
print(keplerian_summary(state_final, "Final GEO"))

# ===========================================================================
# Summary
# ===========================================================================
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"TOI DV: 2.9972 km/s (VNB at LEO)")
print(f"GOI DV: {dv_mag:.4f} km/s (EarthMJ2000Eq at apoapsis)")
print(f"Circ DV: {abs(dv_circ):.4f} km/s (VNB at GEO perigee)")
print(f"Total:  {2.9972 + dv_mag + abs(dv_circ):.4f} km/s")

if state_final:
    print(keplerian_summary(state_final, "Final orbit"))
    sma = state_final.get("SMA", 0)
    ecc = state_final.get("ECC", 0)
    inc = state_final.get("INC", 0)
    if sma > 0:
        print(f"GEO altitude: {sma - R_EARTH:.2f} km above surface")
        print(f"SMA error from GEO: {sma - R_GEO:.2f} km")
    print(f"ECC: {ecc:.6f}")
    print(f"INC: {inc:.4f} deg")

print()
print("All steps completed successfully!")
