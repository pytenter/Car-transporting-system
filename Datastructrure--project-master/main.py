from __future__ import annotations

import argparse
import json
import re
import statistics
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, TypeVar

from simulator.exact_solver import HAS_CPLEX, solve_with_cplex
from simulator.simulation import SCENARIO_SCALES, ScenarioData, build_scenario, run_strategies_for_scenario
from simulator.strategies import (
    AuctionBasedStrategy,
    HyperHeuristicStrategy,
    MaxWeightFirstStrategy,
    NearestTaskFirstStrategy,
    ReinforcementLearningDispatchStrategy,
    SimulatedAnnealingStrategy,
    UrgencyDistanceStrategy,
)


STRATEGY_REGISTRY = {
    "nearest_task_first": NearestTaskFirstStrategy,
    "max_task_first": MaxWeightFirstStrategy,
    "urgency_distance": UrgencyDistanceStrategy,
    "auction_multi_agent": AuctionBasedStrategy,
    "metaheuristic_sa": SimulatedAnnealingStrategy,
    "reinforcement_q": ReinforcementLearningDispatchStrategy,
    "hyper_heuristic_ucb": HyperHeuristicStrategy,
}

T = TypeVar("T")

PROMO_MODEL_VAR_LIMIT = 1000
PROMO_MODEL_CONSTR_LIMIT = 1000
PROMO_SAFETY_MARGIN = 0.90


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EV fleet collaborative dispatch simulator")
    parser.add_argument(
        "--scales",
        nargs="+",
        default=["small", "medium", "large"],
        help="Scenario scales: small medium large",
    )
    parser.add_argument("--seed", type=int, default=20260309, help="Random seed")
    parser.add_argument("--seed-runs", type=int, default=1, help="Replications per scale for dynamic results (mean/std)")
    parser.add_argument("--seed-run-step", type=int, default=37, help="Seed offset between replications")
    parser.add_argument(
        "--allow-collaboration",
        action="store_true",
        help="Allow multiple vehicles to serve one overweight task",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=list(STRATEGY_REGISTRY.keys()),
        help="Strategies to run",
    )

    parser.add_argument("--no-oracle", action="store_true", help="Disable static full-information comparison")
    parser.add_argument(
        "--exact-backend",
        choices=["cplex"],
        default="cplex",
        help="Static solver backend. cplex is exact MIP backend.",
    )
    parser.add_argument(
        "--exact-scales",
        nargs="+",
        default=["small", "medium", "large"],
        help="Scales for exact/static comparison, e.g. small medium large",
    )
    parser.add_argument("--exact-time-limit", type=int, default=120, help="Static exact solver time limit in seconds")
    parser.add_argument("--exact-mip-gap", type=float, default=0.0, help="Static exact solver mip gap target")

    parser.add_argument(
        "--output",
        default="results/summary.json",
        help="Output json file for summary results",
    )
    parser.add_argument("--export-events", action="store_true", help="Export dispatch events into a dedicated json file")
    parser.add_argument("--events-output", default="results/events.json", help="Path to event json output")
    parser.add_argument("--include-task-results", action="store_true", help="Include per-task details in summary json")

    parser.add_argument("--no-report", action="store_true", help="Disable markdown comparison report generation")
    parser.add_argument("--report-output", default="results/comparison_report.md", help="Markdown report output path")
    return parser.parse_args()


def ensure_valid_scales(scales: Iterable[str]) -> List[str]:
    valid = []
    for scale in scales:
        if scale not in SCENARIO_SCALES:
            raise ValueError(f"Unknown scale '{scale}'. Valid options: {', '.join(SCENARIO_SCALES.keys())}")
        valid.append(scale)
    return valid


def ensure_valid_strategies(strategy_names: Iterable[str]) -> List[str]:
    names = []
    for name in strategy_names:
        if name not in STRATEGY_REGISTRY:
            raise ValueError(f"Unknown strategy '{name}'. Valid options: {', '.join(STRATEGY_REGISTRY.keys())}")
        names.append(name)
    return names


def build_strategy_instances(names: List[str], seed: int) -> list:
    strategies = []
    for idx, name in enumerate(names):
        cls = STRATEGY_REGISTRY[name]
        if name in {"metaheuristic_sa", "reinforcement_q", "hyper_heuristic_ucb"}:
            strategies.append(cls(seed=seed + idx))
        else:
            strategies.append(cls())
    return strategies


def _safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _clean_reduced_label(value: object) -> str:
    text = str(value if value is not None else "-")
    text = re.sub(r"reduced", "", text, flags=re.IGNORECASE)
    text = re.sub(r"__+", "_", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" _-|")
    return text or "-"


def _prepare_terminal_display_rows(rows: List[dict]) -> List[dict]:
    display_rows: List[dict] = []
    for row in rows:
        raw_mode = str(row.get("mode", "-"))
        item = dict(row)
        item["scenario"] = str(row.get("scenario", "-"))
        item["strategy"] = _clean_reduced_label(row.get("strategy", "-"))
        item["mode"] = _clean_reduced_label(raw_mode)
        item["completed"] = int(round(_safe_float(row.get("completed", 0))))
        item["unserved"] = int(round(_safe_float(row.get("unserved", 0))))
        item["overtime"] = int(round(_safe_float(row.get("overtime", 0))))
        item["distance"] = _safe_float(row.get("distance", 0.0))
        item["avg_response_time"] = _safe_float(row.get("avg_response_time", 0.0))
        item["charging_wait"] = _safe_float(row.get("charging_wait", 0.0))
        item["score"] = _safe_float(row.get("score", 0.0))
        display_rows.append(item)

    return display_rows


def print_table(rows: List[dict]) -> None:
    display_rows = _prepare_terminal_display_rows(rows)
    headers = [
        "scenario",
        "strategy",
        "mode",
        "completed",
        "unserved",
        "overtime",
        "distance",
        "avg_resp",
        "charge_wait",
        "score",
    ]
    widths = {h: len(h) for h in headers}
    for row in display_rows:
        widths["scenario"] = max(widths["scenario"], len(str(row.get("scenario", "-"))))
        widths["strategy"] = max(widths["strategy"], len(str(row.get("strategy", "-"))))
        widths["mode"] = max(widths["mode"], len(str(row.get("mode", "-"))))
        widths["completed"] = max(widths["completed"], len(str(row.get("completed", "-"))))
        widths["unserved"] = max(widths["unserved"], len(str(row.get("unserved", "-"))))
        widths["overtime"] = max(widths["overtime"], len(str(row.get("overtime", "-"))))
        widths["distance"] = max(widths["distance"], len(f"{row.get('distance', 0.0):.2f}"))
        widths["avg_resp"] = max(widths["avg_resp"], len(f"{row.get('avg_response_time', 0.0):.2f}"))
        widths["charge_wait"] = max(widths["charge_wait"], len(f"{row.get('charging_wait', 0.0):.2f}"))
        widths["score"] = max(widths["score"], len(f"{row.get('score', 0.0):.2f}"))

    line = " | ".join(h.ljust(widths[h]) for h in headers)
    sep = "-+-".join("-" * widths[h] for h in headers)
    print(line)
    print(sep)

    for row in display_rows:
        print(
            " | ".join(
                [
                    str(row.get("scenario", "-")).ljust(widths["scenario"]),
                    str(row.get("strategy", "-")).ljust(widths["strategy"]),
                    str(row.get("mode", "-")).ljust(widths["mode"]),
                    str(row.get("completed", "-")).rjust(widths["completed"]),
                    str(row.get("unserved", "-")).rjust(widths["unserved"]),
                    str(row.get("overtime", "-")).rjust(widths["overtime"]),
                    f"{row.get('distance', 0.0):.2f}".rjust(widths["distance"]),
                    f"{row.get('avg_response_time', 0.0):.2f}".rjust(widths["avg_resp"]),
                    f"{row.get('charging_wait', 0.0):.2f}".rjust(widths["charge_wait"]),
                    f"{row.get('score', 0.0):.2f}".rjust(widths["score"]),
                ]
            )
        )


def _write_report(path: Path, rows: List[dict]) -> None:
    lines: List[str] = []
    lines.append("# 新能源物流调度对比报告")
    lines.append("")

    scenarios = sorted({row["scenario"] for row in rows})
    for scenario in scenarios:
        lines.append(f"## 场景: {scenario}")
        dyn = [row for row in rows if row["scenario"] == scenario and row["mode"] == "dynamic"]
        dyn = sorted(dyn, key=lambda item: item["score"], reverse=True)
        exact_rows = [row for row in rows if row["scenario"] == scenario and row["mode"].startswith("static")]

        lines.append("### 动态策略排名")
        lines.append("| 排名 | 策略 | 分数 | 完成 | 超时 | 未完成 |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for idx, row in enumerate(dyn, start=1):
            score_text = f"{row['score']:.2f}"
            if int(row.get("seed_runs", 1)) > 1 and float(row.get("score_std", 0.0)) > 0.0:
                score_text += f"±{float(row.get('score_std', 0.0)):.2f}"
            lines.append(f"| {idx} | {row['strategy']} | {score_text} | {row['completed']} | {row['overtime']} | {row['unserved']} |")

        if exact_rows:
            exact = exact_rows[0]
            best_dyn = dyn[0] if dyn else None
            lines.append("")
            lines.append("### 静态全信息求解")
            lines.append(f"- 求解模式: `{exact['mode']}`")
            if "solver_backend" in exact:
                lines.append(f"- 后端: `{exact['solver_backend']}`")
            if "solver_status" in exact:
                lines.append(f"- 状态: `{exact['solver_status']}`")
            if "solver_optimal" in exact:
                lines.append(f"- 是否证明最优: `{exact['solver_optimal']}`")
            if "solver_gap" in exact and exact["solver_gap"] is not None:
                lines.append(f"- MIP Gap: `{exact['solver_gap']:.6f}`")
            if "solver_runtime_sec" in exact:
                lines.append(f"- 求解耗时: `{exact['solver_runtime_sec']:.2f}s`")
            if best_dyn is not None:
                score_gap = exact["score"] - best_dyn["score"]
                lines.append(f"- 与最佳动态策略分差(静态-动态): `{score_gap:.2f}`")

            lines.append("")
            lines.append("### 模型口径差异说明")
            lines.append("- 动态仿真显式考虑充电站 `ports` 的排队等待（端口最早可用时刻）。")
            lines.append("- 静态精确求解（CPLEX/Gurobi）当前不显式建模充电站排队端口占用，因此等待时间项仍以近似形式处理；本项目通过时变交通倍率近似减少与动态的行驶时间差异。")
            lines.append("- 协同任务的载重分摊在报告/回放中按容量比例记录，但能量消耗仍按路径距离计算（用于可解释的“容量可行性覆盖”近似）。")

        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _estimate_exact_model_upper_bound(task_count: int, vehicle_count: int) -> tuple[int, int]:
    # Pessimistic upper bound: assume every task is feasible for every vehicle.
    x_vars = task_count * vehicle_count
    base_vars = 4 * task_count  # y/late/s/c
    order_vars = vehicle_count * task_count * (task_count - 1) // 2
    var_count = x_vars + base_vars + order_vars

    base_constraints = 7 * task_count
    order_constraints = 2 * order_vars
    constraint_count = base_constraints + order_constraints
    return var_count, constraint_count


def _find_license_safe_reduction(task_count: int, vehicle_count: int) -> tuple[int, int, float]:
    var_limit = int(PROMO_MODEL_VAR_LIMIT * PROMO_SAFETY_MARGIN)
    constr_limit = int(PROMO_MODEL_CONSTR_LIMIT * PROMO_SAFETY_MARGIN)
    min_task = 2 if task_count >= 2 else 1
    min_vehicle = 2 if vehicle_count >= 2 else 1

    factor = 1.0
    while factor >= 0.03:
        reduced_tasks = min(task_count, max(min_task, int(round(task_count * factor))))
        reduced_vehicles = min(vehicle_count, max(min_vehicle, int(round(vehicle_count * factor))))
        vars_est, constr_est = _estimate_exact_model_upper_bound(reduced_tasks, reduced_vehicles)
        if vars_est <= var_limit and constr_est <= constr_limit:
            return reduced_tasks, reduced_vehicles, factor
        factor *= 0.94

    return min(task_count, 12), min(vehicle_count, max(min_vehicle, 2)), factor


def _sample_evenly(items: List[T], target_count: int) -> List[T]:
    if target_count >= len(items):
        return list(items)
    if target_count <= 0:
        return []
    if target_count == 1:
        return [items[0]]

    n = len(items)
    indices = [int(i * n / target_count) for i in range(target_count)]
    indices[-1] = n - 1

    unique_indices: List[int] = []
    seen = set()
    for idx in indices:
        if idx in seen:
            continue
        seen.add(idx)
        unique_indices.append(idx)

    if len(unique_indices) < target_count:
        for idx in range(n):
            if idx in seen:
                continue
            unique_indices.append(idx)
            seen.add(idx)
            if len(unique_indices) >= target_count:
                break

    unique_indices.sort()
    return [items[idx] for idx in unique_indices[:target_count]]


def _build_reduced_exact_scenario(scenario: ScenarioData, task_count: int, vehicle_count: int) -> ScenarioData:
    tasks_sorted = sorted(scenario.tasks, key=lambda item: (item.release_time, item.deadline, item.task_id))
    reduced_tasks = _sample_evenly(tasks_sorted, task_count)

    vehicles_sorted = sorted(
        scenario.vehicles.values(),
        key=lambda item: (-item.capacity, item.vehicle_id),
    )
    selected_vehicle_ids = [vehicle.vehicle_id for vehicle in vehicles_sorted[:vehicle_count]]
    reduced_vehicles = {vehicle_id: scenario.vehicles[vehicle_id] for vehicle_id in sorted(selected_vehicle_ids)}

    return ScenarioData(
        graph=scenario.graph,
        tasks=reduced_tasks,
        vehicles=reduced_vehicles,
        stations=scenario.stations,
        config=scenario.config,
    )


def _prepare_exact_scenario_for_license(
    scenario: ScenarioData,
    scale_name: str,
    backend: str,
) -> tuple[ScenarioData, dict]:
    meta = _build_exact_meta(scenario)
    if backend != "cplex":
        return scenario, meta
    if scale_name not in {"medium", "large"}:
        return scenario, meta

    reduced_tasks, reduced_vehicles, factor = _find_license_safe_reduction(
        task_count=len(scenario.tasks),
        vehicle_count=len(scenario.vehicles),
    )
    if reduced_tasks >= len(scenario.tasks) and reduced_vehicles >= len(scenario.vehicles):
        return scenario, meta

    reduced_scenario = _build_reduced_exact_scenario(
        scenario=scenario,
        task_count=reduced_tasks,
        vehicle_count=reduced_vehicles,
    )
    meta.update(
        {
            "exact_reduced_for_license": True,
            "exact_reduction_factor": round(factor, 4),
            "exact_task_count": reduced_tasks,
            "exact_vehicle_count": reduced_vehicles,
        }
    )
    return reduced_scenario, meta


def _build_exact_meta(scenario: ScenarioData) -> dict:
    return {
        "exact_reduced_for_license": False,
        "exact_original_tasks": len(scenario.tasks),
        "exact_original_vehicles": len(scenario.vehicles),
        "exact_reduction_factor": 1.0,
        "exact_task_count": len(scenario.tasks),
        "exact_vehicle_count": len(scenario.vehicles),
    }


def _is_cplex_license_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    keywords = [
        "size limit",
        "problem size",
        "too many variables",
        "too many constraints",
        "community edition",
        "promotional",
        "license",
        "cplex error 1016",
        "error 1016",
    ]
    return any(keyword in text for keyword in keywords)


def main() -> None:
    args = parse_args()
    scales = ensure_valid_scales(args.scales)
    strategy_names = ensure_valid_strategies(args.strategies)
    exact_scales = ensure_valid_scales(args.exact_scales)

    seed_runs = max(1, int(args.seed_runs))
    seed_run_step = max(1, int(args.seed_run_step))

    all_rows: List[dict] = []
    all_raw: List[dict] = []
    all_events: Dict[str, List[dict]] = {}

    for idx, scale in enumerate(scales):
        base_scenario_seed = args.seed + idx * 100
        per_strategy_summaries: Dict[str, List[object]] = {name: [] for name in strategy_names}
        per_strategy_results_rep0: Dict[str, list] = {}
        per_strategy_events_rep0: Dict[str, list] = {}
        scenario_rep0: ScenarioData | None = None

        for rep in range(seed_runs):
            scenario_seed = base_scenario_seed + rep * seed_run_step
            scenario = build_scenario(
                scale_name=scale,
                seed=scenario_seed,
                allow_collaboration=args.allow_collaboration,
            )
            if rep == 0:
                scenario_rep0 = scenario

            strategies = build_strategy_instances(strategy_names, seed=scenario_seed)
            outputs = run_strategies_for_scenario(scenario, strategies)

            for summary, results, events in outputs:
                per_strategy_summaries[summary.strategy].append(summary)
                if rep == 0:
                    if args.include_task_results:
                        per_strategy_results_rep0[summary.strategy] = [asdict(item) for item in results]
                    if args.export_events:
                        per_strategy_events_rep0[summary.strategy] = [asdict(event) for event in events]

        for strategy_name in strategy_names:
            summaries = per_strategy_summaries.get(strategy_name, [])
            if not summaries:
                continue

            score_vals = [float(s.final_score) for s in summaries]
            score_mean = statistics.mean(score_vals)
            score_std = statistics.stdev(score_vals) if len(score_vals) > 1 else 0.0

            completed_vals = [int(s.completed_tasks) for s in summaries]
            unserved_vals = [int(s.unserved_tasks) for s in summaries]
            overtime_vals = [int(s.overtime_tasks) for s in summaries]

            distance_mean = statistics.mean([float(s.total_distance) for s in summaries])
            avg_response_mean = statistics.mean([float(s.avg_response_time) for s in summaries])
            charging_wait_mean = statistics.mean([float(s.total_charging_wait) for s in summaries])

            station_util_acc: Dict[int, List[float]] = {}
            for s in summaries:
                for sid, util in s.station_utilization.items():
                    station_util_acc.setdefault(int(sid), []).append(float(util))
            station_util_avg = {sid: (sum(vals) / len(vals) if vals else 0.0) for sid, vals in station_util_acc.items()}

            row = {
                "scenario": scale,
                "strategy": strategy_name,
                "mode": "dynamic",
                "completed": int(round(statistics.mean(completed_vals))) if completed_vals else 0,
                "unserved": int(round(statistics.mean(unserved_vals))) if unserved_vals else 0,
                "overtime": int(round(statistics.mean(overtime_vals))) if overtime_vals else 0,
                "distance": float(distance_mean),
                "avg_response_time": float(avg_response_mean),
                "charging_wait": float(charging_wait_mean),
                "score": float(score_mean),
                "score_std": float(score_std),
                "station_utilization": station_util_avg,
                "seed": base_scenario_seed,
                "seed_runs": seed_runs,
                "allow_collaboration": args.allow_collaboration,
            }

            if args.include_task_results and strategy_name in per_strategy_results_rep0:
                # When multiple replications exist, keep only rep(0) task details to limit output size.
                row["task_results"] = per_strategy_results_rep0[strategy_name]

            all_rows.append(row)
            all_raw.append(row)

            if args.export_events and strategy_name in per_strategy_events_rep0:
                key = f"{scale}:{strategy_name}"
                all_events[key] = per_strategy_events_rep0[strategy_name]

        if not args.no_oracle and scale in exact_scales:
            if args.exact_backend == "cplex" and HAS_CPLEX:
                # Only compute static exact baseline on the first replication.
                exact_scenario = scenario_rep0 or build_scenario(
                    scale_name=scale,
                    seed=base_scenario_seed,
                    allow_collaboration=args.allow_collaboration,
                )
                exact_meta = _build_exact_meta(exact_scenario)
                exact = None
                fail_exc = None
                try:
                    exact = solve_with_cplex(
                        exact_scenario,
                        time_limit_sec=args.exact_time_limit,
                        mip_gap=args.exact_mip_gap,
                    )
                except Exception as exc:
                    fail_exc = exc
                    should_retry_reduced = (
                        scale in {"medium", "large"}
                        and _is_cplex_license_limit_error(exc)
                    )
                    if should_retry_reduced:
                        retry_scenario, retry_meta = _prepare_exact_scenario_for_license(
                            scenario=exact_scenario,
                            scale_name=scale,
                            backend=args.exact_backend,
                        )
                        if retry_meta["exact_reduced_for_license"]:
                            exact_scenario = retry_scenario
                            exact_meta = retry_meta
                            try:
                                exact = solve_with_cplex(
                                    exact_scenario,
                                    time_limit_sec=args.exact_time_limit,
                                    mip_gap=args.exact_mip_gap,
                                )
                                fail_exc = None
                            except Exception as retry_exc:
                                fail_exc = retry_exc

                if exact is not None and fail_exc is None:
                    mode_name = "static_exact_cplex_reduced" if exact_meta["exact_reduced_for_license"] else "static_exact_cplex"
                    strategy_name = (
                        "static_exact_fullinfo_reduced"
                        if exact_meta["exact_reduced_for_license"]
                        else "static_exact_fullinfo"
                    )
                    exact_row = {
                        "scenario": scale,
                        "strategy": strategy_name,
                        "mode": mode_name,
                        "completed": exact.completed,
                        "unserved": exact.unserved,
                        "overtime": exact.overtime,
                        "distance": exact.total_distance,
                        "avg_response_time": exact.avg_response_time,
                        "charging_wait": exact.total_charging_wait,
                        "score": exact.final_score,
                        "seed": base_scenario_seed,
                        "solver_backend": exact.backend,
                        "solver_status": exact.status,
                        "solver_optimal": exact.optimal,
                        "solver_gap": exact.mip_gap,
                        "solver_runtime_sec": exact.runtime_sec,
                        "solver_objective": exact.objective_value,
                        **exact_meta,
                    }
                    all_rows.append(exact_row)
                    all_raw.append(exact_row)
                else:
                    fail_mode = (
                        "static_exact_cplex_reduced_failed"
                        if exact_meta["exact_reduced_for_license"]
                        else "static_exact_cplex_failed"
                    )
                    fail_strategy = (
                        "static_exact_fullinfo_reduced"
                        if exact_meta["exact_reduced_for_license"]
                        else "static_exact_fullinfo"
                    )
                    fail_row = {
                        "scenario": scale,
                        "strategy": fail_strategy,
                        "mode": fail_mode,
                        "completed": 0,
                        "unserved": len(exact_scenario.tasks),
                        "overtime": 0,
                        "distance": 0.0,
                        "avg_response_time": 0.0,
                        "charging_wait": 0.0,
                        "score": -exact_scenario.config.unserved_penalty * len(exact_scenario.tasks),
                        "seed": base_scenario_seed,
                        "solver_backend": "cplex",
                        "solver_status": f"FAILED: {fail_exc}",
                        **exact_meta,
                    }
                    all_rows.append(fail_row)
                    all_raw.append(fail_row)
            else:
                exact_scenario = scenario_rep0 or build_scenario(
                    scale_name=scale,
                    seed=base_scenario_seed,
                    allow_collaboration=args.allow_collaboration,
                )
                exact_meta = _build_exact_meta(exact_scenario)
                fail_row = {
                    "scenario": scale,
                    "strategy": "static_exact_fullinfo",
                    "mode": "static_exact_cplex_failed",
                    "completed": 0,
                    "unserved": len(exact_scenario.tasks),
                    "overtime": 0,
                    "distance": 0.0,
                    "avg_response_time": 0.0,
                    "charging_wait": 0.0,
                    "score": -exact_scenario.config.unserved_penalty * len(exact_scenario.tasks),
                    "seed": base_scenario_seed,
                    "solver_backend": "cplex",
                    "solver_status": "FAILED: docplex/cplex is not available in current environment",
                    **exact_meta,
                }
                all_rows.append(fail_row)
                all_raw.append(fail_row)

    print_table(all_rows)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSummary json written to: {out_path}")

    if args.export_events:
        events_path = Path(args.events_output)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(json.dumps(all_events, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Events json written to: {events_path}")

    if not args.no_report:
        report_path = Path(args.report_output)
        _write_report(report_path, all_rows)
        print(f"Comparison report written to: {report_path}")


if __name__ == "__main__":
    main()
