# Changelog

本文档记录 GMAT Agent Skill 从首个版本至今的所有变更，包括新增功能、Bug 修复、架构调整和文档更新。

## [v0.1.3] — 2026-05-29

### 架构重组

- **三层目录结构**: 将扁平 `assets/` 重组为 `assets/`（配置+提示词）、`scripts/`（工具链）、`references/`（参考脚本）
- `scripts/runner/` — 核心执行引擎 (`python_runner.py`)
- `scripts/analysis/` — OEM 分析工具 (`oem_reader.py`, `plot_altitude.py`, `maneuver_detector.py`)
- `scripts/prediction/` — 发射窗口预测 (`launch_window.py`)
- `references/templates/` — 4 个可运行脚本模板
- `references/samples/` — 19 个精选 GMAT 官方示例（按 propagation / maneuver-transfer / navigation / attitude / optimal-control 分类）
- `gmat-triage.instructions.md` — 5 层分流决策树（GUI需求 → 空间范围 → 任务类型 → 输出要求 → 歧义检测）

### 新增

- **分流决策树**: 按 GUI 需求、空间范围（地球/地月系/行星际）、任务类型、输出要求逐层分析用户需求；地月系和行星际标记为预留架构
- **精选官方示例**: 19 个 GMAT 官方脚本按任务类型分类，含 `INDEX.md` 索引
- **可部署性修复**: 分流文件从 `.github/instructions/` 移入 skill 打包目录内

### 修复

- `python_runner.py`: 修正 `default_config.yaml` 路径解析（适配新 `scripts/runner/` 位置）
- `launch_window.py`: 修正跨目录 `oem_reader` import（添加 `../analysis` 到 sys.path）
- README.md / README_CN.md: 修正 Troubleshooting 中分号描述（"多了分号" → "缺少分号"）

### 文档

- 全面更新 `SKILL.md`、`README.md`、`README_CN.md`、`AGENTS.md` 中的路径引用
- `references/samples/INDEX.md` — 精选脚本索引与使用说明

---

## [v0.1.2] — 2026-05-28

### 新增

- **模板参数化**: `--var KEY=VALUE` / `-D` 命令行支持，脚本中使用 `{{KEY}}` 占位符
- **脚本校验**: `--validate` / `--validate-only` 通过 GmatConsole 预检语法
- **OEM 管线**: CCSDS OEM v2.0 轨道数据的完整分析工具链
  - `oem_reader.py` — OEM 解析器 + Cartesian→Keplerian 批量转换
  - `plot_altitude.py` — 3 面板高度时间序列图（近/远地点、SMA+趋势、偏心率）
  - `maneuver_detector.py` — 轨道周期平滑 SMA 跳跃检测（已滤除 J2 假阳性）
- **发射窗口预测**: `launch_window.py` — Kepler+J2 解析传播 + EME2000→ECEF 坐标转换
  - NW→SE 降轨方向滤波（落区安全约束）
  - 酒泉/文昌双站支持
  - 神舟23号（2026-05-24）验证：窗口预测与 T0 误差 2 分钟以内
- **错误诊断增强**: 失败时自动从 GmatLog.txt 提取行号级错误；日志为空时降级至 GmatConsole
- **新增模板**: `parameterized_propagation.script`（支持 CLI 参数覆盖的模板脚本）
- LICENSE 文件 (Apache 2.0)

### 修复

- **脚本语法规则纠正**（通过 GmatConsole 实测验证）:
  - 所有赋值行（含 ReportFile）必须以分号结尾（之前误认为不需要）
  - `MaximumIterations` 而非 `MaxIterations`
  - `ChemicalThruster.C1` 是推力系数（N），`GravitationalAccel` 用 SI 单位 9.81
  - `PressureModel = PressureRegulated;` 而非 `PressureRegulated = true`
  - `MixRatio` 数组大小匹配贮箱数量
  - Target/Vary/Achieve: DC 在引号外侧
- `system_prompt.txt`: 11 条语法规则修正
- `python_runner.py`: 抑制 GMAT stdout 输出，保持 JSON 输出干净

---

## [v0.1.1] — 2026-05-25

### 新增

- **OEM 支持**: `oem_reader.py` — CCSDS OEM v2.0 文件解析器，支持 Cartesian→Keplerian 解析转换（纯 numpy，不依赖 GMAT API）
- **高度可视化**: `plot_altitude.py` — 近/远地点高度时间序列图（matplotlib）
- **变轨检测（演示版）**: `maneuver_detector.py` — 基于采样的 SMA 跳跃检测 + 二分搜索定位
- **程序化 API**: `python_runner.py` 新增 `create_and_read_state()` 函数，无需 `.script` 文件即可进行 Cartesian→Keplerian 转换

### 文档

- 更新 `SKILL.md`、`README.md`、`README_CN.md`
- `system_prompt.txt` 新增 OEM 工作流规则

---

## [v0.1.0] — 2026-05-23

### 首次发布

- **LLM 系统提示词** (`system_prompt.txt`): 完整 GMAT 脚本语法参考，覆盖 Spacecraft、ForceModel、Propagator、ImpulsiveBurn、FiniteBurn、DifferentialCorrector、ReportFile 等全部资源类型和命令
- **Python 执行引擎** (`python_runner.py`): init→load→run→read 完整闭环
  - GMAT Python API 集成（`gmatpy` 模块）
  - 结构化 JSON 输出（`success`、`stage`、`objects`、`reports`）
  - 错误阶段标记（config / init / load / run / read）
- **统一配置** (`default_config.yaml`): GMAT 路径、默认轨道参数、默认航天器参数；支持 `GMAT_ROOT` 环境变量和 `--gmat-root` CLI 覆盖
- **3 个已验证脚本模板**:
  - `simple_propagation.script` — 简单 LEO 3 天传播
  - `impulsive_targeting.script` — Hohmann 转移（DifferentialCorrector 求解 ΔV）
  - `finite_burn.script` — 有限推力（ChemicalTank + ChemicalThruster）
- **3D 可视化**兼容: 支持 `OpenFramesInterface` 块，脚本可在 GMAT GUI 中查看
- **双语文档**: `README.md`（英文）、`README_CN.md`（中文）、`SKILL.md`（VS Code Skill 定义）
- 实测验证的关键 GMAT 脚本语法规则 (7 条)
