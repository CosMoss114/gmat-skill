# GMAT 精选参考脚本

本目录包含来自 GMAT 官方示例 (`application/samples/`) 的精选参考脚本，按任务类型分类。

每个脚本均可通过 GMAT GUI 或 Python API 独立运行。详细语法请参考 `assets/system_prompt.txt`。

## 分类索引

### propagation — 轨道传播

| 脚本 | 用途 |
|------|------|
| `Tut_SimulatingAnOrbit.script` | 基础轨道传播教程：设置航天器、力模型、传播器并运行 |
| `Ex_HohmannTransfer.script` | 经典 Hohmann 转移：LEO→GEO 双脉冲变轨，含瞄准求解 |
| `Ex_GEOTransfer.script` | GEO 转移：从倾斜椭圆轨道到赤道同步轨道 |
| `Ex_TLE_Propagation.script` | TLE 两行根数传播：使用 SGP4 传播器 |
| `Ex_ConstellationScript.script` | 星座传播：多航天器作为编队同时传播 |
| `Ex_ForceModels.script` | 多力模型配置：引力、大气阻力、太阳光压、多体引力 |

### maneuver-transfer — 变轨与转移

| 脚本 | 用途 |
|------|------|
| `Tut_SimpleOrbitTransfer.script` | 简单轨道转移教程：使用 Target/Vary/Achieve |
| `Ex_FiniteBurn.script` | 有限推力：贮箱+推力器+有限时长机动序列 |
| `Ex_LEOStationKeeping.script` | LEO 轨道保持：高度盒 stationkeeping |
| `Ex_ElectricPropulsion.script` | 电推进：长时间低推力变轨 |
| `Ex_TargetFiniteBurn_CenterPeriapsisDuration.script` | 有限推力瞄准：基于时长的近地点中心化 |

### navigation — 导航与估计

| 脚本 | 用途 |
|------|------|
| `Ex_Estimate_RangeRangeRate.script` | 距离/距离率估计：双向测距和多向距离率 |
| `Ex_Simulate_and_Process_Range_and_RangeRate_data.script` | 仿真+处理距离/距离率数据 |
| `Ex_Estimate_ThrustScaleFactor.script` | 推力标度因子估计 |

### attitude — 姿态

| 脚本 | 用途 |
|------|------|
| `Ex_Attitude_NadirPointing.script` | 对地定向姿态模型 |
| `Ex_Attitude_Spinner.script` | 自旋姿态模型 |
| `Ex_Attitude_VNB.script` | VNB (速度-法向-副法向) 坐标系姿态 |

### optimal-control — 最优控制

| 脚本 | 用途 |
|------|------|
| `Ex_EarthToMarsSOI_C3Eq0_CSALTTutorial.script` | 地球-火星 SOI 最优控制教程 (CSALT) |
| `Ex_CelestialBodyRendezvous_Mars.script` | 火星交会优化 |

## 使用方式

### GMAT GUI
在 GMAT GUI 中 File → Open → 选择对应 `.script` 文件，点击 Run。

### Python API
```powershell
python scripts/runner/python_runner.py --script references/samples/propagation/Ex_HohmannTransfer.script --objects Sat
```

## 注意事项

- 部分脚本依赖插件（如 EstimationPlugin、CSALT）。确保 GMAT 安装包含所需插件。
- `optimal-control/` 下的脚本需要 `-DGMAT_INCLUDE_CSALT=ON` 编译选项。
- 脚本中的航天器名、传播器名等可能不同，使用 `--objects` 指定需要读取的对象名。
- 若脚本执行失败，使用 `--validate-only` 预检语法。
