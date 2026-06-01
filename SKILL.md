---
name: gmat-agent
user-invocable: true
description: "Use when the user wants to run GMAT (General Mission Analysis Tool) space mission simulations via natural language. Triggers on: GMAT, orbit, space mission, satellite, spacecraft, propagation, maneuver, trajectory, delta-V, Hohmann, GEO, LEO, 航天, 轨道, 卫星, 仿真, 变轨, 发射. Generates GMAT .script files, executes them via Python API, and returns structured results."
---

# GMAT Agent — 自然语言驱动航天任务仿真

本 Skill 通过 LLM 将自然语言描述转化为 GMAT 仿真脚本，自动执行并解析结果，实现完整闭环。

## 工作流

1. **理解用户需求** — 从自然语言中提取：任务类型（传播/变轨/参数扫描）、天体、轨道参数、时间跨度、输出要求
2. **生成 GMAT 脚本** — 参考 [`assets/system_prompt.txt`](assets/system_prompt.txt) 中的完整 GMAT 语法参考，生成正确的 `.script` 文件
3. **执行仿真** — 调用 [`scripts/runner/python_runner.py`](scripts/runner/python_runner.py) 通过 GMAT Python API 加载脚本并运行
4. **解读结果** — 解析返回的结构化 JSON，用自然语言向用户报告关键结果

## 关键约束

- **ASCII-Only 铁律**: `.script` 文件必须为纯 ASCII。不允许 em-dash（—）、弯引号（""''）、中文等非 ASCII 字符，即使出现在注释中也不行。这是 GMAT 解释器的硬限制。
- **Python 执行环境**: 推荐使用系统原生 shell 直接执行 Python 脚本（Windows: PowerShell, Linux/macOS: bash）。避免通过 `conda run` 包装执行 — conda 在中文 Windows 上会强制 GBK 编码，导致 GMAT 输出的 UTF-8 错误信息损坏，返回误导性错误。如果必须用 conda 环境，先 `conda activate` 再直接 `python script.py`。
- **GMAT 路径配置**: 编辑 [`assets/default_config.yaml`](assets/default_config.yaml) 中的 `gmat_root` 字段，支持绝对路径和相对路径。也可通过 `GMAT_ROOT` 环境变量覆盖。
- **官方帮助文档**: GMAT 发行版自带完整教程，路径为 `<GMAT_ROOT>/docs/help/`（含 HTML 和 PDF 格式）。遇到不确定的脚本语法、对象字段、报错信息时，可在此目录下搜索关键词获取官方说明。
- 生成的 `.script` 文件写入 GMAT 的 `output/` 目录（由配置文件的 `output_dir` 指定）
- 执行后始终检查 `python_runner.py` 返回的 `success` 字段
- 如果 `success: false`，根据 `stage`、`error`、`details` 字段诊断问题并修正脚本
- `python_runner.py` 内置错误诊断：失败时自动提取行号级错误信息，**已内置 ASCII 预检**，非 ASCII 字符会被立即捕获并报告
- 使用 `--validate` / `--validate-only` 通过 GmatConsole 预检脚本语法
- 使用 `--var KEY=VALUE` 进行模板参数化替换（脚本中 `{{KEY}}` 占位符）
- **AI 执行仅用 Python API**：自动执行/迭代/验证阶段不启动 GMAT GUI（`GMAT.exe`），统一通过 `python_runner.py` 驱动
- 生成的 `.script` 文件是**标准 GMAT 格式**，可手动加载到 GMAT GUI 进行图形化仿真和 3D 可视化
- **GUI 分流**：当用户要求可视化/3D/动画时（分流树第1层），生成含 `OpenFramesInterface` 块的脚本，告知用户在 GUI 中打开
- **API/GUI 脚本分离**: Python API 不支持加载 GUI 独有对象 (`OpenFramesInterface`, `GroundTrackPlot`, `OrbitView`, `XYPlot`)。始终生成两份脚本——API 版（`*_api.script`，纯计算）用于迭代验证，GUI 版（`*.script`，含可视化块）用于最终 3D 查看
- **复杂任务工作流**：先通过 Python API 迭代验证（快速、可自动纠错），通过后提供含 `OpenFramesInterface` 的 GUI 版本供用户可视化确认
**参数扫描**:
- 当用户需要批量扫描轨道参数（SMA范围/倾角网格/质量扫描）时：使用 `parameter_scan.py`
- 支持 `-p KEY=START:END:STEP` 范围和 `-p KEY=VALUE` 固定值
- 自动汇总为表格，可选 CSV/JSON/趋势图输出

**OEM 数据获取与轨道分析**:
- 当用户需要最新的 CSS 轨道数据时：使用 `scripts/fetch/fetch_oem.py` 自动下载
- 当用户提供 OEM 文件时：使用 `oem_reader.py` 解析，`plot_altitude.py` 可视化，`maneuver_detector.py` 检测变轨
- 当用户询问神舟/天舟发射窗口时：使用 `launch_window.py`，指定酒泉/文昌站和时间

## 已验证的 GMAT 脚本语法（重要）

1. **所有赋值行以分号结尾**: `RF.Filename = 'out.txt';` 正确，不加分号导致解析错误
2. **续行符 `...`**: 在 `{}` 块内跨行时必须使用 `...`
3. **ReportFile 自动写入**: 不含 `Report RF;` 命令，任务结束时自动生成
4. **ReportFile.Add 只接受 Cartesian 参数**: `Sat.EarthMJ2000Eq.X` 有效，`Sat.Earth.SMA` 无效
5. **月球体名**: Python API 中使用 `Luna` 而非 `Moon`
6. **DifferentialCorrector 字段名**: `MaximumIterations`，不是 `MaxIterations`
7. **ChemicalThruster.C1**: 推力系数（N），不是 Isp。`GravitationalAccel` 用 SI 单位：`9.81` m/s²
8. **ChemicalTank.PressureModel**: `PressureModel = PressureRegulated;` 不是 `PressureRegulated = true`
9. **MixRatio 数组大小**: 必须匹配贮箱数量，一个贮箱用 `[1]`
10. **Target/Vary/Achieve 语法**: `Vary 'desc' DC(var=val, {opts})` — DC 在引号外侧
11. **ASCII-Only**: `.script` 文件必须纯 ASCII — em-dash、中文标点、弯引号均导致解析失败
12. **JacchiaRoberts 拼写**: 正确拼写为 `JacchiaRoberts`（非 `JacobiaRoberts`），且 R2026a 语法为 `FM.Drag.AtmosphereModel = JacchiaRoberts;`
13. **SPADSRPArea**: R2026a 不支持此字段
14. **SolarRadiationPressure**: R2026a 中 `FM.SolarRadiationPressure = On` 已废弃，会报错
15. **轨道衰减必须差分**: 单次"有阻力"仿真无法可靠判断衰减（J₂ 周期变化 >> 阻力效应），需有/无阻力对比
16. **VNB 参考系限制**: 高度偏心轨道 (ECC > 0.5) 远地点 VNB 帧数值不稳定，会导致轨道双曲化。此时应使用 `CoordinateSystem = EarthMJ2000Eq; Axes = MJ2000Eq;` 惯性系 ImpulsiveBurn
17. **Axes 字段值**: 仅接受 `MJ2000Eq`（不含 "Earth" 前缀），`EarthMJ2000Eq` 用于 `CoordinateSystem`
18. **ImpulsiveBurn 惯性系**: 在 EarthMJ2000Eq 下 Element1/2/3 分别为 ΔV_X/ΔV_Y/ΔV_Z 惯性分量
19. **Target 系统限制**: ≥4 耦合变量时 Jacobian 易奇异；界约束过紧会锁死求解器；高 ECC 下避免 `Propagate to Periapsis` 停止条件
20. **多冲量策略**: 强耦合问题用分步 Target（每步独立求解、固化后继续）或逐步执行（GMAT 传播 → 读实态 → Python 算 ΔV → GMAT ImpulsiveBurn 施加）
21. **节点变面 (Z=0)**: 消除倾角的机动必须在 Z=0 节点处执行，不可在远地点。节点处 |v| 足够大，VNB 数值稳定；远地点 |v| 极小导致 VNB 不可靠 → 轨道双曲化
22. **Target 分块模式**: 多冲量任务拆为独立 Target 块（每块≤2 Vary+≤2 Achieve），参照 Ex_GEOTransfer.script。单块 ≥4 变量 Jacobian 奇异
23. **OFI 字段限制**: OpenFramesInterface 不接受 `DataCollectFrequency`/`UpdatePlotFrequency`/`OpenFrameName`。多边形效应靠减小步长 (10s) 解决
24. **GEO 双视图标配**: GUI 脚本带 OFI_Inertial (EarthMJ2000Eq) + OFI_Fixed (EarthFixed) + GroundTrackPlot
25. **MaxStep 限制**: Prop.MaxStep ≤ 600s，86400s(1天) 可能导致积分跳过关键事件
26. **GmatFunction 外部文件**: R2026a 不支持 `.script` 内联 `function` 关键字。函数体必须写在独立 `.gmf` 文件中，通过 `FunctionPath = '../userfunctions/gmat/xxx.gmf'` 引用。适用场景：同一任务中多次调用的复用模块

### 变轨参考系决策树

```
需要变轨？
├─ ECC < 0.3 (近圆轨道) → VNB 安全，直接用
├─ ECC > 0.5 + 变面需求 → 在 Z=0 节点执行 (VNB)，不可在远地点
│   └─ 参照 Ex_GEOTransfer.script 三 Target 块模式
├─ ECC > 0.5 + 仅变速 → 若远地点 |v|>1 km/s → VNB 可用
│                     → 若远地点 |v|<0.5 km/s → EarthMJ2000Eq 惯性系
└─ 不确定 → 优先用节点 (Z=0) 或分步 Target，避免单块多变量
```

### 轨道衰减仿真策略

在 ~380 km 高度：
- 纯阻力导致 SMA 衰减 ~0.5 km/周
- J₂ 引力摄动导致 SMA 周期振荡 ~5-6 km/周
- **必须差分**: 生成两份脚本 → 分别执行 → 对比差值
- 低阶重力场 (Degree=0) 比高阶更能凸显阻力效应

## 典型使用示例

**简单传播**:
> "仿真一颗 500km 圆轨道卫星 3 天，输出位置速度"

**变轨任务**:
> "设计 Hohmann 转移从 300km LEO 到 GEO，计算需要的 delta-V"

**参数扫描**:
> "扫描倾角从 0 到 90 度对轨道寿命的影响"

**中国空间站**:
> "分析这个 OEM 文件的轨道变化趋势"（→ `oem_reader.py` + `plot_altitude.py`）

**发射窗口**:
> "神舟23号从酒泉发射，空间站过顶窗口是什么？"（→ `launch_window.py -s Jiuquan`）

## 文件说明

详见 [README.md](README.md)（英文）或 [README_CN.md](README_CN.md)（中文）。
