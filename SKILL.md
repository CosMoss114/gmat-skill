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

- **GMAT 路径配置**: 编辑 [`assets/default_config.yaml`](assets/default_config.yaml) 中的 `gmat_root` 字段，支持绝对路径和相对路径。也可通过 `GMAT_ROOT` 环境变量覆盖。
- 生成的 `.script` 文件写入 GMAT 的 `output/` 目录（由配置文件的 `output_dir` 指定）
- 执行后始终检查 `python_runner.py` 返回的 `success` 字段
- 如果 `success: false`，根据 `stage`、`error`、`details` 字段诊断问题并修正脚本
- `python_runner.py` 内置错误诊断：失败时自动提取行号级错误信息
- 使用 `--validate` / `--validate-only` 通过 GmatConsole 预检脚本语法
- 使用 `--var KEY=VALUE` 进行模板参数化替换（脚本中 `{{KEY}}` 占位符）
- **AI 执行仅用 Python API**：自动执行/迭代/验证阶段不启动 GMAT GUI（`GMAT.exe`），统一通过 `python_runner.py` 驱动
- 生成的 `.script` 文件是**标准 GMAT 格式**，可手动加载到 GMAT GUI 进行图形化仿真和 3D 可视化
- **GUI 分流**：当用户要求可视化/3D/动画时（分流树第1层），生成含 `OpenFramesInterface` 块的脚本，告知用户在 GUI 中打开
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

| 文件 | 用途 |
|------|------|
| `README.md` | 英文使用说明 |
| `README_CN.md` | 中文使用说明 |
| `assets/system_prompt.txt` | LLM 系统提示词 — GMAT 脚本语法完整参考 |
| `assets/default_config.yaml` | **唯一配置入口** — GMAT 路径、轨道默认值、物理常量 |
| `scripts/runner/python_runner.py` | Python 执行引擎 — 加载/执行/读取结果 + 程序化 API + -D 模板变量 + --validate |
| `scripts/fetch/fetch_oem.py` | OEM 数据获取 — 从 cmse.gov.cn 自动下载 CSS 轨道数据 |
| `scripts/analysis/parameter_scan.py` | 参数扫描 — 批量传播 + 汇总表格/趋势图 |
| `scripts/analysis/oem_reader.py` | OEM 解析器 — 解析 CCSDS OEM v2.0，Cartesian→Keplerian 解析计算 |
| `scripts/analysis/plot_altitude.py` | 高度绘图 — 近/远地点高度时间序列图 |
| `scripts/analysis/maneuver_detector.py` | 变轨检测 V0.3.0 — 10-bin趋势 + 脉冲/连续双模式 |
| `scripts/prediction/launch_window.py` | 发射窗口计算 — 空间站过顶预测（Kepler+J2 传播 + 方向滤波） |
| `scripts/test/smoke_test.py` | CI 冒烟测试 — 5 条核心管线验证 |
| `references/templates/*.script` | 4 个可运行脚本模板（含 {{PLACEHOLDER}} 参数化 + 默认值） |
| `references/samples/` | 19 个精选 GMAT 官方示例 + INDEX.md |
