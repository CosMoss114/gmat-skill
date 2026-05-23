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
3. **执行仿真** — 调用 [`assets/python_runner.py`](assets/python_runner.py) 通过 GMAT Python API 加载脚本并运行
4. **解读结果** — 解析返回的结构化 JSON，用自然语言向用户报告关键结果

## 关键约束

- **GMAT 路径配置**: 编辑 [`assets/default_config.yaml`](assets/default_config.yaml) 中的 `gmat_root` 字段，支持绝对路径和相对路径。也可通过 `GMAT_ROOT` 环境变量覆盖。
- 生成的 `.script` 文件写入 GMAT 的 `output/` 目录（由配置文件的 `output_dir` 指定）
- 执行后始终检查 `python_runner.py` 返回的 `success` 字段
- 如果 `success: false`，根据 `stage` 和 `error` 字段诊断问题并修正脚本
- 不要尝试运行 GMAT GUI（GMAT.exe），只使用 Python API 方式
- 生成的 `.script` 文件是**标准 GMAT 格式**，可手动加载到 GMAT GUI 进行图形化仿真和 3D 可视化
- 当用户要求可视化时，在脚本中添加 `OpenFramesInterface` 块（见 system_prompt.txt 模板 6）

## 已验证的 GMAT 脚本语法（重要）

1. **ReportFile 配置行不加分号**: `RF.Filename = 'out.txt'` 而非 `RF.Filename = 'out.txt';`
2. **续行符 `...`**: 在 `{}` 块内跨行时必须使用 `...`，如 `RF.Add = {Sat.X, ...`
3. **ReportFile 自动写入**: 不含 `Report RF;` 命令，ReportFile 在任务结束时自动生成
4. **ReportFile.Add 只接受 Cartesian 参数**: `Sat.EarthMJ2000Eq.X` 有效, `Sat.Earth.SMA` 无效
5. **月球体名**: Python API 中使用 `Luna` 而非 `Moon`
6. **点质量**: MVP 阶段推荐仅使用纯地球中心引力，避免使用 `PointMasses`
7. **轨道初始值**: 推荐使用 Keplerian 状态 (`DisplayStateType = Keplerian`, SMA/ECC/INC)

## 典型使用示例

**简单传播**:
> "仿真一颗 500km 圆轨道卫星 3 天，输出位置速度"

**变轨任务**:
> "设计 Hohmann 转移从 300km LEO 到 GEO，计算需要的 delta-V"

**参数扫描**:
> "扫描倾角从 0 到 90 度对轨道寿命的影响"

## 文件说明

| 文件 | 用途 |
|------|------|
| `README.md` | 英文使用说明 |
| `README_CN.md` | 中文使用说明 |
| `assets/system_prompt.txt` | LLM 系统提示词 — GMAT 脚本语法完整参考 |
| `assets/python_runner.py` | Python 包装器 — 加载/执行/读取结果 |
| `assets/default_config.yaml` | **唯一配置入口** — GMAT 路径、轨道默认值、物理常量 |
| `assets/templates/*.script` | 可运行的脚本模板，供参考 |
