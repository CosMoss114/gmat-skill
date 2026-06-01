# Changelog

本文档记录 GMAT Agent Skill 从首个版本至今的所有变更，包括新增功能、Bug 修复、架构调整和文档更新。

## [v0.1.5] — 2026-06-01

### Bug 修复 — Scene1: CSS 轨道衰减 (CherryStudio 实测)

基于 CSS 轨道衰减仿真端到端测试的 22 次失败分析，修复以下问题：

- **`python_runner.py` — subprocess 编码修复**: `validate_script()` 的 `subprocess.run` 改用二进制模式 + 手动 `decode("utf-8", errors="replace")`，解决 Windows GBK 终端下错误信息被编码损坏的问题。此前 GmatConsole 输出的真实错误（如 Non-ASCII）被 GBK 解码吞没，返回误导性 traceback。
- **`python_runner.py` — ASCII 预检**: 新增 `_check_script_ascii()` 函数；`load_script()` 和 `validate_script()` 在加载前自动检查非 ASCII 字符，直接报告行号、字符和 Unicode codepoint，避免模糊的 "Non-ASCII character" 错误。
- **`system_prompt.txt` — ForceModel 语法更新 (R2026a)**: `FM.Drag` 字段名、`JacchiaRoberts` 拼写、`SolarRadiationPressure`/`SPADSRPArea` 废弃标记
- **`system_prompt.txt` — ASCII-Only 铁律**: 在硬规则中提升为第 0 规则，新增版本兼容矩阵
- **`system_prompt.txt` — 差分仿真指南**: 新增轨道衰减必须使用有/无阻力差分对比的策略说明
- **`SKILL.md`**: 新增 ASCII-Only、R2026a 语法变更 (规则 11-14)、差分仿真策略 (规则 15)
- **执行环境指南**: `SKILL.md` 关键约束新增 "Python 执行环境"；`DEVGUIDE.md` 新增 "已知问题与故障排除" 节

### Bug 修复 — Scene2: Hohmann 转移 (CherryStudio 实测)

基于 Hohmann 转移仿真 (300km LEO → GEO 100°E) 测试的 3 次失败分析，修复以下问题：

- **`python_runner.py` — 非 Spacecraft 对象参数读取**: `COMMON_PARAMETERS` 扩展为包含 ImpulsiveBurn (`Element1-3`)、ChemicalThruster (`C1-3`)、DifferentialCorrector (`MaximumIterations`) 的数值参数。`read_object()` 现在自动尝试所有参数并跳过不适用的，新增 `_type` 字段推断对象类型。
- **`system_prompt.txt` — API/GUI 对象兼容性矩阵**: 新增 Python API 不支持 `OpenFramesInterface`/`GroundTrackPlot`/`OrbitView`/`XYPlot` 的明确说明，以及 API/GUI 双脚本分离策略。
- **`SKILL.md` — API/GUI 脚本分离**: 关键约束新增分离策略条目

### Bug 修复 — Scene3: 超同步转移 (CherryStudio 实测)

基于超同步转移仿真 (400km/46° LEO → GEO 40°E) 的 28 次失败分析，修复以下问题：

- **`system_prompt.txt` — ImpulsiveBurn 参考系完整指南**: 重写 ImpulsiveBurn 章节，新增 VNB 参考系限制说明（ECC > 0.5 远地点不可靠）、EarthMJ2000Eq 惯性系完整用法（CoordinateSystem/Axes 字段正确值、ΔV 计算模式）、参考系选择速查表
- **`system_prompt.txt` — DifferentialCorrector 限制**: 新增 Target 系统 4 条限制（Jacobian 奇异、界约束锁死、高 ECC 停止条件、变量数上限）+ 使用检查清单
- **`system_prompt.txt` — 多冲量策略**: 新增分步 Target 和逐步执行两种替代模式，覆盖 ≥3 冲量强耦合场景
- **`SKILL.md`**: 新增规则 16-20 (VNB 限制、Axes 字段、惯性系 ImpulsiveBurn、Target 限制、多冲量策略)

### 实测验证 — 超同步转移 (内部端到端测试)

基于 Ex_GEOTransfer.script 官方模式，成功跑通完整超同步转移 (400km/46°→GEO)：

- **节点变面策略验证**: 确认在 Z=0 节点处用 VNB 执行变面机动完全可靠（3 iter 收敛），远地点变面导致 ECC→1.47 双曲逃逸
- **三 Target 块模式**: TOI(ΔV=3.005) + GOI(ΔV=0.620, V+N) + MOI(ΔV=0.886) 均在 3-4 次迭代内收敛，总 ΔV=4.511 km/s
- **`system_prompt.txt` — 节点变面策略**: 新增完整决策逻辑 + 正确/错误模式对比
- **`system_prompt.txt` — 可视化字段参考**: 新增 OFI/GTP 合法字段清单（OFI 不支持 DataCollectFrequency 等字段）+ 多边形效应消除方法
- **`system_prompt.txt` — 常见错误**: 新增 22-27 号错误（VNB 高 ECC、Target 多变量、变面位置、OFI 非法字段、MaxStep 过大、节点跳过）
- **`system_prompt.txt` — 脚本生成规则**: 新增 12-15 号规则（分块 Target、节点变面、GEO 双视图、步长选择）
- **`SKILL.md`**: 新增规则 21-25 + 变轨参考系决策树（4 分支）
- **`DEVGUIDE.md`**: 新增 3 个故障排除条目（VNB 高 ECC、OFI 多边形效应、OFI 非法字段）

### 新增 — GmatFunction 集成

- **调研**: 确认 GMAT R2026a 不支持 `.script` 内联 `function` 关键字，必须使用外部 `.gmf` 文件 + `FunctionPath` 引用。GmatConsole 和 Python API 均兼容
- **`system_prompt.txt` — GmatFunction 语法参考**: 新增完整章节（定义 `.gmf` 文件、调用语法、输入/输出类型、Global 声明、使用场景决策表）
- **`system_prompt.txt` — 错误 28**: 新增"内联 function 关键字"错误
- **`references/templates/HohmannTarget.gmf`**: Hohmann 转移函数模板（Target 块封装）
- **`references/templates/gmat_function_hohmann.script`**: 调用 GmatFunction 的主脚本模板
- **`SKILL.md`**: 新增规则 26（GmatFunction 外部文件）

## [v0.1.4] — 2026-05-31

### 变轨检测 V0.3.0 — 双模式 + 趋势分析

- **算法重写**: 从轨道周期平滑 + 阈值检测 → 10-bin 粗粒化趋势分析
  - 每 bin ~17 小时，覆盖 ~11 个 J2 周期，自然消除 J2 ±7 km 振荡
- **双模式检测**: 脉冲（化学推力器）+ 连续（霍尔/电推）
- **dV 估计**: vis-viva 圆轨道近似；连续推力加速度 + 持续时间诊断

### OEM 数据自动获取

- **`scripts/fetch/fetch_oem.py`**: cmse.gov.cn 全量下载 + 文件名去重 + 自动解压
  - `--dry-run` 预览 / `--json` 输出 / 数据存储 `data/oem/`

### 参数扫描自动化

- **`scripts/analysis/parameter_scan.py`**: `-p SMA=6600:7600:200` 范围扫描 + 多参数网格
  - 终端表格 / `--csv` / `--json-output` / `--plot` (matplotlib)

### 模板默认值

- `parameterized_propagation.script`: `%% Defaults:` 注释行 + runner 自动解析填充

### 输出格式扩展

- **`python_runner.py`**: `--format csv|markdown`, 默认 `--format json` 向后兼容

### CI 验证脚本

- **`scripts/test/smoke_test.py`**: 简单传播 / 参数化传播 / 校验 / 错误诊断 / OEM 解析

### 文档

- README/README_CN: 路径更新到 V0.1.3 三层结构，新增 OEM 获取、参数扫描、测试章节
- AGENTS.md: GMAT Python API 章节 + 15 条脚本语法规则
- DEVGUIDE.md: V0.1.4 短期目标全部标记完成
- SKILL.md: 文件结构引用更新

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
