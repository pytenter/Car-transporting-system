# 新能源物流调度对比报告

## 新增策略补充说明

当前代码已经新增第 8 种动态策略 `lns_aaai_2025`，即大邻域搜索（LNS）。该策略在 `simulator/strategies.py` 中通过“候选解破坏、修复、接受判断”的流程对在线派单决策做局部重优化。

下面原有排名表来自既有批量实验结果；新增 LNS 的单独 smoke 检查结果已保存在 `results/summary_lns_smoke.json`，天气/路况统计已补齐到 `results/weather_stats.json`，Dashboard 会合并展示。

| 场景 | 策略 | 模式 | 完成 | 超时 | 未完成 | 得分 |
|---|---|---|---:|---:|---:|---:|
| small | `lns_aaai_2025` | dynamic | 14 | 2 | 0 | 1554.40 |
| medium | `lns_aaai_2025` | dynamic | 110 | 5 | 0 | 19030.96 |
| large | `lns_aaai_2025` | dynamic | 220 | 6 | 0 | 36246.19 |

如需生成完全同口径的 8 策略排名，可重新运行：

```bash
python main.py --no-oracle --allow-collaboration --seed-runs 3 --output results/summary_dynamic.json
```

## 场景: large
### 动态策略排名
| 排名 | 策略 | 分数 | 完成 | 超时 | 未完成 |
|---|---|---:|---:|---:|---:|
| 1 | metaheuristic_sa | 37587.36±1327.04 | 220 | 2 | 0 |
| 2 | hyper_heuristic_ucb | 37545.49±1313.37 | 220 | 3 | 0 |
| 3 | reinforcement_q | 37499.38±1294.35 | 220 | 4 | 0 |
| 4 | auction_multi_agent | 37396.83±1211.57 | 220 | 4 | 0 |
| 5 | max_task_first | 37396.36±1372.16 | 220 | 4 | 0 |
| 6 | urgency_distance | 37361.04±1385.09 | 220 | 4 | 0 |
| 7 | nearest_task_first | 37317.37±1392.37 | 220 | 4 | 0 |

## 场景: medium
### 动态策略排名
| 排名 | 策略 | 分数 | 完成 | 超时 | 未完成 |
|---|---|---:|---:|---:|---:|
| 1 | metaheuristic_sa | 17785.58±2588.77 | 110 | 7 | 0 |
| 2 | hyper_heuristic_ucb | 17754.00±2645.29 | 110 | 7 | 0 |
| 3 | auction_multi_agent | 17733.04±2687.57 | 110 | 6 | 0 |
| 4 | nearest_task_first | 17711.21±2393.08 | 110 | 7 | 0 |
| 5 | reinforcement_q | 17704.96±2743.27 | 110 | 8 | 0 |
| 6 | max_task_first | 17676.15±2656.33 | 110 | 6 | 0 |
| 7 | urgency_distance | 17214.59±2677.11 | 110 | 8 | 0 |

## 场景: small
### 动态策略排名
| 排名 | 策略 | 分数 | 完成 | 超时 | 未完成 |
|---|---|---:|---:|---:|---:|
| 1 | hyper_heuristic_ucb | 2233.03±333.61 | 14 | 0 | 0 |
| 2 | max_task_first | 2232.16±332.73 | 14 | 0 | 0 |
| 3 | urgency_distance | 2216.63±361.88 | 14 | 0 | 0 |
| 4 | metaheuristic_sa | 2216.63±361.88 | 14 | 0 | 0 |
| 5 | auction_multi_agent | 2215.75±361.00 | 14 | 0 | 0 |
| 6 | reinforcement_q | 2206.49±314.43 | 14 | 1 | 0 |
| 7 | nearest_task_first | 2101.64±412.82 | 14 | 0 | 0 |
