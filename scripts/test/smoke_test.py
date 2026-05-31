#!/usr/bin/env python3
"""
GMAT Agent Smoke Tests — 快速冒烟测试，覆盖核心管线关键路径。

用法:
    python smoke_test.py                  # 运行全部测试
    python smoke_test.py --verbose        # 详细输出

退出码: 0 = 全部通过, 1 = 有失败
"""

import argparse
import json
import os
import subprocess
import sys

# ---- 配置 ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
RUNNER = os.path.join(SKILL_ROOT, "scripts", "runner", "python_runner.py")
TEMPLATE_SIMPLE = os.path.join(SKILL_ROOT, "references", "templates",
                               "simple_propagation.script")
TEMPLATE_PARAM = os.path.join(SKILL_ROOT, "references", "templates",
                              "parameterized_propagation.script")
OEM_READER = os.path.join(SKILL_ROOT, "scripts", "analysis", "oem_reader.py")
OEM_FILE = os.path.join(SKILL_ROOT, "data", "oem",
                        "CSS_OEM_20260529004933_0001.dat")

TESTS = []


def test(name: str):
    """装饰器：注册测试函数。"""
    def decorator(fn):
        TESTS.append((name, fn))
        return fn
    return decorator


def _run_runner(*extra_args) -> dict:
    """运行 python_runner.py 并返回解析后的 JSON。"""
    cmd = [sys.executable, RUNNER] + list(extra_args)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                          cwd=SKILL_ROOT)

    # runner 默认输出 JSON 到 stdout
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        return {"_raw_stdout": proc.stdout[:500], "_raw_stderr": proc.stderr[:500],
                "_rc": proc.returncode}


# =====================================================================
# 测试用例
# =====================================================================

@test("simple propagation")
def test_simple_propagation():
    """简单传播：success=true, objects.Sat.SMA 存在。"""
    result = _run_runner("--script", TEMPLATE_SIMPLE, "--objects", "Sat")
    assert result.get("success"), f"success != true: {result.get('error','?')}"
    objects = result.get("objects", {})
    assert "Sat" in objects, "objects 中缺少 Sat"
    assert "SMA" in objects["Sat"], "Sat 中缺少 SMA"
    return f"SMA={objects['Sat']['SMA']:.1f} km"


@test("parameterized propagation")
def test_parameterized_propagation():
    """参数化传播：-D SMA=7200 → success=true。"""
    result = _run_runner("--script", TEMPLATE_PARAM, "--objects", "Sat",
                         "-D", "SMA=7200")
    assert result.get("success"), f"success != true: {result.get('error','?')}"
    return f"SMA={result['objects']['Sat']['SMA']:.1f} km (input=7200)"


@test("script validation")
def test_script_validation():
    """脚本校验：--validate-only → _validation.valid==true。"""
    result = _run_runner("--script", TEMPLATE_SIMPLE, "--validate-only")
    val = result.get("_validation", {})
    assert val.get("valid"), f"validation.valid != true: {val.get('errors',[])}"
    return "OK"


@test("error diagnostics")
def test_error_diagnostics():
    """错误诊断：BadField → success=false, stage==load。"""
    import tempfile
    bad_script = os.path.join(tempfile.gettempdir(), "test_bad_smoke.script")
    with open(bad_script, "w", encoding="ascii") as f:
        f.write("""Create Spacecraft Sat;
Sat.DateFormat = UTCGregorian;
Sat.Epoch = '01 Jan 2025 12:00:00.000';
Sat.CoordinateSystem = EarthMJ2000Eq;
Sat.DisplayStateType = Keplerian;
Sat.BADFIELD = 7100;
Sat.DryMass = 850;

Create ForceModel FM;
FM.CentralBody = Earth;

Create Propagator Prop;
Prop.FM = FM;
Prop.Type = PrinceDormand78;

BeginMissionSequence;
Propagate Prop(Sat) {Sat.ElapsedDays = 3};
""")

    result = _run_runner("--script", bad_script, "--objects", "Sat")
    os.unlink(bad_script)
    assert not result.get("success"), "错误脚本竟然 success=true"
    assert result.get("stage") == "load", f"stage != load: {result.get('stage')}"
    err = result.get("error", "")
    assert "BADFIELD" in err.upper() or "not permitted" in err, \
        f"错误信息不含 BADFIELD: {err[:100]}"
    return "error detected correctly"


@test("OEM parsing")
def test_oem_parsing():
    """OEM 解析：已知文件可正确解析。"""
    if not os.path.exists(OEM_FILE):
        return "SKIPPED (no OEM data in data/oem/)"

    proc = subprocess.run([sys.executable, OEM_READER, OEM_FILE],
                          capture_output=True, text=True, timeout=30,
                          cwd=SKILL_ROOT)
    output = proc.stdout
    assert "Parsed:" in output, f"输出不含 'Parsed:': {output[:200]}"
    return "OK"


# =====================================================================
# 主入口
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="GMAT Agent Smoke Tests"
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="详细输出")
    args = parser.parse_args()

    passed = 0
    failed = 0
    skipped = 0

    print(f"GMAT Agent Smoke Tests ({len(TESTS)} tests)\n")

    for name, fn in TESTS:
        try:
            detail = fn()
            if detail and detail.startswith("SKIPPED"):
                skipped += 1
                status = "SKIP"
            else:
                passed += 1
                status = "PASS"
            print(f"  [{status}] {name}")
            if detail and args.verbose:
                print(f"         {detail}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}")
            print(f"         {e}")
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {name} (exception)")
            print(f"         {e}")

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
