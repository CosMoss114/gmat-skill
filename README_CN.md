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
python assets/python_runner.py `
  --script assets/templates/simple_propagation.script `
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
python python_runner.py --script mission.script

# 读取指定对象的结果
python python_runner.py --script mission.script --objects "Sat,Sat2"

# 手动覆盖 GMAT 路径
python python_runner.py --script mission.script --gmat-root "D:\other-gmat"

# 指定自定义配置文件
python python_runner.py --script mission.script --config my_config.yaml
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
| 简单轨道传播（3 天） | `assets/templates/simple_propagation.script` |
| Hohmann 转移目标求解 | `assets/templates/impulsive_targeting.script` |
| 连续小推力推进 | `assets/templates/finite_burn.script` |

VS Code Chat 中的示例提示：

- *"仿真一颗 500km 高度的近地轨道卫星 3 天"*
- *"设计从 300km LEO 到 GEO 的 Hohmann 转移，计算所需 ΔV"*
- *"扫描 SMA 从 6600 到 7600 km，记录轨道周期变化"*
- *"模拟连续推力从 LEO 螺旋上升到 10000km，持续 10 天"*

## 文件结构

```
gmat-agent/
├── SKILL.md                    # Skill 定义（VS Code）
├── README.md                   # 英文文档
├── README_CN.md                # 本文件（中文文档）
└── assets/
    ├── system_prompt.txt       # LLM 系统提示词（GMAT 脚本语法参考）
    ├── python_runner.py        # Python 包装器: 加载 → 执行 → 读取结果
    ├── default_config.yaml     # 唯一配置入口
    └── templates/
        ├── simple_propagation.script
        ├── impulsive_targeting.script
        └── finite_burn.script
```

## 已验证的脚本规则

以下规则通过 GMAT Python API 实测验证：

1. ReportFile 配置行**不加分号** — `RF.Filename = 'out.txt'` 正确，`RF.Filename = 'out.txt';` 错误
2. `...` 是 `{}` 块内的**续行符**
3. ReportFile **自动写入**，无需显式 `Report RF;` 命令
4. `RF.Add` 只接受 **Cartesian** 参数（`Sat.EarthMJ2000Eq.X`），不接受 Keplerian（`Sat.Earth.SMA`）
5. 月球在 Python API 中名称为 **`Luna`**
6. 点质量引力源在 API 模式下可能导致轨道发散 — 推荐**纯地球引力**
7. 使用 **Keplerian** 状态初始化（`DisplayStateType = Keplerian`，SMA/ECC/INC）最简洁

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| `stage: "config"` 错误 | 检查 `default_config.yaml` 中的 `gmat_root` |
| `stage: "init"` 错误 | 确认 GMAT bin/ 下有 `gmatpy.pyd`。如需要先运行 `BuildApiStartupFile.py` |
| `stage: "load"` 错误 | 脚本语法错误。常见：ReportFile 行多了分号、`RF.Add` 参数名错误 |
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
