#!/usr/bin/env python3
"""
Parameter Scan — 批量扫描轨道参数，自动汇总结果。

通过多次调用 python_runner.py 执行参数化模板，支持单参数范围和
多参数网格扫描。自动收集结果并输出表格/CSV/JSON/趋势图。

用法:
    # 单参数扫描
    python parameter_scan.py -p SMA=6600:7600:200 --objects Sat

    # 多参数网格扫描
    python parameter_scan.py -p SMA=6600:7600:1000 -p INC=0:90:45

    # 输出到文件
    python parameter_scan.py -p SMA=6600:7600:200 --csv results.csv --plot plot.png
"""

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from datetime import datetime

# ---- 配置 ----
MU_EARTH = 398600.4418  # km³/s²
EARTH_RADIUS = 6378.1363  # km

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
RUNNER = os.path.join(SKILL_ROOT, "scripts", "runner", "python_runner.py")
DEFAULT_TEMPLATE = os.path.join(SKILL_ROOT, "references", "templates",
                                "parameterized_propagation.script")


def parse_param_spec(spec: str) -> dict:
    """
    解析参数规格。

    "SMA=6600:7600:200" → {"key": "SMA", "values": [6600, 6800, 7000, 7200, 7400, 7600]}
    "INC=60"            → {"key": "INC", "values": [60]}
    "INC=0:90:45"       → {"key": "INC", "values": [0, 45, 90]}
    """
    if "=" not in spec:
        raise ValueError(f"参数格式错误，需要 KEY=VALUE 或 KEY=START:END:STEP: {spec}")

    key, val_str = spec.split("=", 1)

    if ":" in val_str:
        parts = val_str.split(":")
        if len(parts) == 3:
            start, end, step = float(parts[0]), float(parts[1]), float(parts[2])
            # 生成浮点数范围
            values = []
            v = start
            if step > 0:
                while v <= end + 1e-9:
                    # 智能取整：如果全是整数则用 int
                    if start == int(start) and end == int(end) and step == int(step):
                        values.append(int(round(v)))
                    else:
                        values.append(round(v, 4))
                    v += step
            else:
                raise ValueError(f"步长必须为正: {spec}")
        else:
            raise ValueError(f"范围格式错误，需要 START:END:STEP: {spec}")
    else:
        # 单值：尝试解析为数字，否则保留字符串
        try:
            v = float(val_str)
            values = [int(v) if v == int(v) else v]
        except ValueError:
            values = [val_str]

    return {"key": key, "values": values}


def generate_combinations(param_specs: list[dict]) -> list[dict]:
    """生成参数组合的笛卡尔积。"""
    import itertools

    keys = [p["key"] for p in param_specs]
    value_lists = [p["values"] for p in param_specs]

    combos = []
    for vals in itertools.product(*value_lists):
        combo = dict(zip(keys, vals))
        # 添加 -D 格式的标签
        combo["_label"] = ", ".join(f"{k}={v}" for k, v in combo.items())
        combos.append(combo)

    return combos


def run_single(combo: dict, template: str, objects: str) -> dict:
    """执行单次参数化传播，返回结果 dict。"""
    cmd = [sys.executable, RUNNER,
           "--script", template,
           "--objects", objects]

    for key, val in combo.items():
        if not key.startswith("_"):
            cmd.extend(["-D", f"{key}={val}"])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                              cwd=SKILL_ROOT)
        if proc.returncode != 0:
            return {"_error": f"runner 返回码 {proc.returncode}",
                    "_stderr": proc.stderr[:500]}

        result = json.loads(proc.stdout)
        if not result.get("success"):
            return {"_error": result.get("error", "未知错误"),
                    "_stage": result.get("stage", "?")}

        # 提取对象参数
        objects_data = result.get("objects", {})
        obj_result = {}
        for obj_name, props in objects_data.items():
            for prop, val in props.items():
                obj_result[f"{obj_name}.{prop}"] = val

        # 派生值
        sma = obj_result.get(f"{objects.split(',')[0]}.SMA")
        ecc = obj_result.get(f"{objects.split(',')[0]}.ECC", 0)
        if sma:
            obj_result["_period_min"] = round(
                2 * math.pi * math.sqrt(sma ** 3 / MU_EARTH) / 60, 1)
            obj_result["_perigee_km"] = round(
                sma * (1 - ecc) - EARTH_RADIUS, 2)
            obj_result["_apogee_km"] = round(
                sma * (1 + ecc) - EARTH_RADIUS, 2)

        return obj_result

    except subprocess.TimeoutExpired:
        return {"_error": "执行超时 (120s)"}
    except json.JSONDecodeError:
        return {"_error": "JSON 解析失败", "_stdout": proc.stdout[:500]}
    except Exception as e:
        return {"_error": str(e)}


def run_scan(param_specs: list[dict], template: str, objects: str,
             verbose: bool = True) -> dict:
    """执行完整扫描。"""
    combos = generate_combinations(param_specs)
    total = len(combos)
    param_keys = [p["key"] for p in param_specs]

    if verbose:
        print(f"扫描参数: {', '.join(param_keys)}")
        print(f"共 {total} 个组合\n")

    results = []
    errors = 0
    t0 = datetime.now()

    for i, combo in enumerate(combos):
        label = combo["_label"]
        if verbose:
            print(f"[{i + 1}/{total}] {label} ... ", end="", flush=True)

        data = run_single(combo, template, objects)

        if "_error" in data:
            errors += 1
            if verbose:
                print(f"✗ {data['_error']}")
        else:
            if verbose:
                print("✓")

        row = {k: v for k, v in combo.items() if not k.startswith("_")}
        row.update(data)
        results.append(row)

    elapsed = (datetime.now() - t0).total_seconds()

    return {
        "results": results,
        "total": total,
        "errors": errors,
        "elapsed_s": round(elapsed, 1),
        "param_keys": param_keys,
    }


def format_table(scan: dict) -> str:
    """格式化扫描结果为终端表格。"""
    results = scan["results"]
    if not results:
        return "(无结果)"

    # 确定显示列：参数键 + 关键输出
    param_keys = scan["param_keys"]
    output_keys = []
    for key in results[0].keys():
        if not key.startswith("_") and key not in param_keys:
            output_keys.append(key)
    # 优先显示的派生列
    derived_order = ["_period_min", "_perigee_km", "_apogee_km"]
    derived = [k for k in derived_order if k in output_keys]
    named = [k for k in output_keys if k not in derived_order and not k.startswith("_")]
    # 只选前 8 个命名列 + 派生列
    display_keys = param_keys + named[:8] + derived

    # 列宽
    col_widths = {}
    for key in display_keys:
        col_widths[key] = len(key)
        for r in results:
            val_str = _fmt_val(r.get(key, ""))
            col_widths[key] = max(col_widths[key], len(val_str))

    # 表头
    header = "│ " + " │ ".join(
        key.ljust(col_widths[key]) for key in display_keys) + " │"
    sep = "├" + "┼".join("─" * (col_widths[k] + 2) for k in display_keys) + "┤"
    top = "┌" + "┬".join("─" * (col_widths[k] + 2) for k in display_keys) + "┐"
    bot = "└" + "┴".join("─" * (col_widths[k] + 2) for k in display_keys) + "┘"

    lines = [top, header, sep]
    for r in results:
        row = "│ " + " │ ".join(
            _fmt_val(r.get(key, "")).ljust(col_widths[key])
            for key in display_keys) + " │"
        lines.append(row)
    lines.append(bot)

    return "\n".join(lines)


def _fmt_val(val) -> str:
    """格式化单个值为字符串。"""
    if val is None:
        return "?"
    if isinstance(val, float):
        if abs(val) < 0.01 and val != 0:
            return f"{val:.4f}"
        return f"{val:.4g}"
    return str(val)


def write_csv(scan: dict, path: str):
    """输出 CSV。"""
    results = scan["results"]
    if not results:
        return
    all_keys = list(results[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(results)


def write_plot(scan: dict, path: str):
    """生成扫描参数 vs 关键输出量的趋势图。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("⚠ matplotlib 未安装，跳过绘图。pip install matplotlib 以启用。")
        return

    results = scan["results"]
    if len(results) < 2:
        print("⚠ 至少需要 2 个数据点才能绘图。")
        return

    param_keys = scan["param_keys"]
    if len(param_keys) != 1:
        print("⚠ 多参数网格扫描暂不支持自动绘图（请用单参数扫描）。")
        return

    x_key = param_keys[0]
    x_vals = [r[x_key] for r in results]

    # 找出可绘制的数值列
    plot_keys = []
    for k in results[0].keys():
        if k.startswith("_") and k in ("_period_min", "_perigee_km", "_apogee_km"):
            plot_keys.append(k)
    # 加 SMA 和 ECC
    for k in ["Sat.SMA", "Sat.ECC"]:
        if k in results[0]:
            plot_keys.append(k)

    if not plot_keys:
        print("⚠ 无可绘制的数值列。")
        return

    n_plots = len(plot_keys)
    fig, axes = plt.subplots(n_plots, 1, figsize=(8, 3 * n_plots), sharex=True)
    if n_plots == 1:
        axes = [axes]

    for ax, y_key in zip(axes, plot_keys):
        y_vals = [r.get(y_key) for r in results]
        ax.plot(x_vals, y_vals, "o-", markersize=6)
        ax.set_ylabel(y_key.replace("_", " ").strip())
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel(x_key)
    fig.suptitle(f"Parameter Scan: {x_key}", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  图表已保存: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="批量扫描轨道参数，自动汇总结果"
    )
    parser.add_argument(
        "-p", "--param", action="append", required=True,
        help="参数规格: KEY=VALUE 或 KEY=START:END:STEP (可多次指定)"
    )
    parser.add_argument(
        "--template", default=DEFAULT_TEMPLATE,
        help=f"参数化模板路径 (默认: parameterized_propagation.script)"
    )
    parser.add_argument(
        "--objects", default="Sat",
        help="要读取的 GMAT 对象名 (默认: Sat)"
    )
    parser.add_argument(
        "--csv", default="",
        help="输出 CSV 文件路径"
    )
    parser.add_argument(
        "--json-output", default="",
        help="输出 JSON 文件路径"
    )
    parser.add_argument(
        "--plot", default="",
        help="输出趋势图 PNG 路径 (需 matplotlib)"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="静默模式 (仅输出最终表格)"
    )
    args = parser.parse_args()

    # 解析参数规格
    param_specs = [parse_param_spec(p) for p in args.param]

    # 执行扫描
    scan = run_scan(param_specs, args.template, args.objects,
                    verbose=not args.quiet)

    # 输出
    if not args.quiet:
        print()

    print(format_table(scan))
    print(f"\n{scan['total']} 次运行, {scan['errors']} 失败, "
          f"耗时 {scan['elapsed_s']}s")

    # 文件输出
    if args.csv:
        write_csv(scan, args.csv)
        print(f"CSV: {args.csv}")

    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as f:
            json.dump(scan, f, indent=2, ensure_ascii=False)
        print(f"JSON: {args.json_output}")

    if args.plot:
        write_plot(scan, args.plot)

    sys.exit(1 if scan["errors"] > 0 else 0)
