#!/usr/bin/env python3
"""
GMAT Python Runner — 通过 GMAT Python API 加载/执行 .script 文件并返回结构化结果。

用法:
    python python_runner.py --script <script_path> --gmat-root <gmat_root> [--objects <name1,name2>]

输出: JSON 到 stdout
    {
        "success": true/false,
        "stage": "init"|"load"|"run"|"read",
        "error": "...",          // 仅失败时
        "summary": "...",        // GMAT 运行摘要
        "objects": {...},        // GetRuntimeObject 读取的参数
        "reports": {...}         // ReportFile 解析后的数据
    }
"""

import argparse
import json
import sys
import os
import traceback

# ==============================================================================
# GMAT 环境初始化
# ==============================================================================

def generate_api_startup_file(gmat_root: str) -> str:
    """
    从 gmat_startup_file.txt 生成 api_startup_file.txt。
    将相对路径 .. 替换为 GMAT 根目录的绝对路径。
    返回 api_startup_file.txt 的完整路径。
    """
    gmat_root = os.path.abspath(gmat_root)
    bin_dir = os.path.join(gmat_root, "bin")
    startup_src = os.path.join(bin_dir, "gmat_startup_file.txt")
    startup_dst = os.path.join(bin_dir, "api_startup_file.txt")

    if not os.path.exists(startup_src):
        raise FileNotFoundError(f"找不到 GMAT startup file: {startup_src}")

    with open(startup_src, "r") as f_in:
        with open(startup_dst, "w") as f_out:
            for line in f_in:
                f_out.write(line.replace("..", gmat_root))

    return startup_dst


def init_gmat(gmat_root: str) -> dict:
    """
    初始化 GMAT Python API。
    返回 {"success": bool, "stage": "init", "error": str}
    """
    try:
        gmat_root = os.path.abspath(gmat_root)
        bin_dir = os.path.join(gmat_root, "bin")
        api_startup = os.path.join(bin_dir, "api_startup_file.txt")

        # 如果 api_startup_file.txt 不存在, 自动生成
        if not os.path.exists(api_startup):
            api_startup = generate_api_startup_file(gmat_root)

        # 将 GMAT bin 目录加入 Python 路径
        if bin_dir not in sys.path:
            sys.path.insert(1, bin_dir)

        # 导入 GMAT Python 绑定
        global gmat
        import gmatpy as gmat

        # 初始化 GMAT
        gmat.Setup(api_startup)

        return {"success": True, "stage": "init"}
    except FileNotFoundError as e:
        return {"success": False, "stage": "init", "error": str(e)}
    except ImportError:
        return {
            "success": False,
            "stage": "init",
            "error": f"无法导入 gmatpy 模块。请确认 GMAT bin 目录 ({bin_dir}) 在 PYTHONPATH 中, 且 gmatpy.pyd 存在。"
        }
    except Exception as e:
        return {"success": False, "stage": "init", "error": f"GMAT 初始化失败: {str(e)}"}


# ==============================================================================
# 脚本加载与执行
# ==============================================================================

def load_script(script_path: str) -> dict:
    """
    加载 GMAT .script 文件。
    返回 {"success": bool, "stage": "load", "error": str}
    """
    try:
        script_path = os.path.abspath(script_path)
        if not os.path.exists(script_path):
            return {"success": False, "stage": "load", "error": f"脚本文件不存在: {script_path}"}

        result = gmat.LoadScript(script_path)
        if not result:
            return {"success": False, "stage": "load", "error": "GMAT 无法解析脚本文件。请检查语法。"}

        return {"success": True, "stage": "load"}
    except Exception as e:
        return {"success": False, "stage": "load", "error": f"脚本加载异常: {str(e)}"}


def run_mission() -> dict:
    """
    执行已加载的 GMAT 任务。
    返回 {"success": bool, "stage": "run", "error": str, "summary": str}
    """
    try:
        result = gmat.RunScript()
        summary = gmat.GetRunSummary() if hasattr(gmat, "GetRunSummary") else ""

        if not result:
            return {
                "success": False,
                "stage": "run",
                "error": "任务执行失败。请检查脚本中的物理参数和停止条件。",
                "summary": summary
            }

        return {"success": True, "stage": "run", "summary": summary}
    except Exception as e:
        return {
            "success": False,
            "stage": "run",
            "error": f"任务执行异常: {str(e)}",
            "summary": ""
        }


# ==============================================================================
# 结果读取
# ==============================================================================

# 常用可读参数列表
COMMON_PARAMETERS = [
    "SMA", "ECC", "INC", "RAAN", "AOP", "TA",
    "X", "Y", "Z", "VX", "VY", "VZ",
    "RMAG", "VMAG", "Altitude",
    "Latitude", "Longitude",
    "TotalMass", "DryMass",
    "ElapsedSecs", "ElapsedDays",
]


def read_object(obj_name: str) -> dict:
    """
    读取单个 GMAT 运行时对象的常用参数。
    返回 {param_name: value, ...}
    """
    try:
        obj = gmat.GetRuntimeObject(obj_name)
        if obj is None:
            return {"_error": f"对象 '{obj_name}' 不存在"}

        params = {}
        for param in COMMON_PARAMETERS:
            try:
                val = obj.GetNumber(param)
                params[param] = val
            except Exception:
                pass  # 参数不存在或不是数值类型

        # 同时尝试读取字符串类型参数
        for str_param in ["DateFormat", "CoordinateSystem", "DisplayStateType", "Epoch"]:
            try:
                val = obj.GetString(str_param)
                if val:
                    params[str_param] = val
            except Exception:
                pass

        return params
    except Exception as e:
        return {"_error": f"读取对象 '{obj_name}' 失败: {str(e)}"}


def read_objects(object_names: list) -> dict:
    """
    读取多个 GMAT 运行时对象。
    返回 {name: {params}, ...}
    """
    if not object_names:
        # 自动检测: 尝试读取常见对象名
        object_names = ["Sat", "Sat1", "Spacecraft", "Spacecraft1"]

    results = {}
    for name in object_names:
        results[name] = read_object(name)
    return results


# ==============================================================================
# ReportFile 解析
# ==============================================================================

def parse_report_file(report_path: str) -> dict:
    """
    解析 GMAT ReportFile 输出。
    返回 {"columns": [...], "data": [[...], ...], "summary": {...}}
    """
    try:
        report_path = os.path.abspath(report_path)
        if not os.path.exists(report_path):
            return {"_error": f"报告文件不存在: {report_path}"}

        with open(report_path, "r") as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            return {"_error": "报告文件为空"}

        # 第一行通常是列标题
        headers = lines[0].split()
        data_rows = []

        for line in lines[1:]:
            parts = line.split()
            if len(parts) == len(headers):
                try:
                    data_rows.append([float(p) for p in parts])
                except ValueError:
                    data_rows.append(parts)

        # 生成摘要
        summary = {}
        if data_rows:
            num_rows = len(data_rows)
            summary["num_rows"] = num_rows
            if all(isinstance(row[0], (int, float)) for row in data_rows):
                summary["first_row"] = data_rows[0]
                summary["last_row"] = data_rows[-1]

        return {"columns": headers, "data": data_rows, "summary": summary}
    except Exception as e:
        return {"_error": f"解析报告文件失败: {str(e)}"}


# ==============================================================================
# 配置加载
# ==============================================================================

def load_config(config_path: str = None) -> dict:
    """
    从 default_config.yaml 加载配置。
    优先级: GMAT_ROOT 环境变量 > YAML 配置文件
    支持 {gmat_root} 占位符自动替换。
    """
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "default_config.yaml")

    if not os.path.exists(config_path):
        return {}

    config = {}
    with open(config_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过注释和空行
            if line.startswith("#") or not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            config[key] = value

    # GMAT_ROOT 环境变量优先
    env_root = os.environ.get("GMAT_ROOT", "")
    if env_root:
        config["gmat_root"] = env_root

    # 替换 {gmat_root} 占位符
    root = config.get("gmat_root", "")
    for k, v in config.items():
        if isinstance(v, str) and "{gmat_root}" in v:
            config[k] = v.replace("{gmat_root}", root)

    return config


# ==============================================================================
# 主入口
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="GMAT Python Runner - 加载/执行 GMAT .script 文件并返回结构化 JSON 结果"
    )
    parser.add_argument(
        "--script", "-s", required=True,
        help="GMAT .script 文件路径"
    )
    parser.add_argument(
        "--gmat-root", "-g", default="",
        help="GMAT 安装根目录 (可省略, 默认从 default_config.yaml 或 GMAT_ROOT 环境变量读取)"
    )
    parser.add_argument(
        "--config", "-c", default="",
        help="配置文件路径 (可省略, 默认使用同目录下的 default_config.yaml)"
    )
    parser.add_argument(
        "--objects", "-o", default="",
        help="要读取的运行时对象名, 逗号分隔 (如 Sat,Sat1)"
    )
    parser.add_argument(
        "--report", "-r", default="",
        help="ReportFile 输出路径 (相对于 GMAT output/ 目录)"
    )

    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config) if args.config else load_config()

    # 确定 GMAT 根目录: CLI 参数 > 环境变量 > 配置文件
    gmat_root = args.gmat_root or config.get("gmat_root", "")
    if not gmat_root:
        print(json.dumps({
            "success": False, "stage": "config",
            "error": "未指定 GMAT 路径。请通过 --gmat-root 参数、GMAT_ROOT 环境变量或 default_config.yaml 配置。"
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    output_dir = config.get("output_dir", os.path.join(gmat_root, "output"))

    result = {"success": False, "stage": "unknown", "error": "", "objects": {}, "reports": {}}

    # Step 1: 初始化 GMAT
    init_result = init_gmat(gmat_root)
    if not init_result["success"]:
        result.update(init_result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    # Step 2: 加载脚本
    load_result = load_script(args.script)
    if not load_result["success"]:
        result.update(load_result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    # Step 3: 执行
    run_result = run_mission()
    if not run_result["success"]:
        result.update(run_result)
        result["stage"] = "run"
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    result["summary"] = run_result.get("summary", "")

    # Step 4: 读取结果
    obj_names = [n.strip() for n in args.objects.split(",") if n.strip()]
    result["objects"] = read_objects(obj_names)
    result["stage"] = "read"

    # Step 5: 解析报告文件 (如果指定)
    if args.report:
        report_full_path = os.path.join(output_dir, args.report)
        result["reports"] = parse_report_file(report_full_path)

    # 尝试自动查找 output_report.txt
    auto_report = os.path.join(output_dir, "output_report.txt")
    if os.path.exists(auto_report) and not args.report:
        result["reports"] = parse_report_file(auto_report)

    result["success"] = True
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
