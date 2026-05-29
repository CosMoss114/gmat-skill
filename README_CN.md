# GMAT Agent Skill

[GMAT](https://sourceforge.net/projects/gmat/)（通用任务分析工具）的自然语言接口 — 用中文或英文描述航天任务，直接获得仿真结果。

> **Language**: [English Documentation](README.md)

---

> **注意**：本项目仍处于早期开发阶段，正在持续迭代中。如发现问题，欢迎[提交 Issue](https://github.com) 或直接联系作者。有能力者亦可提交 Pull Request 参与贡献。

## 概述

GMAT Agent 在自然语言与 GMAT 脚本语言之间架起桥梁。你说想要什么 —「仿真一颗近地轨道卫星 3 天」— Agent 自动生成正确的 GMAT 脚本、执行并返回结构化结果。

```
用户: "设计一个从 300km LEO 到 GEO 的 Hohmann 转移"
  → LLM 生成 .script 文件
  → python_runner.py 通过 GMAT Python API 执行
  → 返回: ΔV、末轨道参数、报告数据
```

## 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| GMAT | R2020a 或更高 | 完整安装（含 bin/、data/、plugins/） |
| Python | 3.9+ | 需与 GMAT 编译时的 Python 版本一致 |
| GMAT Python API | 内置 | `gmatpy` 模块，位于 GMAT bin/ 目录 |

## 快速开始

### 1. 配置 GMAT 路径

编辑 `assets/default_config.yaml`，**只改一行**：

```yaml
gmat_root: "D:\\你的路径\\gmat-win-R2026a"   # ← 你的 GMAT 安装目录
```

或设置 `GMAT_ROOT` 环境变量（可选覆盖）。

### 2. 运行测试

```powershell
python scripts/runner/python_runner.py `
  --script references/templates/simple_propagation.script `
  --objects Sat
```

预期输出：
```json
{
  "success": true,
  "stage": "read",
  "objects": {
    "Sat": {
      "SMA": 7094.91,
      "ECC": 0.011,
      "INC": 44.94,
      "RMAG": 7027.32
    }
  }
}
```

### 3. 在 VS Code 中使用

在聊天中输入 `/gmat-agent` 后跟任务描述，例如：

> `/gmat-agent 仿真一颗 500km 圆轨道卫星 7 天，输出位置和速度`

Agent 会查阅 `assets/system_prompt.txt`（完整 GMAT 脚本参考），生成正确的 `.script` 文件，执行并报告结果。

## 配置

所有路径统一在 **`assets/default_config.yaml`** 中管理 — 唯一的配置入口：

```yaml
# === GMAT 安装路径 ===
# 改为你自己的 GMAT 根目录（包含 bin/、data/、output/ 的顶层目录）
gmat_root: "e:\\GMAT\\GMATdev\\gmat-win-R2026a"

# 以下通常无需修改（自动从 gmat_root 推导）
gmat_bin: "{gmat_root}\\bin"
output_dir: "{gmat_root}\\output"
```

支持**绝对路径**和**相对路径**。相对路径相对于 `assets/` 目录解析。

### 路径解析优先级

1. `--gmat-root` 命令行参数（显式覆盖）
2. `GMAT_ROOT` 环境变量
3. `default_config.yaml` 中的 `gmat_root`

## 使用方式

### Python Runner 命令行

```powershell
# 最简用法（自动读取配置）
python scripts/runner/python_runner.py --script mission.script

# 读取指定对象的结果
python scripts/runner/python_runner.py --script mission.script --objects "Sat,Sat2"

# 手动覆盖 GMAT 路径
python scripts/runner/python_runner.py --script mission.script --gmat-root "D:\other-gmat"

# 指定自定义配置文件
python scripts/runner/python_runner.py --script mission.script --config my_config.yaml
```

### 输出格式

```json
{
  "success": true,
  "stage": "read",
  "error": "",
  "summary": "...",
  "objects": {
    "Sat": { "SMA": 7094.9, "ECC": 0.011, "INC": 44.9 }
  },
  "reports": {
    "columns": ["Sat.X", "Sat.Y", "Sat.Z"],
    "data": [[7100.0, 0.0, 1300.0], ...],
    "summary": { "num_rows": 1948 }
  }
}
```

错误阶段：`config` → `init` → `load` → `run` → `read`。当 `success: false` 时，查看 `stage` 和 `error` 字段定位问题。

## GUI 兼容性

本 Skill 生成的所有脚本均为**标准 GMAT `.script` 格式**，与 GMAT 图形界面完全兼容。

- 打开 `GMAT.exe` → **File → Open** → 选择生成的 `.script` 文件
- 点击**运行按钮**（▶）即可执行，并获得完整的 3D 可视化
- 与 Python API 不同，GUI 支持 `OpenFramesInterface` 进行交互式 3D 轨道显示
- 脚本同样可在 `GmatConsole.exe`（命令行模式）中运行

**如需 3D 可视化**，在脚本的 `BeginMissionSequence` 之前插入：

```
Create OpenFramesInterface OFI;
OFI.SolverIterations = Current;
OFI.UpperLeft = [ 0 0 ];
OFI.Size = [ 0.6 0.5 ];
OFI.Maximized = false;
OFI.Add = {Sat, Earth};
OFI.CoordinateSystem = EarthMJ2000Eq;
OFI.DrawObject = [ true true ];
OFI.DrawLabel = [ true true ];
OFI.Axes = On;
OFI.EnableStars = On;
OFI.ShowPlot = true;
```

> **注意**: GMAT `.script` 文件必须使用 **纯 ASCII 字符**。注释中的中文、全角标点（如 `—` `"` `"`）会导致解析错误。

## 使用示例

| 任务描述 | 模板文件 |
|----------|----------|
| 简单轨道传播（3 天） | `references/templates/simple_propagation.script` |
| 参数化传播（命令行可调） | `references/templates/parameterized_propagation.script` |
| Hohmann 转移目标求解 | `references/templates/impulsive_targeting.script` |
| 连续小推力推进 | `references/templates/finite_burn.script` |

另有 19 个精选 GMAT 官方示例 — 参见 [`references/samples/INDEX.md`](references/samples/INDEX.md)。

VS Code Chat 中的示例提示：

- *"仿真一颗 500km 高度的近地轨道卫星 3 天"*
- *"设计从 300km LEO 到 GEO 的 Hohmann 转移，计算所需 ΔV"*
- *"扫描 SMA 从 6600 到 7600 km，记录轨道周期变化"*
- *"模拟连续推力从 LEO 螺旋上升到 10000km，持续 10 天"*

## Python Runner — 完整功能

`python_runner.py` 现已支持三项额外能力：

### 模板参数化

脚本中使用 `{{KEY}}` 占位符，通过 `--var` / `-D` 传入：

```powershell
python scripts/runner/python_runner.py --script references/templates/parameterized_propagation.script `
  -D SMA=7200 -D INC=60 -D DURATION=7 --objects Sat
```

### 脚本校验

执行前通过 `GmatConsole` 预检语法：

```powershell
# 仅校验
python scripts/runner/python_runner.py --script test.script --validate-only

# 校验 + 执行
python scripts/runner/python_runner.py --script test.script --validate --objects Sat
```

### 错误诊断

`load_script()` 或 `run_mission()` 失败时，自动从 `GmatLog.txt` 提取行号级错误；日志为空时降级至 `GmatConsole` 获取带行号的详细诊断。

## OEM 管线 — 中国空间站轨道分析

三个工具处理 CCSDS OEM v2.0 格式星历：

| 工具 | 用途 |
|------|------|
| `oem_reader.py` | 解析 OEM → Cartesian → Keplerian（纯 numpy，不依赖 GMAT） |
| `plot_altitude.py` | 三面板高度图：近/远地点、SMA+趋势、偏心率 |
| `maneuver_detector.py` | 轨道周期平滑 SMA 跳跃检测，已滤除 J2 假阳性 |

```powershell
python scripts/analysis/oem_reader.py CSS_OEM.dat
python scripts/analysis/plot_altitude.py CSS_OEM.dat -o altitude.png --step 4
python scripts/analysis/maneuver_detector.py CSS_OEM.dat --step 200 --threshold 5.0 --window 24
```

## 发射窗口预测

`launch_window.py` 计算空间站过顶发射窗口（神舟/天舟任务）：

- **算法**：Kepler+J2 解析反向传播 → EME2000→ECEF→仰角 → 过顶检测
- **方向滤波**：仅 NW→SE 降轨通过（落区安全 — 东南向海域）
- **默认阈值**：60° 峰值仰角
- **站点**：酒泉（40.96°N, 100.29°E）和文昌（19.32°N, 109.80°E）

```powershell
# 神舟（酒泉）
python scripts/prediction/launch_window.py CSS_OEM.dat -s Jiuquan --t0 "2026-05-24T23:08:36+08:00" -e 60

# 天舟（文昌）
python scripts/prediction/launch_window.py CSS_OEM.dat -s Wenchang -e 60 -w 24
```

**验证**：神舟23号（2026年5月24日 23:08 BJT）唯一有效窗口为降轨过顶，峰值 79.1°，AOS 23:06 BJT，与实际 T0 误差 2 分钟以内。

## 文件结构

```
gmat-agent/
├── SKILL.md                    # Skill 定义（VS Code）
├── README.md                   # 英文文档
├── README_CN.md                # 本文件（中文文档）
├── gmat-triage.instructions.md # 分流决策树（5 层路由）
├── assets/                     # 仅配置与提示词
│   ├── system_prompt.txt       # LLM 系统提示词（GMAT 脚本语法参考）
│   └── default_config.yaml     # 唯一配置入口
├── scripts/                    # Python 工具链
│   ├── runner/
│   │   └── python_runner.py    # 核心引擎: 加载 → 执行 → 读取结果
│   ├── analysis/
│   │   ├── oem_reader.py       # OEM 解析器: CCSDS OEM v2.0 → Keplerian
│   │   ├── plot_altitude.py    # 高度绘图: 近/远地点时间序列
│   │   └── maneuver_detector.py # 变轨检测: 轨道周期平滑 SMA 跳跃检测
│   └── prediction/
│       └── launch_window.py    # 发射窗口计算: 空间站过顶预测
└── references/                 # 参考脚本
    ├── templates/              # 4 个可运行模板
    │   ├── simple_propagation.script
    │   ├── parameterized_propagation.script  # {{KEY}} 模板占位符
    │   ├── impulsive_targeting.script
    │   └── finite_burn.script
    └── samples/                # 19 个精选 GMAT 官方示例
        ├── INDEX.md
        ├── propagation/        # 轨道传播（6）
        ├── maneuver-transfer/  # 变轨与转移（5）
        ├── navigation/         # 导航与估计（3）
        ├── attitude/           # 姿态（3）
        └── optimal-control/    # 最优控制（2）
```

## 已验证的脚本规则

以下规则通过 GMAT Python API 与 GmatConsole 实测验证：

1. **所有赋值行以分号结尾** — 包括 ReportFile。`RF.Filename = 'out.txt';` 正确，不带分号导致解析错误
2. `...` 是 `{}` 块内的**续行符**
3. ReportFile **自动写入**，无需显式 `Report RF;` 命令
4. `RF.Add` 只接受 **Cartesian** 参数（`Sat.EarthMJ2000Eq.X`），不接受 Keplerian（`Sat.Earth.SMA`）
5. 月球在 Python API 中名称为 **`Luna`**
6. `DifferentialCorrector` 字段：**`MaximumIterations`** 而非 `MaxIterations`
7. `ChemicalThruster.C1` 是**推力系数 (N)**，不是 Isp。`GravitationalAccel` 用 **SI 单位 (m/s²)**：填 `9.81` 而非 `0.00981`
8. `ChemicalTank.PressureModel = PressureRegulated;`（不是 `PressureRegulated = true`）
9. `MixRatio` 数组大小必须匹配贮箱数：一个贮箱用 `[1]`
10. Target/Vary/Achieve 语法：`Vary '描述' DC(变量=值, {选项})` — DC 在引号外侧

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| `stage: "config"` 错误 | 检查 `default_config.yaml` 中的 `gmat_root` |
| `stage: "init"` 错误 | 确认 GMAT bin/ 下有 `gmatpy.pyd`。如需要先运行 `BuildApiStartupFile.py` |
| `stage: "load"` 错误 | 脚本语法错误。常见：ReportFile 行缺少分号、`RF.Add` 参数名错误 |
| `stage: "run"` 错误 | 物理配置问题。检查：点质量是否正确？`DateFormat` 是否在 `Epoch` 之前？ |
| 轨道发散（双曲线） | 移除 `PointMasses`，仅用地球中心引力 |
| `ModuleNotFoundError: gmatpy` | 将 GMAT `bin/` 加入 `PYTHONPATH`，或从能找到 gmatpy 的目录运行 |

## 已知限制

- **MVP 范围**：传播 + 机动 + 目标求解。不含轨道确定、不含实时可视化
- **仅 Python API**：不使用 GMAT GUI（`GMAT.exe`），不直接调用 `GmatConsole.exe`
- **无自动迭代循环**：LLM 每次生成一个脚本，多轮优化需手动进行
- **ReportFile 参数**：`RF.Add` 仅支持 Cartesian 参数。Keplerian 根数需通过 `GetRuntimeObject().GetNumber()` 读取
- **第三天体引力**：点质量（太阳、月球）在 API 模式下可能有问题

## 许可证

本 Skill 与 GMAT 采用相同许可证（Apache 2.0）。
