#!/usr/bin/env python3
"""
GMAT Python Runner — 通过 GMAT Python API 加载/执行 .script 文件并返回结构化结果。

用法:
    python python_runner.py --script <script_path> --gmat-root <gmat_root> [--objects <name1,name2>]

输出: JSON 到 stdout
    {
        "success": true/false,
        "stage": "init"|"load"|"run"|"read",
        "error": "...",
        "summary": "...",
        "objects": {...},
        "reports": {...}
    }

程序化 API 用法 (无需 .script 文件):
    from python_runner import init_gmat, create_and_read_state

    init_gmat(r"C:\\GMAT")
    keplerian = create_and_read_state(
        epoch="01 Jun 2026 00:00:00.000",
        x=-5525.77, y=-1872.37, z=3428.75,
        vx=0.299, vy=-6.928, vz=-3.289
    )
    # -> {"SMA": 6767.86, "ECC": 0.00077, "INC": 41.60, ...}
"""

import argparse
import json
import re
import subprocess
import sys
import os
import traceback

# ==============================================================================
# 程序化 API: Construct + SetField + Initialize
# ==============================================================================

# Default Keplerian parameters to read
_KEPLERIAN_PARAMS = ["SMA", "ECC", "INC", "RAAN", "AOP", "TA", "RMAG", "VMAG"]


def create_and_read_state(epoch, x, y, z, vx, vy, vz,
                          frame="EarthMJ2000Eq", obj_name="Sat"):
    """
    通过 GMAT API 直接设置 Cartesian 状态并返回 Keplerian 根数。
    无需 .script 文件 — 纯 Python 调用。

    Args:
        epoch:  GMAT 格式的历元字符串 ("01 Jun 2026 00:00:00.000")
        x, y, z:   位置 (km)
        vx, vy, vz: 速度 (km/s)
        frame:      坐标系 (默认 EarthMJ2000Eq)
        obj_name:   对象名

    Returns:
        dict: Keplerian elements + perigee/apogee altitude,
              或 {"error": "..."} 如果失败
    """
    try:
        # 确保不重名
        gmat.Clear(obj_name)
        sat = gmat.Construct("Spacecraft", obj_name)
        sat.SetField("DateFormat", "UTCGregorian")
        sat.SetField("Epoch", epoch)
        sat.SetField("CoordinateSystem", frame)
        sat.SetField("DisplayStateType", "Cartesian")
        sat.SetField("X", x)
        sat.SetField("Y", y)
        sat.SetField("Z", z)
        sat.SetField("VX", vx)
        sat.SetField("VY", vy)
        sat.SetField("VZ", vz)

        # Initialize 后才能读取 Keplerian
        gmat.Initialize()

        result = {}
        for p in _KEPLERIAN_PARAMS:
            try:
                result[p] = sat.GetNumber(p)
            except Exception:
                result[p] = None

        # 计算近/远地点高度
        sma = result.get("SMA")
        ecc = result.get("ECC")
        if sma and ecc is not None:
            result["Perigee_km"] = sma * (1 - ecc) - 6378.1363
            result["Apogee_km"] = sma * (1 + ecc) - 6378.1363

        return result
    except Exception as e:
        return {"error": str(e)}

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
    global _gmat_root_cache
    try:
        gmat_root = os.path.abspath(gmat_root)
        _gmat_root_cache = gmat_root  # 缓存给错误诊断用
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
# 错误诊断: 从 GmatLog.txt 提取具体错误信息
# ==============================================================================

def _find_gmat_log(gmat_root: str) -> str:
    """在 GMAT 输出目录中查找 GmatLog.txt"""
    candidates = [
        os.path.join(gmat_root, "output", "GmatLog.txt"),
        os.path.join(gmat_root, "bin", "GmatLog.txt"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return ""


def extract_script_errors(gmat_root: str, script_path: str = None) -> list:
    """
    从 GmatLog.txt 中提取与脚本解析/执行相关的错误行。
    返回 [{"line": int, "message": str, "raw": str}, ...]
    """
    log_path = _find_gmat_log(gmat_root)
    if not log_path:
        return []

    errors = []
    script_name = os.path.basename(script_path) if script_path else ""

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()
                # GMAT 错误行格式: "   line_num: path: **** ERROR **** ..."
                m = re.search(
                    r"(?:^\s*(\d+):\s*(.+?):\s*\*+\s*(ERROR|Exception|Hardware Exception).*?\*+\s*(.+))",
                    line
                )
                if m:
                    errors.append({
                        "line": int(m.group(1)),
                        "file": m.group(2).strip(),
                        "type": m.group(3).strip(),
                        "message": m.group(4).strip(),
                        "raw": line,
                    })
                    continue

                # 备用匹配: **** ERROR **** ...
                m2 = re.search(r"\*+\s*(ERROR|Exception)\s*\*+\s*(.+)", line)
                if m2:
                    errors.append({
                        "line": 0,
                        "file": script_name,
                        "type": m2.group(1).strip(),
                        "message": m2.group(2).strip(),
                        "raw": line,
                    })
    except Exception:
        pass

    return errors


# ==============================================================================
# 脚本校验: 通过 GmatConsole 子进程预检脚本
# ==============================================================================

def _check_script_ascii(script_path: str) -> list:
    """
    预检脚本文件是否为纯 ASCII。GMAT 解释器拒绝任何非 ASCII 字符（包括注释中的中文、em-dash 等）。
    返回非法行列表: [{"line": int, "char": str, "col": int}, ...]
    """
    violations = []
    try:
        with open(script_path, "r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                for col, ch in enumerate(line, 1):
                    if ord(ch) > 127:
                        violations.append({
                            "line": line_no,
                            "char": ch,
                            "codepoint": f"U+{ord(ch):04X}",
                            "col": col,
                        })
    except Exception:
        pass
    return violations


def validate_script(script_path: str, gmat_root: str) -> dict:
    """
    通过 GmatConsole --run --minimize 预检脚本语法。
    返回 {"valid": bool, "errors": [...], "raw_output": str}

    注意: GmatConsole 会实际执行脚本，对长仿真可能较慢。
    """
    gmat_root = os.path.abspath(gmat_root)
    gmat_console = os.path.join(gmat_root, "bin", "GmatConsole.exe")
    if not os.path.isfile(gmat_console):
        # Linux/macOS fallback
        gmat_console = os.path.join(gmat_root, "bin", "GmatConsole")
    if not os.path.isfile(gmat_console):
        return {"valid": False, "errors": [{"line": 0, "message": f"GmatConsole not found: {gmat_console}"}], "raw_output": ""}

    # ---- ASCII 预检 ----
    ascii_violations = _check_script_ascii(script_path)
    if ascii_violations:
        lines_msg = "; ".join(
            f"Line {v['line']}: non-ASCII '{v['char']}' ({v['codepoint']}) at col {v['col']}"
            for v in ascii_violations[:5]
        )
        return {
            "valid": False,
            "errors": [{
                "line": ascii_violations[0]["line"],
                "file": os.path.basename(script_path),
                "type": "ASCII",
                "message": f"脚本包含非 ASCII 字符: {lines_msg}。GMAT .script 文件必须为纯 ASCII（包括注释）。请将中文标点（—、""、''）替换为 ASCII 等价字符（-、\"、'）。",
            }],
            "raw_output": "",
        }

    script_abs = os.path.abspath(script_path)

    try:
        proc = subprocess.run(
            [gmat_console, "--run", script_abs, "--minimize"],
            capture_output=True, timeout=120,
            cwd=os.path.join(gmat_root, "bin"),
        )
        # 强制 UTF-8 解码，无法解码的字符用 ? 替代，避免 GBK 编码错误
        stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        output = stdout + "\n" + stderr

        # 提取错误行
        errors = []
        for raw_line in output.splitlines():
            line = raw_line.strip()
            m = re.search(
                r"(?:^\s*(\d+):\s*(.+?):\s*\*+\s*(ERROR|Exception|Hardware Exception).*?\*+\s*(.+))",
                line
            )
            if m:
                errors.append({
                    "line": int(m.group(1)),
                    "file": m.group(2).strip(),
                    "type": m.group(3).strip(),
                    "message": m.group(4).strip(),
                })
                continue
            m2 = re.search(r"\*+\s*(ERROR|Exception)\s*\*+\s*(.+)", line)
            if m2:
                errors.append({
                    "line": 0, "file": os.path.basename(script_path),
                    "type": m2.group(1).strip(), "message": m2.group(2).strip(),
                })

        status_line = ""
        for l in output.splitlines():
            if "successful" in l.lower() or "failed" in l.lower():
                status_line = l

        return {
            "valid": len(errors) == 0 and proc.returncode == 0,
            "errors": errors,
            "raw_output": output,
            "status_line": status_line,
        }
    except subprocess.TimeoutExpired:
        return {"valid": False, "errors": [{"line": 0, "message": "GmatConsole validation timed out (120s)"}], "raw_output": ""}
    except Exception as e:
        return {"valid": False, "errors": [{"line": 0, "message": f"GmatConsole validation failed: {str(e)}"}], "raw_output": ""}


# ==============================================================================
# 模板参数化: 占位符替换
# ==============================================================================

def apply_template(script_path: str, variables: dict) -> str:
    """
    读取脚本文件，将 {{KEY}} 占位符替换为对应值，写入临时文件并返回路径。

    支持从模板注释中解析默认值:
        %% Defaults: SMA=6600 ECC=0.01 INC=45 EPOCH='01 Jan 2025 12:00:00.000'
    未通过 -D 提供的变量自动使用默认值填充。

    示例:
        script 内容:  Sat.SMA = {{SMA}};
        调用:         apply_template("t.script", {"SMA": "7100"})
        结果:         Sat.SMA = 7100;

    返回: 临时脚本文件的绝对路径 (调用方负责清理)
    """
    script_path = os.path.abspath(script_path)
    with open(script_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # ---- 解析模板默认值 ----
    # 格式: %% Defaults: KEY1=val1 KEY2='val with spaces' KEY3=42
    defaults = {}
    default_match = re.search(r'%%\s*Defaults\s*:\s*(.+)', content)
    if default_match:
        defaults_str = default_match.group(1)
        # 匹配 KEY='value' 或 KEY=value (值可含空格如果被单引号包裹)
        for m in re.finditer(r"(\w+)=(?:'([^']*)'|(\S+))", defaults_str):
            key = m.group(1)
            val = m.group(2) if m.group(2) is not None else m.group(3)
            defaults[key] = val

    # ---- 合并: 用户变量优先, 未提供的用默认值 ----
    merged = dict(defaults)
    merged.update(variables)

    # ---- 单遍替换 (避免级联: value 中的 {{KEY}} 不会被二次替换) ----
    def _replace_placeholder(match):
        key = match.group(1)
        return str(merged.get(key, match.group(0)))
    content = re.sub(r'\{\{(\w+)\}\}', _replace_placeholder, content)

    # 检查是否有未替换的占位符
    unreplaced = re.findall(r'\{\{(\w+)\}\}', content)
    if unreplaced:
        import warnings
        warnings.warn(f"模板中以下占位符未被替换且无默认值: {unreplaced}")

    # 写入临时文件 (保留原文件名便于错误定位)
    dir_name = os.path.dirname(script_path)
    base_name = os.path.splitext(os.path.basename(script_path))[0]
    import tempfile
    fd, tmp_path = tempfile.mkstemp(
        suffix=".script", prefix=base_name + "_", dir=dir_name
    )
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)

    return tmp_path


# ==============================================================================
# 脚本加载与执行 (带错误诊断)
# ==============================================================================

# GMAT 根目录缓存 (init 后设置)
_gmat_root_cache = ""
_original_stdout = None


def _suppress_gmat_output():
    """将 stdout 重定向到 os.devnull，抑制 GMAT 调试输出"""
    global _original_stdout
    if _original_stdout is not None:
        return  # 已抑制, 避免嵌套调用丢失原始 stdout 引用
    _original_stdout = sys.stdout
    sys.stdout = open(os.devnull, "w")


def _restore_stdout():
    """恢复原始 stdout"""
    global _original_stdout
    if _original_stdout is not None:
        sys.stdout.close()
        sys.stdout = _original_stdout
        _original_stdout = None


def _with_suppressed_output(fn, *args, **kwargs):
    """安全执行 fn，确保 suppress/restore 始终配对，即使 fn 抛出异常"""
    _suppress_gmat_output()
    try:
        return fn(*args, **kwargs)
    finally:
        _restore_stdout()


def load_script(script_path: str, gmat_root: str = "") -> dict:
    """
    加载 GMAT .script 文件。
    失败时自动从 GmatLog.txt 提取详细错误；若无，降级到 GmatConsole 校验。
    返回 {"success": bool, "stage": "load", "error": str, "details": [...]}
    """
    try:
        script_path = os.path.abspath(script_path)
        if not os.path.exists(script_path):
            return {"success": False, "stage": "load", "error": f"脚本文件不存在: {script_path}", "details": []}

        # ---- ASCII 预检 ----
        ascii_violations = _check_script_ascii(script_path)
        if ascii_violations:
            lines_msg = "; ".join(
                f"Line {v['line']}: '{v['char']}' ({v['codepoint']}) at col {v['col']}"
                for v in ascii_violations[:5]
            )
            return {
                "success": False, "stage": "load",
                "error": f"脚本包含非 ASCII 字符: {lines_msg}。GMAT .script 文件必须为纯 ASCII。请将中文标点替换为 ASCII 等价字符。",
                "details": ascii_violations,
            }

        result = gmat.LoadScript(script_path)
        if not result:
            root = gmat_root or _gmat_root_cache
            details = extract_script_errors(root, script_path) if root else []
            # GmatLog 通常被 API 覆盖为空，降级到 GmatConsole
            if not details and root and os.path.isfile(
                os.path.join(root, "bin", "GmatConsole.exe") if os.name == "nt"
                else os.path.join(root, "bin", "GmatConsole")
            ):
                val = validate_script(script_path, root)
                if val.get("errors"):
                    details = val["errors"]
            if details:
                lines = "; ".join(
                    f"Line {d['line']}: {d['message']}" for d in details[:3]
                )
                return {
                    "success": False, "stage": "load",
                    "error": f"GMAT 无法解析脚本文件: {lines}",
                    "details": details,
                }
            return {"success": False, "stage": "load", "error": "GMAT 无法解析脚本文件。请检查语法。", "details": []}

        return {"success": True, "stage": "load", "details": []}
    except Exception as e:
        return {"success": False, "stage": "load", "error": f"脚本加载异常: {str(e)}", "details": []}


def run_mission() -> dict:
    """
    执行已加载的 GMAT 任务。
    失败时自动从 GmatLog.txt 提取详细错误。
    """
    try:
        result = gmat.RunScript()
        summary = gmat.GetRunSummary() if hasattr(gmat, "GetRunSummary") else ""

        if not result:
            details = extract_script_errors(_gmat_root_cache) if _gmat_root_cache else []
            if details:
                lines = "; ".join(
                    f"Line {d['line']}: {d['message']}" for d in details[:3]
                )
                return {
                    "success": False, "stage": "run",
                    "error": f"任务执行失败: {lines}",
                    "summary": summary, "details": details,
                }
            return {
                "success": False, "stage": "run",
                "error": "任务执行失败。请检查脚本中的物理参数和停止条件。",
                "summary": summary, "details": [],
            }

        return {"success": True, "stage": "run", "summary": summary, "details": []}
    except Exception as e:
        details = extract_script_errors(_gmat_root_cache) if _gmat_root_cache else []
        return {
            "success": False, "stage": "run",
            "error": f"任务执行异常: {str(e)}",
            "summary": "", "details": details,
        }


# ==============================================================================
# 结果读取
# ==============================================================================

# 常用可读参数列表 (按对象类型分组，尝试读取时自动跳过不适用的参数)
COMMON_PARAMETERS = (
    # Spacecraft / CelestialBody
    "SMA", "ECC", "INC", "RAAN", "AOP", "TA",
    "X", "Y", "Z", "VX", "VY", "VZ",
    "RMAG", "VMAG", "Earth.Altitude",
    "Latitude", "Longitude",
    "TotalMass", "DryMass",
    "ElapsedSecs", "ElapsedDays",
    # ImpulsiveBurn / FiniteBurn
    "Element1", "Element2", "Element3",
    # ChemicalThruster
    "C1", "C2", "C3",
    # DifferentialCorrector
    "MaximumIterations",
)


def read_object(obj_name: str) -> dict:
    """
    读取单个 GMAT 运行时对象的常用参数。
    自动适配 Spacecraft / ImpulsiveBurn / ChemicalThruster / DifferentialCorrector 等类型。
    返回 {param_name: value, ..., "_type": "推断类型"}
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
        for str_param in ["DateFormat", "CoordinateSystem", "DisplayStateType", "Epoch",
                          "Axes", "Origin"]:
            try:
                val = obj.GetString(str_param)
                if val:
                    params[str_param] = val
            except Exception:
                pass

        # 推断对象类型
        if params.get("SMA") is not None or params.get("X") is not None:
            params["_type"] = "Spacecraft"
        elif params.get("Element1") is not None:
            params["_type"] = "ImpulsiveBurn" if not params.get("C1") else "ChemicalThruster"

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
    从 default_config.yaml 加载配置，优先使用 yaml.safe_load()（需 PyYAML）。
    若 PyYAML 不可用，降级为简单行解析（仅提取 gmat_root 和 output_dir）。

    优先级: --gmat-root CLI > GMAT_ROOT 环境变量 > YAML 文件中的 gmat_root
    支持 {gmat_root} 占位符自动展开（顶层键和嵌套字符串值均适用）。
    """
    if config_path is None:
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets")
        config_path = os.path.join(assets_dir, "default_config.yaml")

    if not os.path.exists(config_path):
        return {}

    # ---- 尝试 yaml.safe_load() ----
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except ImportError:
        # PyYAML 不可用，降级为简单行解析
        config = {}
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
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

    # 替换 {gmat_root} 占位符（顶层字符串值 + 一层嵌套字符串值）
    def _expand_placeholder(v):
        if isinstance(v, str) and "{gmat_root}" in v:
            return v.replace("{gmat_root}", root or "")
        if isinstance(v, dict):
            return {k2: _expand_placeholder(v2) for k2, v2 in v.items()}
        return v

    root = config.get("gmat_root", "")
    if root:
        config = {k: _expand_placeholder(v) for k, v in config.items()}

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
    parser.add_argument(
        "--validate", "-V", action="store_true",
        help="通过 GmatConsole 预检脚本语法后再执行"
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="仅运行 GmatConsole 预检，不执行 API 运行"
    )
    parser.add_argument(
        "--var", "-D", action="append", default=[],
        help="模板变量替换: KEY=VALUE (可多次指定, 替换脚本中 {{KEY}} 占位符)"
    )
    parser.add_argument(
        "--no-cleanup", action="store_true",
        help="保留模板替换生成的临时脚本文件 (调试用)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="输出进度信息到 stderr (默认静默，JSON 输出不混入诊断)"
    )
    parser.add_argument(
        "--format", "-f", default="json", choices=["json", "csv", "markdown"],
        help="输出格式: json (默认) | csv | markdown"
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
    _messages = []  # 诊断信息收集 (始终在 JSON 中返回)

    def _log(msg: str):
        _messages.append(msg)
        if args.verbose:
            print(f"[{result.get('stage','info')}] {msg}", file=sys.stderr)

    # --- Step 0: 模板参数化 ---
    script_to_run = args.script
    tmp_script_path = ""
    template_vars = {}
    if args.var:
        for kv in args.var:
            if "=" in kv:
                k, v = kv.split("=", 1)
                template_vars[k.strip()] = v.strip()
        if template_vars:
            tmp_script_path = apply_template(args.script, template_vars)
            script_to_run = tmp_script_path
            _log(f"Template variables applied: {template_vars}")
            _log(f"Generated temporary script: {tmp_script_path}")

    # --- Step 0.5: GmatConsole 校验 (可选) ---
    if args.validate or args.validate_only:
        _log("Running GmatConsole pre-check...")
        val_result = validate_script(script_to_run, gmat_root)
        if not val_result["valid"]:
            _log("Validation FAILED")
            for e in val_result["errors"]:
                _log(f"  Line {e['line']}: {e['message']}")
        else:
            _log("Validation PASSED")
        result["_validation"] = {
            "valid": val_result["valid"],
            "errors": val_result["errors"],
            "status_line": val_result.get("status_line", ""),
        }

    if args.validate_only:
        result["success"] = result["_validation"]["valid"]
        result["stage"] = "validate"
        _print_result(result, _messages, args.format)
        _cleanup_template(tmp_script_path, args.no_cleanup)
        sys.exit(0 if result["success"] else 1)

    # --- Step 1: 初始化 GMAT ---
    init_result = init_gmat(gmat_root)
    if not init_result["success"]:
        result.update(init_result)
        _print_result(result, _messages, args.format)
        _cleanup_template(tmp_script_path, args.no_cleanup)
        sys.exit(1)

    # --- Step 2: 加载脚本 ---
    load_result = _with_suppressed_output(load_script, script_to_run, gmat_root)
    if not load_result["success"]:
        result.update(load_result)
        _print_result(result, _messages, args.format)
        _cleanup_template(tmp_script_path, args.no_cleanup)
        sys.exit(1)

    # --- Step 3: 执行 ---
    run_result = _with_suppressed_output(run_mission)
    if not run_result["success"]:
        result.update(run_result)
        result["stage"] = "run"
        _print_result(result, _messages, args.format)
        _cleanup_template(tmp_script_path, args.no_cleanup)
        sys.exit(1)

    result["summary"] = run_result.get("summary", "")

    # --- Step 4: 读取结果 ---
    obj_names = [n.strip() for n in args.objects.split(",") if n.strip()]
    result["objects"] = read_objects(obj_names)
    result["stage"] = "read"

    # --- Step 5: 解析报告文件 ---
    if args.report:
        report_full_path = os.path.join(output_dir, args.report)
        result["reports"] = parse_report_file(report_full_path)

    # 尝试自动查找 output_report.txt
    auto_report = os.path.join(output_dir, "output_report.txt")
    if os.path.exists(auto_report) and not args.report:
        result["reports"] = parse_report_file(auto_report)

    result["success"] = True
    result["_messages"] = _messages
    _print_result(result, _messages, args.format)

    # 清理临时文件
    _cleanup_template(tmp_script_path, args.no_cleanup)


def _print_result(result: dict, messages: list, fmt: str = "json"):
    """根据格式输出结果。"""
    if messages:
        result["_messages"] = messages

    try:
        if fmt == "csv":
            print(format_as_csv(result))
        elif fmt == "markdown":
            print(format_as_markdown(result))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except UnicodeEncodeError:
        # Windows GBK 终端回退：用 ASCII 安全模式输出
        if fmt == "markdown":
            print(format_as_markdown(result).encode("ascii", errors="replace").decode("ascii"))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=True))


def format_as_csv(result: dict) -> str:
    """将结果格式化为 CSV 字符串。"""
    lines = []

    # objects → key,value
    objects = result.get("objects", {})
    if objects:
        lines.append("section,key,value")
        for obj_name, props in objects.items():
            for prop, val in props.items():
                # CSV 安全：含逗号的值加引号
                val_str = str(val)
                if "," in val_str or "\n" in val_str:
                    val_str = f'"{val_str}"'
                lines.append(f"objects,{obj_name}.{prop},{val_str}")

    # reports → columns header + data rows
    reports = result.get("reports", {})
    if reports and "columns" in reports and "data" in reports:
        cols = reports["columns"]
        data_rows = reports["data"]
        if lines:
            lines.append("")  # 空行分隔
        lines.append("reports," + ",".join(str(c) for c in cols))
        for row in data_rows[:1000]:  # 最多 1000 行
            lines.append("reports," + ",".join(str(v) for v in row))
        if len(data_rows) > 1000:
            lines.append(f"reports,... ({len(data_rows)} rows total, showing first 1000)")

    return "\n".join(lines)


def format_as_markdown(result: dict) -> str:
    """将结果格式化为 Markdown 表格字符串。"""
    lines = []

    # Summary line
    success = result.get("success", False)
    stage = result.get("stage", "?")
    error = result.get("error", "")
    status = "[OK]" if success else "[FAIL]"
    lines.append(f"**Status**: {status} `success={success}` | stage: `{stage}`")
    if error:
        lines.append(f"**Error**: {error}")
    lines.append("")

    # objects → table
    objects = result.get("objects", {})
    if objects:
        lines.append("### Objects")
        lines.append("")
        # 收集所有属性名
        all_props = []
        for props in objects.values():
            for p in props:
                if p not in all_props:
                    all_props.append(p)
        # 优先显示常用参数
        priority = ["SMA", "ECC", "INC", "RAAN", "AOP", "TA", "RMAG", "VMAG",
                    "TotalMass", "DryMass", "X", "Y", "Z", "VX", "VY", "VZ"]
        ordered = [p for p in priority if p in all_props] + \
                  [p for p in all_props if p not in priority]
        # 表头
        header = "| Object | " + " | ".join(ordered) + " |"
        sep = "|---" * (len(ordered) + 1) + "|"
        lines.append(header)
        lines.append(sep)
        for obj_name, props in objects.items():
            vals = []
            for p in ordered:
                v = props.get(p, "")
                if isinstance(v, float):
                    vals.append(f"{v:.4g}")
                else:
                    vals.append(str(v))
            lines.append(f"| {obj_name} | " + " | ".join(vals) + " |")
        lines.append("")

    # reports → table (truncated)
    reports = result.get("reports", {})
    if reports and "columns" in reports and "data" in reports:
        cols = reports["columns"]
        data_rows = reports["data"]
        max_show = 50
        lines.append(f"### Report ({len(data_rows)} rows)")
        lines.append("")
        header = "| " + " | ".join(str(c) for c in cols) + " |"
        sep = "|---" * len(cols) + "|"
        lines.append(header)
        lines.append(sep)
        for row in data_rows[:max_show]:
            vals = [f"{v:.4g}" if isinstance(v, float) else str(v) for v in row]
            lines.append("| " + " | ".join(vals) + " |")
        if len(data_rows) > max_show:
            lines.append(f"| ... | (showing {max_show} of {len(data_rows)} rows) |")

    return "\n".join(lines)


def _cleanup_template(tmp_path: str, keep: bool = False):
    """清理模板替换产生的临时脚本文件"""
    if tmp_path and os.path.isfile(tmp_path) and not keep:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


if __name__ == "__main__":
    main()
