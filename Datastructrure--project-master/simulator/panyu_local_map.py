from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from PIL import Image

from .graph import WeightedGraph
from .models import ChargingStation, SimulationConfig, Task, Vehicle
from .simulation import SCENARIO_SCALES, ScenarioData, _build_weather_rush_windows


ASSETS_DIR = Path(__file__).with_name("web") / "assets"
BASEMAP_PATH = ASSETS_DIR / "panyu-basemap.png"
ROADMASK_PATH = ASSETS_DIR / "panyu-roadmask.png"
MAP_BOUNDS = {
    "west": 113.15,
    "east": 113.70,
    "south": 22.86,
    "north": 23.24,
}
ROAD_THRESHOLD = 208
PROCESS_MAX_WIDTH = 960
_TEMPLATE_CACHE: Dict[str, "_RoadTemplate"] = {}


@dataclass(frozen=True)
class _RoadTemplate:
    width: int
    height: int
    points: List[Tuple[int, int]]
    edges: List[Tuple[int, int]]


def has_panyu_local_map_assets() -> bool:
    return BASEMAP_PATH.exists() and BASEMAP_PATH.is_file()


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

    scale = SCENARIO_SCALES[scale_name]
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
            speed=rnd.uniform(1.35, 1.95),
            energy_per_distance=rnd.uniform(0.82, 1.06),
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

    explicit_mask = ROADMASK_PATH.exists()
    image = Image.open(BASEMAP_PATH if not explicit_mask else ROADMASK_PATH).convert("RGB")
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
    target_x = template.width * 0.60
    target_y = template.height * 0.30
    return min(
        range(len(template.points)),
        key=lambda node_id: (
            abs(template.points[node_id][0] - target_x)
            + abs(template.points[node_id][1] - target_y)
            - degrees.get(node_id, 0) * 12.0
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
    chosen: List[int] = []
    pool = list(candidates)
    if len(pool) <= count:
        rnd.shuffle(pool)
        return pool[:count]

    while pool and len(chosen) < count:
        best_idx = 0
        best_score = None
        for idx, node_id in enumerate(pool):
            x, y = template.points[node_id]
            nearest = min((_pixel_distance((x, y), template.points[item]) for item in chosen), default=9999.0)
            degree_bonus = degrees.get(node_id, 0) * (20.0 if weight_mode == "degree" else 10.0)
            center_bias = abs(x - template.width * 0.55) * 0.08 + abs(y - template.height * 0.58) * 0.04
            random_bias = rnd.random() * (28.0 if weight_mode == "mixed" else 8.0)
            score = nearest + degree_bonus - center_bias + random_bias
            if best_score is None or score > best_score:
                best_score = score
                best_idx = idx
        chosen.append(pool.pop(best_idx))
    return chosen


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
        collab_ratio = 0.08 if scale.name == "small" else 0.16
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
    return tasks


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
