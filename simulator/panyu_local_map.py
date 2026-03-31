from __future__ import annotations

import json
import math
import random
from dataclasses import replace
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from PIL import Image

from .graph import WeightedGraph
from .models import ChargingStation, SimulationConfig, Task, Vehicle
from .simulation import SCENARIO_SCALES, ScenarioData, ScenarioScale, _build_weather_rush_windows


ASSETS_DIR = Path(__file__).with_name("web") / "assets"
BASEMAP_PATH = ASSETS_DIR / "panyu-basemap.png"
ROADMASK_CANDIDATES = (
    ASSETS_DIR / "panyu-roadmask.png",
    ASSETS_DIR / "main_roads_black_white_cropped.png",
)
MAP_BOUNDS = {
    "west": 113.15,
    "east": 113.70,
    "south": 22.86,
    "north": 23.24,
}
ROAD_THRESHOLD = 208
PROCESS_MAX_WIDTH = 960
SPREAD_GRID_COLS = 4
SPREAD_GRID_ROWS = 3
LOCAL_CACHE_DIR = Path(__file__).with_name("offline_cache")
LOCAL_TEMPLATE_CACHE_VERSION = 2
MAP_ENERGY_CALIBRATION_FACTOR = 0.78
MAP_SCALE_TUNING = {
    "small": {
        "deadline_add": 25,
        "speed_mul": 1.03,
        "station_charge_rate_mul": 1.0,
        "station_ports_add": 0,
    },
    "medium": {
        "deadline_add": 18,
        "speed_mul": 1.04,
        "station_charge_rate_mul": 1.35,
        "station_ports_add": 1,
    },
    "large": {
        "deadline_add": 0,
        "speed_mul": 1.0,
        "station_charge_rate_mul": 1.0,
        "station_ports_add": 0,
    },
}
_TEMPLATE_CACHE: Dict[str, "_RoadTemplate"] = {}


@dataclass(frozen=True)
class _RoadTemplate:
    width: int
    height: int
    points: List[Tuple[int, int]]
    edges: List[Tuple[int, int]]


def has_panyu_local_map_assets() -> bool:
    return BASEMAP_PATH.exists() and BASEMAP_PATH.is_file()


def _roadmask_path() -> Path | None:
    for path in ROADMASK_CANDIDATES:
        if path.exists() and path.is_file():
            return path
    return None


def build_panyu_local_scenario(
    scale_name: str,
    seed: int,
    allow_collaboration: bool = False,
    weather_mode: str = "normal",
) -> ScenarioData:
    if scale_name not in SCENARIO_SCALES:
        raise ValueError(f"Unknown scale: {scale_name}")
    if not has_panyu_local_map_assets():
        raise RuntimeError(f"Local basemap not found: {BASEMAP_PATH}")

    scale = _local_scale(scale_name)
    template = _get_template(scale_name)
    rnd = random.Random(seed)

    graph = WeightedGraph()
    node_meta: Dict[int, dict] = {}
    for node_id, (px, py) in enumerate(template.points):
        lng, lat = _pixel_to_lnglat(px, py, template.width, template.height)
        graph.add_node(node_id=node_id, x=lng, y=lat)
        node_meta[node_id] = {
            "name": f"番禺区道路节点 {node_id}",
            "address": "广州市番禺区主干道路网",
            "pixel_x": px,
            "pixel_y": py,
        }

    for src, dst in template.edges:
        a = graph.nodes[src]
        b = graph.nodes[dst]
        distance = max(0.08, _haversine_km(a.x, a.y, b.x, b.y) * 1.05)
        graph.add_edge(src, dst, distance)

    degrees = _degree_map(template.edges, len(template.points))
    available_nodes = set(range(len(template.points)))
    depot_node = _pick_depot_node(template, degrees)
    available_nodes.discard(depot_node)
    node_meta[depot_node]["name"] = "番禺区车库"

    station_nodes = _pick_spread_nodes(
        candidates=list(available_nodes),
        count=scale.stations,
        template=template,
        rnd=rnd,
        degrees=degrees,
        weight_mode="degree",
    )
    for node_id in station_nodes:
        available_nodes.discard(node_id)

    task_nodes = _pick_spread_nodes(
        candidates=list(available_nodes),
        count=scale.tasks,
        template=template,
        rnd=rnd,
        degrees=degrees,
        weight_mode="mixed",
    )
    for node_id in task_nodes:
        available_nodes.discard(node_id)

    stations: Dict[int, ChargingStation] = {}
    for station_id, node_id in enumerate(station_nodes):
        stations[station_id] = ChargingStation(
            station_id=station_id,
            node_id=node_id,
            charge_rate=rnd.uniform(3.8, 6.4),
            ports=rnd.randint(1, 4),
        )
        node_meta[node_id]["name"] = f"番禺区充电站 {station_id}"

    vehicles: Dict[int, Vehicle] = {}
    for vehicle_id in range(scale.vehicles):
        battery_capacity = rnd.uniform(130.0, 220.0)
        vehicles[vehicle_id] = Vehicle(
            vehicle_id=vehicle_id,
            capacity=rnd.uniform(9.5, 16.0),
            battery_capacity=battery_capacity,
            speed=rnd.uniform(1.55, 2.25),
            # Geographic map distances are materially longer than the synthetic graph's
            # abstract edge lengths, so calibrate energy intensity downward to keep
            # route feasibility comparable across scenario sources.
            energy_per_distance=rnd.uniform(0.82, 1.06) * MAP_ENERGY_CALIBRATION_FACTOR,
            current_node=depot_node,
            battery=battery_capacity * 0.90,
        )

    tasks = _build_tasks(
        scale=scale,
        graph=graph,
        task_nodes=task_nodes,
        vehicles=vehicles,
        allow_collaboration=allow_collaboration,
        rnd=rnd,
    )
    _apply_map_scale_tuning(scale.name, tasks, vehicles, stations)
    for task in tasks:
        node_meta[task.node_id]["name"] = f"番禺区任务点 {task.task_id}"

    config = SimulationConfig(
        name=scale.name,
        seed=seed,
        horizon=scale.horizon,
        depot_node=depot_node,
        service_time=3.8,
        overtime_penalty=70.0,
        unserved_penalty=60.0,
        allow_collaboration=allow_collaboration,
        min_battery_reserve_ratio=0.22 if scale.name == "small" else 0.30,
        task_end_target_ratio=0.45 if scale.name == "small" else 0.55,
        idle_recharge_trigger_ratio=0.45 if scale.name == "small" else 0.55,
        idle_recharge_target_ratio=0.90,
        allow_depot_charging=True,
        depot_charge_rate=7.2,
        depot_charge_ports=max(3, min(8, scale.vehicles // 3)),
        rush_windows=_build_weather_rush_windows(scale=scale, rnd=rnd, weather_mode=weather_mode),
        weather_mode=weather_mode,
        map_mode="local_mask",
        city_name="广州市",
        district_name="番禺区",
        route_provider="local_mask",
    )
    tasks.sort(key=lambda item: (item.release_time, item.task_id))
    return ScenarioData(graph=graph, tasks=tasks, vehicles=vehicles, stations=stations, config=config, node_meta=node_meta)


def _get_template(scale_name: str) -> _RoadTemplate:
    cached = _TEMPLATE_CACHE.get(scale_name)
    if cached is not None:
        return cached

    cached_disk = _load_template_from_disk(scale_name)
    if cached_disk is not None:
        _TEMPLATE_CACHE[scale_name] = cached_disk
        return cached_disk

    roadmask_path = _roadmask_path()
    explicit_mask = roadmask_path is not None
    image = Image.open(BASEMAP_PATH if not explicit_mask else roadmask_path).convert("RGB")
    if image.width > PROCESS_MAX_WIDTH:
        scale = PROCESS_MAX_WIDTH / float(image.width)
        resized_height = max(1, int(round(image.height * scale)))
        resample = Image.NEAREST if explicit_mask else Image.BILINEAR
        image = image.resize((PROCESS_MAX_WIDTH, resized_height), resample=resample)
    width, height = image.size
    mask = _build_road_mask(image, explicit_mask=explicit_mask)
    dense_points = _extract_candidate_points(mask, width, height, step=14, search_radius=9)
    target = _target_graph_nodes(scale_name)
    points = _select_spread_points(dense_points, target, width // 2, height // 2)
    edges = _build_edges(points, mask, width, height, max_neighbors=5, max_distance=190)
    edges = _connect_components(points, edges, mask, width, height)
    template = _RoadTemplate(width=width, height=height, points=points, edges=edges)
    _save_template_to_disk(scale_name, template)
    _TEMPLATE_CACHE[scale_name] = template
    return template


def _build_road_mask(image: Image.Image, explicit_mask: bool) -> List[List[bool]]:
    width, height = image.size
    pixels = image.load()
    mask = [[False for _ in range(width)] for _ in range(height)]
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if explicit_mask:
                mask[y][x] = ((r + g + b) / 3.0) <= ROAD_THRESHOLD
                continue
            max_c = max(r, g, b)
            min_c = min(r, g, b)
            sat = max_c - min_c
            mask[y][x] = sat >= 36 and 96 <= max_c <= 245 and not (b > 150 and g > 150 and r < 150)
    return mask


def _extract_candidate_points(
    mask: List[List[bool]],
    width: int,
    height: int,
    *,
    step: int,
    search_radius: int,
) -> List[Tuple[int, int]]:
    candidates: List[Tuple[int, int]] = []
    seen = set()
    for cy in range(step // 2, height, step):
        y0 = max(0, cy - search_radius)
        y1 = min(height, cy + search_radius + 1)
        for cx in range(step // 2, width, step):
            x0 = max(0, cx - search_radius)
            x1 = min(width, cx + search_radius + 1)
            best = None
            best_score = None
            for y in range(y0, y1):
                row = mask[y]
                for x in range(x0, x1):
                    if not row[x]:
                        continue
                    score = abs(x - cx) + abs(y - cy)
                    if best_score is None or score < best_score:
                        best_score = score
                        best = (x, y)
            if best is None or best in seen:
                continue
            seen.add(best)
            candidates.append(best)
    if len(candidates) < 32:
        raise RuntimeError("番禺区道路骨架节点不足，请补充 panyu-roadmask.png 或更清晰的底图。")
    return candidates


def _target_graph_nodes(scale_name: str) -> int:
    if scale_name == "small":
        return 64
    if scale_name == "medium":
        return 150
    return 260


def _local_scale(scale_name: str) -> ScenarioScale:
    base = SCENARIO_SCALES[scale_name]
    if scale_name != "small":
        return base
    return replace(
        base,
        tasks=22,
        stations=4,
        horizon=max(base.horizon, 450),
        max_task_weight=min(20.0, base.max_task_weight + 0.8),
    )


def _select_spread_points(
    candidates: Sequence[Tuple[int, int]],
    count: int,
    center_x: int,
    center_y: int,
) -> List[Tuple[int, int]]:
    if len(candidates) <= count:
        return list(candidates)

    selected: List[Tuple[int, int]] = []
    remaining = list(candidates)
    start = min(remaining, key=lambda item: abs(item[0] - center_x) + abs(item[1] - center_y))
    selected.append(start)
    remaining.remove(start)

    while remaining and len(selected) < count:
        best_idx = 0
        best_score = -1.0
        for idx, point in enumerate(remaining):
            nearest = min(_pixel_distance(point, chosen) for chosen in selected)
            if nearest > best_score:
                best_score = nearest
                best_idx = idx
        selected.append(remaining.pop(best_idx))
    return selected


def _build_edges(
    points: Sequence[Tuple[int, int]],
    mask: List[List[bool]],
    width: int,
    height: int,
    *,
    max_neighbors: int,
    max_distance: float,
) -> List[Tuple[int, int]]:
    edges = set()
    for src, point in enumerate(points):
        distances = []
        for dst, other in enumerate(points):
            if src == dst:
                continue
            dist = _pixel_distance(point, other)
            if dist <= max_distance:
                distances.append((dist, dst))
        distances.sort(key=lambda item: item[0])
        added = 0
        for dist, dst in distances:
            if added >= max_neighbors:
                break
            ratio = _line_road_ratio(point, points[dst], mask, width, height)
            if ratio < 0.48:
                continue
            edge = tuple(sorted((src, dst)))
            if edge in edges:
                continue
            edges.add(edge)
            added += 1
    return sorted(edges)


def _connect_components(
    points: Sequence[Tuple[int, int]],
    edges: List[Tuple[int, int]],
    mask: List[List[bool]],
    width: int,
    height: int,
) -> List[Tuple[int, int]]:
    current = set(edges)
    while True:
        components = _connected_components(len(points), list(current))
        if len(components) <= 1:
            return sorted(current)

        base = max(components, key=len)
        others = [component for component in components if component is not base]
        best_edge = None
        best_score = None
        for other in others:
            for src in base:
                for dst in other:
                    dist = _pixel_distance(points[src], points[dst])
                    ratio = _line_road_ratio(points[src], points[dst], mask, width, height)
                    score = dist * (1.45 - min(0.95, ratio))
                    if best_score is None or score < best_score:
                        best_score = score
                        best_edge = tuple(sorted((src, dst)))
        if best_edge is None:
            return sorted(current)
        current.add(best_edge)


def _connected_components(node_count: int, edges: Sequence[Tuple[int, int]]) -> List[List[int]]:
    adj = [[] for _ in range(node_count)]
    for src, dst in edges:
        adj[src].append(dst)
        adj[dst].append(src)

    visited = [False] * node_count
    components: List[List[int]] = []
    for node_id in range(node_count):
        if visited[node_id]:
            continue
        stack = [node_id]
        visited[node_id] = True
        component = []
        while stack:
            cur = stack.pop()
            component.append(cur)
            for nxt in adj[cur]:
                if visited[nxt]:
                    continue
                visited[nxt] = True
                stack.append(nxt)
        components.append(component)
    return components


def _degree_map(edges: Sequence[Tuple[int, int]], node_count: int) -> Dict[int, int]:
    degrees = {node_id: 0 for node_id in range(node_count)}
    for src, dst in edges:
        degrees[src] += 1
        degrees[dst] += 1
    return degrees


def _pick_depot_node(template: _RoadTemplate, degrees: Dict[int, int]) -> int:
    target_x = template.width * 0.52
    target_y = template.height * 0.48
    return min(
        range(len(template.points)),
        key=lambda node_id: (
            abs(template.points[node_id][0] - target_x)
            + abs(template.points[node_id][1] - target_y)
            - degrees.get(node_id, 0) * 20.0
        ),
    )


def _pick_spread_nodes(
    candidates: Sequence[int],
    count: int,
    template: _RoadTemplate,
    rnd: random.Random,
    degrees: Dict[int, int],
    *,
    weight_mode: str,
) -> List[int]:
    pool = list(candidates)
    if len(pool) <= count:
        rnd.shuffle(pool)
        return pool[:count]

    sectors = _group_candidates_by_sector(pool, template)
    active_keys = [key for key, items in sectors.items() if items]
    active_keys.sort(key=lambda key: (-len(sectors[key]), key))

    quotas = {key: 0 for key in active_keys}
    remaining = count
    while remaining > 0 and active_keys:
        progressed = False
        for key in active_keys:
            if remaining <= 0:
                break
            if quotas[key] >= len(sectors[key]):
                continue
            quotas[key] += 1
            remaining -= 1
            progressed = True
        if not progressed:
            break

    chosen: List[int] = []
    chosen_by_sector: Dict[Tuple[int, int], List[int]] = {key: [] for key in active_keys}
    while len(chosen) < count:
        progressed = False
        for key in active_keys:
            if len(chosen) >= count:
                break
            bucket = [node_id for node_id in sectors[key] if node_id not in chosen]
            if not bucket or len(chosen_by_sector[key]) >= quotas[key]:
                continue

            best_node = None
            best_score = None
            for node_id in bucket:
                score = _spread_pick_score(
                    node_id=node_id,
                    chosen=chosen,
                    chosen_local=chosen_by_sector[key],
                    template=template,
                    degrees=degrees,
                    rnd=rnd,
                    weight_mode=weight_mode,
                )
                if best_score is None or score > best_score:
                    best_score = score
                    best_node = node_id
            if best_node is None:
                continue
            chosen.append(best_node)
            chosen_by_sector[key].append(best_node)
            progressed = True

        if not progressed:
            break

    if len(chosen) < count:
        remainder = [node_id for node_id in pool if node_id not in chosen]
        while remainder and len(chosen) < count:
            best_node = max(
                remainder,
                key=lambda node_id: _spread_pick_score(
                    node_id=node_id,
                    chosen=chosen,
                    chosen_local=[],
                    template=template,
                    degrees=degrees,
                    rnd=rnd,
                    weight_mode=weight_mode,
                ),
            )
            chosen.append(best_node)
            remainder.remove(best_node)
    return chosen[:count]


def _group_candidates_by_sector(
    candidates: Sequence[int],
    template: _RoadTemplate,
) -> Dict[Tuple[int, int], List[int]]:
    sectors: Dict[Tuple[int, int], List[int]] = {}
    for node_id in candidates:
        x, y = template.points[node_id]
        col = min(SPREAD_GRID_COLS - 1, max(0, int((x / max(1.0, template.width)) * SPREAD_GRID_COLS)))
        row = min(SPREAD_GRID_ROWS - 1, max(0, int((y / max(1.0, template.height)) * SPREAD_GRID_ROWS)))
        sectors.setdefault((col, row), []).append(node_id)
    return sectors


def _spread_pick_score(
    *,
    node_id: int,
    chosen: Sequence[int],
    chosen_local: Sequence[int],
    template: _RoadTemplate,
    degrees: Dict[int, int],
    rnd: random.Random,
    weight_mode: str,
) -> float:
    point = template.points[node_id]
    global_nearest = min((_pixel_distance(point, template.points[item]) for item in chosen), default=9999.0)
    local_nearest = min((_pixel_distance(point, template.points[item]) for item in chosen_local), default=9999.0)
    degree_bonus = degrees.get(node_id, 0) * (18.0 if weight_mode == "degree" else 7.0)
    center_bias = abs(point[0] - template.width * 0.5) * 0.03 + abs(point[1] - template.height * 0.5) * 0.02
    random_bias = rnd.random() * (10.0 if weight_mode == "mixed" else 3.0)
    return global_nearest * 1.2 + local_nearest * 0.85 + degree_bonus - center_bias + random_bias


def _build_tasks(
    scale,
    graph: WeightedGraph,
    task_nodes: Sequence[int],
    vehicles: Dict[int, Vehicle],
    allow_collaboration: bool,
    rnd: random.Random,
) -> List[Task]:
    tasks: List[Task] = []
    caps = sorted((vehicle.capacity for vehicle in vehicles.values()), reverse=True)
    max_single_cap = caps[0]
    max_pair_cap = caps[0] + (caps[1] if len(caps) > 1 else 0.0)
    task_weight_high = min(scale.max_task_weight, max_single_cap - 0.3)
    collab_task_count = 0
    collab_weight_low = max_single_cap + 0.2
    collab_weight_high = min(scale.max_task_weight, max_pair_cap - 0.2)
    if allow_collaboration and collab_weight_high > collab_weight_low:
        collab_ratio = _local_map_collab_ratio(scale.name)
        collab_task_count = max(1, int(scale.tasks * collab_ratio))

    release_bucket = {"small": 4, "medium": 6, "large": 8}[scale.name]
    jitter = max(2, int(scale.horizon * 0.03))
    peak_count = max(3, scale.tasks // 18)
    release_upper = int(scale.horizon * (0.80 if scale.name == "small" else 1.0))
    release_upper = max(release_bucket, min(scale.horizon - 1, release_upper))
    peak_centers = [rnd.randint(0, release_upper) for _ in range(peak_count)]

    for task_id, node_id in enumerate(task_nodes[: scale.tasks]):
        if rnd.random() < 0.65:
            center = rnd.choice(peak_centers)
            release = center + rnd.randint(-jitter, jitter)
        else:
            release = rnd.randint(0, release_upper)
        release = max(0, min(scale.horizon - 1, release))
        release = (release // release_bucket) * release_bucket
        if task_id < collab_task_count:
            weight = round(rnd.uniform(collab_weight_low, collab_weight_high), 2)
        else:
            weight = round(rnd.uniform(1.5, max(1.6, task_weight_high)), 2)
        deadline = release + rnd.randint(65, 190)
        node = graph.nodes[node_id]
        tasks.append(
            Task(
                task_id=task_id,
                release_time=release,
                node_id=node_id,
                x=node.x,
                y=node.y,
                weight=weight,
                deadline=deadline,
            )
        )
    _ensure_small_map_mid_releases(
        tasks=tasks,
        scale_name=scale.name,
        horizon=scale.horizon,
        release_bucket=release_bucket,
    )
    return tasks


def _local_map_collab_ratio(scale_name: str) -> float:
    if scale_name == "small":
        return 0.12
    if scale_name == "medium":
        return 0.20
    return 0.16


def _ensure_small_map_mid_releases(
    tasks: List[Task],
    scale_name: str,
    horizon: int,
    release_bucket: int,
) -> None:
    if scale_name != "small" or len(tasks) < 6:
        return

    window_start = max(0, int(horizon * 0.35))
    window_end = min(horizon - 1, int(horizon * 0.62))
    window_start = (window_start // release_bucket) * release_bucket
    window_end = (window_end // release_bucket) * release_bucket
    if window_end <= window_start + release_bucket:
        return

    center = (window_start + window_end) / 2.0
    movable = [task for task in tasks if not (window_start <= task.release_time <= window_end)]
    movable.sort(key=lambda item: (abs(item.release_time - center), item.release_time), reverse=True)
    if not movable:
        return

    max_mid_gap = max(release_bucket * 6, 24)
    moved = 0
    next_idx = 0
    used = {task.release_time for task in tasks}

    while moved < 3 and next_idx < len(movable):
        middle_releases = sorted(
            task.release_time for task in tasks if window_start <= task.release_time <= window_end
        )
        anchors = [window_start, *middle_releases, window_end]
        gap_pairs = [(anchors[idx], anchors[idx + 1]) for idx in range(len(anchors) - 1)]
        left, right = max(gap_pairs, key=lambda pair: pair[1] - pair[0])
        if right - left <= max_mid_gap:
            break

        candidate = left + int((right - left) * 0.5)
        candidate = (candidate // release_bucket) * release_bucket
        if candidate <= left:
            candidate = left + release_bucket
        if candidate >= right:
            candidate = right - release_bucket

        while candidate in used and candidate + release_bucket < right:
            candidate += release_bucket
        while candidate in used and candidate - release_bucket > left:
            candidate -= release_bucket
        if candidate in used or candidate <= left or candidate >= right:
            break

        task = movable[next_idx]
        next_idx += 1
        slack = max(65, task.deadline - task.release_time)
        task.release_time = candidate
        task.deadline = candidate + slack
        used.add(candidate)
        moved += 1


def _apply_map_scale_tuning(
    scale_name: str,
    tasks: List[Task],
    vehicles: Dict[int, Vehicle],
    stations: Dict[int, ChargingStation],
) -> None:
    tuning = MAP_SCALE_TUNING.get(scale_name)
    if not tuning:
        return

    deadline_add = int(tuning.get("deadline_add", 0) or 0)
    speed_mul = float(tuning.get("speed_mul", 1.0) or 1.0)
    charge_rate_mul = float(tuning.get("station_charge_rate_mul", 1.0) or 1.0)
    ports_add = int(tuning.get("station_ports_add", 0) or 0)

    if deadline_add:
        for task in tasks:
            task.deadline += deadline_add

    if abs(speed_mul - 1.0) > 1e-9:
        for vehicle in vehicles.values():
            vehicle.speed *= speed_mul

    if abs(charge_rate_mul - 1.0) > 1e-9 or ports_add:
        for station in stations.values():
            station.charge_rate *= charge_rate_mul
            if ports_add:
                station.ports = max(1, station.ports + ports_add)
                station._port_available_times = [0.0 for _ in range(station.ports)]


def _pixel_to_lnglat(px: int, py: int, width: int, height: int) -> Tuple[float, float]:
    lng = MAP_BOUNDS["west"] + (MAP_BOUNDS["east"] - MAP_BOUNDS["west"]) * (px / max(1, width - 1))
    lat = MAP_BOUNDS["north"] - (MAP_BOUNDS["north"] - MAP_BOUNDS["south"]) * (py / max(1, height - 1))
    return lng, lat


def _line_road_ratio(
    a: Tuple[int, int],
    b: Tuple[int, int],
    mask: List[List[bool]],
    width: int,
    height: int,
) -> float:
    distance = _pixel_distance(a, b)
    steps = max(4, int(distance // 4))
    hits = 0
    for idx in range(steps + 1):
        ratio = idx / max(1, steps)
        x = int(round(a[0] + (b[0] - a[0]) * ratio))
        y = int(round(a[1] + (b[1] - a[1]) * ratio))
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        if mask[y][x]:
            hits += 1
    return hits / float(steps + 1)


def _pixel_distance(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    rad = math.pi / 180.0
    p1 = lat1 * rad
    p2 = lat2 * rad
    dp = (lat2 - lat1) * rad
    dl = (lng2 - lng1) * rad
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 6371.0 * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1.0 - a)))


def _template_cache_path(scale_name: str) -> Path:
    return LOCAL_CACHE_DIR / f"panyu_template_{scale_name}.json"


def _load_template_from_disk(scale_name: str) -> _RoadTemplate | None:
    path = _template_cache_path(scale_name)
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("cache_version", 0) or 0) != LOCAL_TEMPLATE_CACHE_VERSION:
        return None

    points_raw = payload.get("points")
    edges_raw = payload.get("edges")
    width = int(payload.get("width", 0) or 0)
    height = int(payload.get("height", 0) or 0)
    if width <= 0 or height <= 0 or not isinstance(points_raw, list) or not isinstance(edges_raw, list):
        return None

    points: List[Tuple[int, int]] = []
    for item in points_raw:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        points.append((int(item[0]), int(item[1])))

    edges: List[Tuple[int, int]] = []
    for item in edges_raw:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        src = int(item[0])
        dst = int(item[1])
        if src == dst:
            continue
        edges.append((min(src, dst), max(src, dst)))

    if len(points) < 16 or len(edges) < 16:
        return None
    return _RoadTemplate(width=width, height=height, points=points, edges=edges)


def _save_template_to_disk(scale_name: str, template: _RoadTemplate) -> None:
    LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "cache_version": LOCAL_TEMPLATE_CACHE_VERSION,
        "width": template.width,
        "height": template.height,
        "points": [[x, y] for x, y in template.points],
        "edges": [[src, dst] for src, dst in template.edges],
    }
    _template_cache_path(scale_name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
