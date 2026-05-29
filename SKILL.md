---
name: gmat-agent
user-invocable: true
description: "Use when the user wants to run GMAT (General Mission Analysis Tool) space mission simulations via natural language. Triggers on: GMAT, orbit, space mission, satellite, spacecraft, propagation, maneuver, trajectory, delta-V, Hohmann, GEO, LEO, 航天, 轨道, 卫星, 仿真, 变轨, 发射. Generates GMAT .script files, executes them via Python API, and returns structured results."
---

# GMAT Agent — 自然语言驱动航天任务仿真

本 Skill 通过 LLM 将自然语言描述转化为 GMAT 仿真脚本，自动执行并解析结果，实现完整闭环。

## 工作流

### 0. 分流决策（必须）

处理任何用户请求前，先按 [`gmat-triage.instructions.md`](gmat-triage.instructions.md) 执行 5 层分流：

1. **GUI 需求** — 需要 3D 可视化？→ 添加 `OpenFramesInterface` 块
2. **空间范围** — 地球(✅) / 地月系(🔮) / 行星际(🔮)
3. **任务类型** — 传播 / 变轨 / 参数扫描 / OEM分析 / 发射窗口
4. **输出要求** — 轨道根数 / 完整轨迹 / 图形 / 时刻表
5. **歧义检测** — 参数不明确时列出选项，**不急于生成**

### 1. 理解用户需求

从自然语言中提取：任务类型、天体、轨道参数、时间跨度、输出要求。参考 [`assets/system_prompt.txt`](assets/system_prompt.txt) 理解 GMAT 能力边界。

### 2. 生成 GMAT 脚本

参考：
- [`assets/system_prompt.txt`](assets/system_prompt.txt) — GMAT 脚本语法完整参考
- [`references/templates/`](references/templates/) — 4 个可运行模板
- [`references/samples/INDEX.md`](references/samples/INDEX.md) — 19 个精选官方示例

### 3. 执行仿真

调用 [`scripts/runner/python_runner.py`](scripts/runner/python_runner.py) 通过 GMAT Python API 加载脚本并运行。

### 4. 解读结果

解析返回的结构化 JSON，用自然语言向用户报告关键结果。

## 关键约束

- **GMAT 路径配置**: 编辑 [`assets/default_config.yaml`](assets/default_config.yaml) 中的 `gmat_root` 字段，支持绝对路径和相对路径。也可通过 `GMAT_ROOT` 环境变量覆盖。
- 生成的 `.script` 文件写入 GMAT 的 `output/` 目录（由配置文件的 `output_dir` 指定）
- 执行后始终检查 `python_runner.py` 返回的 `success` 字段
- 如果 `success: false`，根据 `stage`、`error`、`details` 字段诊断问题并修正脚本
- `python_runner.py` 内置错误诊断：失败时自动提取行号级错误信息
- 使用 `--validate` / `--validate-only` 通过 GmatConsole 预检脚本语法
- 使用 `--var KEY=VALUE` 进行模板参数化替换（脚本中 `{{KEY}}` 占位符）
- 不要尝试运行 GMAT GUI（GMAT.exe），只使用 Python API 方式
- 生成的 `.script` 文件是**标准 GMAT 格式**，可手动加载到 GMAT GUI 进行图形化仿真和 3D 可视化
- 当用户要求可视化时，在脚本中添加 `OpenFramesInterface` 块
- 当用户提供 OEM 文件时：使用 `scripts/analysis/oem_reader.py` 解析，`scripts/analysis/plot_altitude.py` 可视化，`scripts/analysis/maneuver_detector.py` 检测机动
- 当用户询问神舟/天舟发射窗口时：使用 `scripts/prediction/launch_window.py`，指定酒泉/文昌站和时间

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
> "分析这个 OEM 文件的轨道变化趋势"（→ `scripts/analysis/oem_reader.py` + `scripts/analysis/plot_altitude.py`）

**发射窗口**:
> "神舟23号从酒泉发射，空间站过顶窗口是什么？"（→ `scripts/prediction/launch_window.py -s Jiuquan`）

## 目录结构

```
gmat-agent/
├── SKILL.md                         ← 本文件
├── README.md / README_CN.md         ← 使用说明 (EN/中文)
├── assets/                          ← 配置与提示词
│   ├── system_prompt.txt            ← LLM 系统提示词 — GMAT 脚本语法完整参考
│   └── default_config.yaml          ← 唯一配置入口 — GMAT 路径、轨道默认值
├── scripts/                         ← Python 工具链
│   ├── runner/
│   │   └── python_runner.py         ← 核心执行引擎 — 加载/执行/读取结果 + 程序化 API
│   ├── analysis/
│   │   ├── oem_reader.py            ← OEM 解析器 — CCSDS OEM v2.0 → Keplerian 批量转换
│   │   ├── plot_altitude.py         ← 高度绘图 — 近/远地点高度时间序列图
│   │   └── maneuver_detector.py     ← 变轨检测 — 轨道周期平滑 SMA 跳跃检测
│   └── prediction/
│       └── launch_window.py         ← 发射窗口计算 — 空间站过顶预测
├── references/                      ← 参考脚本
│   ├── templates/                   ← 4 个可运行模板 (参数化传播、脉冲变轨、有限推力等)
│   └── samples/                     ← 19 个精选 GMAT 官方示例 (按任务类型分类)
│       ├── INDEX.md                 ← 示例索引与使用说明
│       ├── propagation/             ← 轨道传播 (6)
│       ├── maneuver-transfer/       ← 变轨与转移 (5)
│       ├── navigation/              ← 导航与估计 (3)
│       ├── attitude/                ← 姿态 (3)
│       └── optimal-control/         ← 最优控制 (2)
├── gmat-triage.instructions.md      ← 分流决策树
```

## 相关文档

- **分流决策树**: [`gmat-triage.instructions.md`](gmat-triage.instructions.md)
- **参考脚本索引**: [`references/samples/INDEX.md`](references/samples/INDEX.md)
