# 大作业要求达标说明与演示流程

本文件面向课程验收与答辩，用来快速说明项目如何对应“新能源物流车队协同调度”大作业要求。

## 要求对照表

| 作业要求 | 项目实现 | 主要位置 | 达标情况 |
|---|---|---|---|
| 使用图结构实现道路和寻路 | 使用加权邻接表表示城市路网，并使用 Dijkstra 最短路进行路径规划 | `simulator/graph.py` | 已完成 |
| 车辆数有限，车辆有电量上限和载重上限 | `Vehicle` 记录载重、电池容量、当前电量、速度、能耗和可用时刻 | `simulator/models.py` | 已完成 |
| 动态出现任务，任务包含产生时间、地点坐标、货物重量 | `build_scenario()` 随机生成任务释放时间、节点坐标、货物重量和截止时间 | `simulator/simulation.py` | 已完成 |
| 完成越早、路径越短收益越高，超时扣分 | `_score_task()` 同时惩罚响应时间、行驶距离、充电等待和超时 | `simulator/simulation.py` | 已完成 |
| 电量不足时寻找充电站补能 | 车辆任务规划会先判断直达可行性，不足时调用充电站规划 | `FleetSimulator._plan_vehicle_mission()` | 已完成 |
| 考虑充电站排队与负荷压力 | `ChargingStation.reserve()` 维护端口最早可用时间；summary 输出平均/峰值利用率、会话数、最大等待时间 | `simulator/models.py`, `simulator/simulation.py` | 已加强 |
| 可选择多车协同完成同一任务 | 开启 `--allow-collaboration` 后，超重任务可由多车按容量比例分摊 | `simulator/strategies.py`, `simulator/simulation.py` | 已完成 |
| 至少两种新能源车辆调度策略 | 实现最近任务、最大任务、紧急度距离、拍卖式、模拟退火、大邻域搜索、Q 值启发式、UCB 超启发式共 8 种策略 | `simulator/strategies.py` | 超额完成 |
| 至少三种不同规模 | 支持 `small / medium / large`，并新增 `stress` 充电压力场景 | `SCENARIO_SCALES` | 超额完成 |
| 可尝试进阶算法或精确求解器 | 使用 CPLEX 建立静态全信息优化基线；若求解器证明最优则为全局最优，否则作为限时优化基线 | `simulator/exact_solver.py` | 加分项 |
| 图形界面展示 | 提供 Web Dashboard，可运行仿真、回放车辆路线、展示策略排名和历史结果 | `dashboard.py`, `simulator/web/` | 加分项 |

## 新增压力场景

`stress` 场景用于突出新能源车队调度中的电量与充电资源压力：

- 车辆初始电量更低；
- 车辆单位距离能耗更高；
- 充电站更少，每站端口数固定为 1；
- 充电速率较低；
- 任务释放更集中，协同任务比例更高。

推荐用于答辩中展示第 4、5 条要求：电量不足时的补能决策，以及充电站排队和负荷压力。

## 推荐演示命令

基础动态策略对比：

```bash
python main.py --no-oracle --allow-collaboration --seed-runs 3 --output results/summary_dynamic.json
```

充电压力场景演示：

```bash
python main.py --no-oracle --scales stress --strategies nearest_task_first urgency_distance lns_aaai_2025 hyper_heuristic_ucb --allow-collaboration --export-events --output results/summary_stress.json --events-output results/events_stress.json
```

动态策略与 CPLEX 静态全信息优化基线对比：

```bash
python main.py --allow-collaboration --exact-backend cplex --exact-scales small medium large --output results/summary_cplex.json
```

启动可视化仪表盘：

```bash
python dashboard.py
```

## 答辩表述建议

- 动态策略是在线决策，只能看到已经释放的任务。
- 新增的 `lns_aaai_2025` 是大邻域搜索策略，通过破坏候选解、修复并接受更优邻域解来增强局部重优化能力。
- CPLEX 基线是静态全信息模型，假设任务全集已知，因此信息条件更强。
- 如果 CPLEX 在时间限制内证明最优，可以称为全局最优；如果状态为 `time limit exceeded`，应称为“限时求解得到的静态优化基线”。
- 充电站排队不是只靠文字描述，结果文件中有 `charging_sessions`、`max_charging_wait`、`station_avg_utilization`、`station_peak_utilization` 等指标可以展示。
- 多车协同可通过 `collaborative_tasks`、`collaborative_task_ratio` 和回放事件中的多车辆路线展示。
