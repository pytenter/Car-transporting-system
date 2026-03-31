from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .graph import WeightedGraph
from .models import ChargingStation, SimulationConfig, Task, Vehicle
from .simulation import SCENARIO_SCALES, ScenarioData, _build_weather_rush_windows


AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"
AMAP_DISTRICT_URL = "https://restapi.amap.com/v3/config/district"
AMAP_DIRECTION_URL = "https://restapi.amap.com/v3/direction/driving"
AMAP_TIMEOUT_SEC = 12.0
AMAP_MAX_WAYPOINTS = 16
DEFAULT_CITY_NAME = "上海"
DEFAULT_DISTRICT_NAME = ""

DEPOT_KEYWORDS = ("物流园", "配送中心", "仓储中心", "工业园", "产业园")
TASK_KEYWORDS = (
    "产业园",
    "物流园",
    "写字楼",
    "商场",
    "批发市场",
    "电商产业园",
    "园区",
    "仓库",
)
STATION_KEYWORDS = ("充电站", "汽车充电站", "新能源充电站", "充电桩")

ROAD_DISTANCE_FACTOR = 1.18
OFFLINE_CACHE_DIR = Path(__file__).with_name("offline_cache")
OFFLINE_SCOPE_CITY = "广州市"
OFFLINE_SCOPE_DISTRICT = "番禺区"
OFFLINE_CACHE_SCHEMA_VERSION = 1
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

_ROUTE_CACHE: Dict[tuple[tuple[float, float], ...], dict] = {}


@dataclass(frozen=True)
class AmapPoi:
    poi_id: str
    name: str
    address: str
    lng: float
    lat: float
    typecode: str


@dataclass(frozen=True)
class AmapScope:
    city_name: str
    district_name: str
    search_code: str
    display_name: str


def has_amap_key() -> bool:
    return bool(_get_amap_key())


def is_fixed_offline_scope(city_name: str, district_name: str) -> bool:
    return (
        str(city_name or "").strip() == OFFLINE_SCOPE_CITY
        and str(district_name or "").strip() == OFFLINE_SCOPE_DISTRICT
    )


def has_offline_cached_panyu_data() -> bool:
    return any(_offline_scenario_path(scale_name).exists() for scale_name in SCENARIO_SCALES.keys())


def load_offline_route_cache(scale_name: str) -> Dict[str, dict]:
    path = _offline_routes_path(scale_name)
    payload = _read_offline_payload(path)
    if payload is None:
        return {}
    routes = payload.get("routes")
    if not isinstance(routes, dict):
        return {}

    normalized: Dict[str, dict] = {}
    for route_key, item in routes.items():
        if not isinstance(route_key, str) or not isinstance(item, dict):
            continue
        coordinates = _normalize_coordinate_list(item.get("coordinates"))
        if len(coordinates) < 2:
            continue
        normalized[route_key] = {
            "coordinates": coordinates,
            "distance_km": _safe_float(item.get("distance_km")),
            "duration_min": _safe_float(item.get("duration_min")),
        }
    return normalized


def cache_offline_route_geometry(
    scale_name: str,
    route_nodes: Sequence[int],
    coordinates: Sequence[Sequence[float]],
    *,
    distance_km: float = 0.0,
    duration_min: float = 0.0,
) -> bool:
    route_key = _offline_route_key(route_nodes)
    normalized = _normalize_coordinate_list(coordinates)
    if len(normalized) < 2 or not route_key:
        return False

    path = _offline_routes_path(scale_name)
    payload = _read_offline_payload(path) or _build_offline_route_payload(scale_name)
    routes = payload.setdefault("routes", {})
    if not isinstance(routes, dict):
        routes = {}
        payload["routes"] = routes
    routes[route_key] = {
        "coordinates": normalized,
        "distance_km": float(distance_km or 0.0),
        "duration_min": float(duration_min or 0.0),
    }
    _write_offline_payload(path, payload)
    return True


def load_offline_scenario(
    scale_name: str,
    seed: int,
    allow_collaboration: bool = False,
    weather_mode: str = "normal",
) -> ScenarioData | None:
    path = _offline_scenario_path(scale_name)
    payload = _read_offline_payload(path)
    if payload is None:
        return None

    nodes_payload = payload.get("nodes")
    tasks_payload = payload.get("tasks")
    vehicles_payload = payload.get("vehicles")
    stations_payload = payload.get("stations")
    config_payload = payload.get("config")
    if not all(isinstance(item, list) for item in (nodes_payload, tasks_payload, vehicles_payload, stations_payload)):
        return None
    if not isinstance(config_payload, dict):
        return None

    scale = SCENARIO_SCALES.get(scale_name)
    if scale is None:
        return None

    graph = WeightedGraph()
    for row in nodes_payload:
        if not isinstance(row, dict):
            continue
        graph.add_node(
            node_id=int(row.get("node_id", 0)),
            x=float(row.get("x", 0.0)),
            y=float(row.get("y", 0.0)),
        )

    edges_payload = payload.get("edges")
    if isinstance(edges_payload, list):
        for row in edges_payload:
            if not isinstance(row, dict):
                continue
            graph.add_edge(
                int(row.get("a", 0)),
                int(row.get("b", 0)),
                float(row.get("distance", 0.0)),
            )
    else:
        node_ids = sorted(graph.nodes.keys())
        for idx, src in enumerate(node_ids):
            for dst in node_ids[idx + 1 :]:
                a = graph.nodes[src]
                b = graph.nodes[dst]
                distance = max(0.15, _haversine_km(a.x, a.y, b.x, b.y) * ROAD_DISTANCE_FACTOR)
                graph.add_edge(src, dst, distance)

    tasks: List[Task] = []
    for row in tasks_payload:
        if not isinstance(row, dict):
            continue
        tasks.append(
            Task(
                task_id=int(row.get("task_id", 0)),
                release_time=int(row.get("release_time", 0)),
                node_id=int(row.get("node_id", 0)),
                x=float(row.get("x", 0.0)),
                y=float(row.get("y", 0.0)),
                weight=float(row.get("weight", 0.0)),
                deadline=int(row.get("deadline", 0)),
            )
        )

    vehicles: Dict[int, Vehicle] = {}
    for row in vehicles_payload:
        if not isinstance(row, dict):
            continue
        vehicle_id = int(row.get("vehicle_id", 0))
        vehicles[vehicle_id] = Vehicle(
            vehicle_id=vehicle_id,
            capacity=float(row.get("capacity", 0.0)),
            battery_capacity=float(row.get("battery_capacity", 0.0)),
            speed=float(row.get("speed", 0.0)),
            energy_per_distance=float(row.get("energy_per_distance", 0.0)),
            current_node=int(row.get("current_node", 0)),
            battery=float(row.get("battery", 0.0)),
            available_time=float(row.get("available_time", 0.0)),
        )

    stations: Dict[int, ChargingStation] = {}
    for row in stations_payload:
        if not isinstance(row, dict):
            continue
        station_id = int(row.get("station_id", 0))
        stations[station_id] = ChargingStation(
            station_id=station_id,
            node_id=int(row.get("node_id", 0)),
            charge_rate=float(row.get("charge_rate", 0.0)),
            ports=int(row.get("ports", 1)),
        )

    node_meta_payload = payload.get("node_meta") or {}
    node_meta = {
        int(node_id): dict(meta)
        for node_id, meta in node_meta_payload.items()
        if isinstance(meta, dict)
    }
    cached_allow_collaboration = bool(config_payload.get("allow_collaboration", allow_collaboration))
    effective_allow_collaboration = bool(allow_collaboration or cached_allow_collaboration)
    rnd = random.Random(seed)
    config = SimulationConfig(
        name=str(config_payload.get("name", scale_name)),
        seed=seed,
        horizon=int(config_payload.get("horizon", scale.horizon)),
        depot_node=int(config_payload.get("depot_node", 0)),
        service_time=float(config_payload.get("service_time", 3.8)),
        overtime_penalty=float(config_payload.get("overtime_penalty", 70.0)),
        unserved_penalty=float(config_payload.get("unserved_penalty", 60.0)),
        allow_collaboration=effective_allow_collaboration,
        min_battery_reserve_ratio=float(config_payload.get("min_battery_reserve_ratio", 0.30)),
        task_end_target_ratio=float(config_payload.get("task_end_target_ratio", 0.55)),
        idle_recharge_trigger_ratio=float(config_payload.get("idle_recharge_trigger_ratio", 0.55)),
        idle_recharge_target_ratio=float(config_payload.get("idle_recharge_target_ratio", 0.90)),
        allow_depot_charging=bool(config_payload.get("allow_depot_charging", True)),
        depot_charge_rate=float(config_payload.get("depot_charge_rate", 7.2)),
        depot_charge_ports=int(config_payload.get("depot_charge_ports", 4)),
        rush_windows=_build_weather_rush_windows(scale=scale, rnd=rnd, weather_mode=weather_mode),
        weather_mode=weather_mode,
        map_mode="amap",
        city_name=OFFLINE_SCOPE_CITY,
        district_name=OFFLINE_SCOPE_DISTRICT,
        route_provider="offline_panyu",
    )

    tasks.sort(key=lambda item: (item.release_time, item.task_id))
    scenario = ScenarioData(graph=graph, tasks=tasks, vehicles=vehicles, stations=stations, config=config, node_meta=node_meta)
    if is_fixed_offline_scope(scope.city_name, scope.district_name):
        save_offline_scenario(scale_name, scenario)
    return scenario


def build_amap_scenario(
    scale_name: str,
    seed: int,
    allow_collaboration: bool = False,
    weather_mode: str = "normal",
    city_name: str = DEFAULT_CITY_NAME,
    district_name: str = DEFAULT_DISTRICT_NAME,
) -> ScenarioData:
    if is_fixed_offline_scope(city_name, district_name):
        cached = load_offline_scenario(
            scale_name=scale_name,
            seed=seed,
            allow_collaboration=allow_collaboration,
            weather_mode=weather_mode,
        )
        if cached is not None:
            return cached
    if not has_amap_key():
        raise RuntimeError("地图模式需要配置高德 Web 服务 Key。请设置环境变量 AMAP_KEY。")
    if scale_name not in SCENARIO_SCALES:
        raise ValueError(f"Unknown scale: {scale_name}")

    scale = SCENARIO_SCALES[scale_name]
    rnd = random.Random(seed)
    city = (city_name or DEFAULT_CITY_NAME).strip() or DEFAULT_CITY_NAME
    district = (district_name or DEFAULT_DISTRICT_NAME).strip()
    scope = _resolve_scope(city=city, district=district)

    depot_pool = _collect_city_pois(scope=scope, keywords=DEPOT_KEYWORDS, target_count=18, seed=seed + 11)
    task_pool = _collect_city_pois(scope=scope, keywords=TASK_KEYWORDS, target_count=max(scale.tasks * 2, 60), seed=seed + 29)
    station_pool = _collect_city_pois(
        scope=scope,
        keywords=STATION_KEYWORDS,
        target_count=max(scale.stations * 4, 24),
        seed=seed + 41,
    )

    depot_poi = _pick_distinct_poi(depot_pool, excluded_ids=set(), rnd=rnd)
    if depot_poi is None:
        raise RuntimeError(f"未能从高德地点检索到范围“{scope.display_name}”的车库候选点。")

    excluded_ids = {depot_poi.poi_id}
    selected_task_pois = _pick_many_distinct(task_pool, scale.tasks, excluded_ids, rnd)
    if len(selected_task_pois) < scale.tasks:
        raise RuntimeError(f"范围“{scope.display_name}”可用任务地点不足，当前仅找到 {len(selected_task_pois)} 个。")

    selected_station_pois = _pick_many_distinct(station_pool, scale.stations, excluded_ids, rnd)
    if len(selected_station_pois) < scale.stations:
        selected_station_pois.extend(_pick_many_distinct(task_pool, scale.stations - len(selected_station_pois), excluded_ids, rnd))
    if len(selected_station_pois) < scale.stations:
        raise RuntimeError(f"范围“{scope.display_name}”可用充电站地点不足，当前仅找到 {len(selected_station_pois)} 个。")

    all_places = [depot_poi, *selected_task_pois, *selected_station_pois]
    graph = WeightedGraph()
    node_meta: Dict[int, dict] = {}

    for node_id, poi in enumerate(all_places):
        graph.add_node(node_id=node_id, x=poi.lng, y=poi.lat)
        node_meta[node_id] = {
            "name": poi.name,
            "address": poi.address,
            "typecode": poi.typecode,
            "lng": poi.lng,
            "lat": poi.lat,
        }

    for src in range(len(all_places)):
        for dst in range(src + 1, len(all_places)):
            a = all_places[src]
            b = all_places[dst]
            distance = max(0.15, _haversine_km(a.lng, a.lat, b.lng, b.lat) * ROAD_DISTANCE_FACTOR)
            graph.add_edge(src, dst, distance)

    depot_node = 0
    task_node_ids = list(range(1, 1 + len(selected_task_pois)))
    station_node_ids = list(range(1 + len(selected_task_pois), len(all_places)))

    stations: Dict[int, ChargingStation] = {}
    for station_id, node_id in enumerate(station_node_ids):
        charge_rate = rnd.uniform(3.6, 6.6)
        ports = rnd.randint(1, 4)
        stations[station_id] = ChargingStation(
            station_id=station_id,
            node_id=node_id,
            charge_rate=charge_rate,
            ports=ports,
        )

    vehicles: Dict[int, Vehicle] = {}
    for vehicle_id in range(scale.vehicles):
        battery_capacity = rnd.uniform(130.0, 220.0)
        vehicles[vehicle_id] = Vehicle(
            vehicle_id=vehicle_id,
            capacity=rnd.uniform(9.5, 16.0),
            battery_capacity=battery_capacity,
            speed=rnd.uniform(1.4, 2.1),
            # Real geographic routes in map mode are longer than the synthetic graph's
            # abstract edges, so calibrate energy intensity downward to avoid
            # systematically over-penalizing map-mode feasibility.
            energy_per_distance=rnd.uniform(0.82, 1.08) * MAP_ENERGY_CALIBRATION_FACTOR,
            current_node=depot_node,
            battery=battery_capacity * 0.90,
        )

    tasks: List[Task] = []
    caps = sorted((vehicle.capacity for vehicle in vehicles.values()), reverse=True)
    max_single_cap = caps[0]
    max_pair_cap = caps[0] + (caps[1] if len(caps) > 1 else 0.0)
    task_weight_high = min(scale.max_task_weight, max_single_cap - 0.3)
    collab_task_count = 0
    collab_weight_low = max_single_cap + 0.2
    collab_weight_high = min(scale.max_task_weight, max_pair_cap - 0.2)
    if allow_collaboration and collab_weight_high > collab_weight_low:
        collab_ratio = _amap_collab_ratio(scale.name)
        collab_task_count = max(1, int(scale.tasks * collab_ratio))

    release_bucket = {"small": 4, "medium": 6, "large": 8}[scale.name]
    jitter = max(2, int(scale.horizon * 0.03))
    peak_count = max(3, scale.tasks // 18)
    release_upper = int(scale.horizon * (0.80 if scale.name == "small" else 1.0))
    release_upper = max(release_bucket, min(scale.horizon - 1, release_upper))
    peak_centers = [rnd.randint(0, release_upper) for _ in range(peak_count)]

    for task_id, node_id in enumerate(task_node_ids[: scale.tasks]):
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
    _apply_map_scale_tuning(scale.name, tasks, vehicles, stations)
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
        map_mode="amap",
        city_name=scope.city_name,
        district_name=scope.district_name,
        route_provider="amap",
    )

    tasks.sort(key=lambda item: (item.release_time, item.task_id))
    return ScenarioData(graph=graph, tasks=tasks, vehicles=vehicles, stations=stations, config=config, node_meta=node_meta)


def _amap_collab_ratio(scale_name: str) -> float:
    if scale_name == "small":
        return 0.18
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


def fetch_route_geometry(waypoints: Sequence[Sequence[float]], strategy: str = "4") -> dict:
    if not has_amap_key():
        raise RuntimeError("路线规划需要配置环境变量 AMAP_KEY。")
    pts = _normalize_waypoints(waypoints)
    if len(pts) < 2:
        raise ValueError("waypoints 至少需要 2 个点。")

    cache_key = tuple(pts)
    cached = _ROUTE_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    trimmed = list(pts)
    if len(trimmed) > AMAP_MAX_WAYPOINTS + 2:
        inner = trimmed[1:-1]
        keep = AMAP_MAX_WAYPOINTS
        step = max(1, math.ceil(len(inner) / keep))
        inner = inner[::step][:keep]
        trimmed = [trimmed[0], *inner, trimmed[-1]]

    params: Dict[str, str] = {
        "key": _get_amap_key(),
        "origin": f"{trimmed[0][0]},{trimmed[0][1]}",
        "destination": f"{trimmed[-1][0]},{trimmed[-1][1]}",
        "strategy": str(strategy or "4"),
        "extensions": "base",
        "output": "json",
    }
    if len(trimmed) > 2:
        params["waypoints"] = ";".join(f"{lng},{lat}" for lng, lat in trimmed[1:-1])

    payload = _amap_request(AMAP_DIRECTION_URL, params)
    if str(payload.get("status")) != "1":
        raise RuntimeError(str(payload.get("info") or "高德路线规划失败"))

    route = ((payload.get("route") or {}).get("paths") or [{}])[0]
    steps = route.get("steps") or []
    coordinates: List[List[float]] = []
    for step in steps:
        polyline = step.get("polyline")
        if not isinstance(polyline, str):
            continue
        for segment in polyline.split(";"):
            text = segment.strip()
            if not text or "," not in text:
                continue
            lng_text, lat_text = text.split(",", 1)
            point = [round(float(lng_text), 6), round(float(lat_text), 6)]
            if coordinates and coordinates[-1] == point:
                continue
            coordinates.append(point)

    if len(coordinates) < 2:
        coordinates = [[lng, lat] for lng, lat in trimmed]

    result = {
        "provider": "amap",
        "coordinates": coordinates,
        "distance_km": _safe_float(route.get("distance")) / 1000.0,
        "duration_min": _safe_float(route.get("duration")) / 60.0,
        "strategy": str(strategy or "4"),
    }
    _ROUTE_CACHE[cache_key] = dict(result)
    return result


def _resolve_scope(city: str, district: str) -> AmapScope:
    city_clean = (city or DEFAULT_CITY_NAME).strip() or DEFAULT_CITY_NAME
    district_clean = (district or DEFAULT_DISTRICT_NAME).strip()
    payload = _amap_request(
        AMAP_DISTRICT_URL,
        {
            "key": _get_amap_key(),
            "keywords": city_clean,
            "subdistrict": "1",
            "extensions": "base",
            "output": "json",
        },
    )
    if str(payload.get("status")) != "1":
        raise RuntimeError(str(payload.get("info") or f"高德行政区解析失败: {city_clean}"))

    city_items = [item for item in (payload.get("districts") or []) if isinstance(item, dict)]
    city_match = _pick_admin_match(city_items, city_clean)
    city_name_resolved = str((city_match or {}).get("name") or city_clean).strip() or city_clean
    city_adcode = str((city_match or {}).get("adcode") or "").strip()

    if not district_clean:
        return AmapScope(
            city_name=city_name_resolved,
            district_name="",
            search_code=city_adcode or city_clean,
            display_name=city_name_resolved,
        )

    children = [item for item in ((city_match or {}).get("districts") or []) if isinstance(item, dict)]
    district_match = _pick_admin_match(children, district_clean)
    if district_match is not None:
        district_name_resolved = str(district_match.get("name") or district_clean).strip() or district_clean
        district_adcode = str(district_match.get("adcode") or "").strip()
        if district_adcode:
            return AmapScope(
                city_name=city_name_resolved,
                district_name=district_name_resolved,
                search_code=district_adcode,
                display_name=f"{city_name_resolved}{district_name_resolved}",
            )

    return AmapScope(
        city_name=city_name_resolved,
        district_name=district_clean,
        search_code=f"{city_name_resolved}{district_clean}",
        display_name=f"{city_name_resolved}{district_clean}",
    )


def _pick_admin_match(items: Sequence[dict], target_name: str) -> dict | None:
    target = str(target_name or "").strip()
    if not target:
        return items[0] if items else None
    normalized_target = _normalize_admin_name(target)

    exact_matches = []
    normalized_matches = []
    fuzzy_matches = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        normalized_name = _normalize_admin_name(name)
        if name == target:
            exact_matches.append(item)
            continue
        if normalized_name and normalized_name == normalized_target:
            normalized_matches.append(item)
            continue
        if target in name or name in target or (normalized_target and normalized_target in normalized_name):
            fuzzy_matches.append(item)

    if exact_matches:
        return exact_matches[0]
    if normalized_matches:
        return normalized_matches[0]
    if fuzzy_matches:
        return fuzzy_matches[0]
    return items[0] if items else None


def _normalize_admin_name(value: str) -> str:
    text = str(value or "").strip().replace(" ", "")
    suffixes = ["特别行政区", "自治州", "自治县", "开发区", "高新区", "新区", "城区", "地区", "盟", "市", "区", "县"]
    changed = True
    while changed and text:
        changed = False
        for suffix in suffixes:
            if text.endswith(suffix) and len(text) > len(suffix):
                text = text[: -len(suffix)]
                changed = True
                break
    return text


def _collect_city_pois(scope: AmapScope, keywords: Iterable[str], target_count: int, seed: int) -> List[AmapPoi]:
    rnd = random.Random(seed)
    merged: List[AmapPoi] = []
    seen: set[str] = set()
    for keyword in keywords:
        for page in range(1, 5):
            rows = _search_text_pois(scope=scope, keyword=keyword, page=page, offset=25)
            if not rows:
                break
            rnd.shuffle(rows)
            for poi in rows:
                if poi.poi_id in seen:
                    continue
                seen.add(poi.poi_id)
                merged.append(poi)
            if len(rows) < 25 or len(merged) >= target_count:
                break
        if len(merged) >= target_count:
            break
    rnd.shuffle(merged)
    return merged


def _pick_many_distinct(pool: Sequence[AmapPoi], count: int, excluded_ids: set[str], rnd: random.Random) -> List[AmapPoi]:
    chosen: List[AmapPoi] = []
    for poi in list(pool):
        if poi.poi_id in excluded_ids:
            continue
        chosen.append(poi)
        excluded_ids.add(poi.poi_id)
        if len(chosen) >= count:
            break
    rnd.shuffle(chosen)
    return chosen[:count]


def _pick_distinct_poi(pool: Sequence[AmapPoi], excluded_ids: set[str], rnd: random.Random) -> AmapPoi | None:
    candidates = [poi for poi in pool if poi.poi_id not in excluded_ids]
    if not candidates:
        return None
    return rnd.choice(candidates)


def _search_text_pois(scope: AmapScope, keyword: str, page: int, offset: int) -> List[AmapPoi]:
    payload = _amap_request(
        AMAP_PLACE_TEXT_URL,
        {
            "key": _get_amap_key(),
            "city": scope.search_code,
            "keywords": keyword,
            "citylimit": "true",
            "offset": str(offset),
            "page": str(page),
            "extensions": "base",
            "output": "json",
        },
    )
    if str(payload.get("status")) != "1":
        raise RuntimeError(str(payload.get("info") or f"高德地点检索失败: {keyword}"))

    result: List[AmapPoi] = []
    for item in payload.get("pois") or []:
        poi = _parse_poi(item)
        if poi is not None:
            result.append(poi)
    return result


def _parse_poi(item: object) -> AmapPoi | None:
    if not isinstance(item, dict):
        return None
    location = str(item.get("location") or "")
    if "," not in location:
        return None
    lng_text, lat_text = location.split(",", 1)
    try:
        lng = float(lng_text)
        lat = float(lat_text)
    except (TypeError, ValueError):
        return None
    poi_id = str(item.get("id") or "").strip()
    if not poi_id:
        return None
    return AmapPoi(
        poi_id=poi_id,
        name=str(item.get("name") or "未命名地点").strip() or "未命名地点",
        address=str(item.get("address") or "").strip(),
        lng=lng,
        lat=lat,
        typecode=str(item.get("typecode") or "").strip(),
    )


def _amap_request(url: str, params: Dict[str, str]) -> dict:
    req = Request(f"{url}?{urlencode(params)}", headers={"User-Agent": "EVFleetSimulator/1.0"})
    try:
        with urlopen(req, timeout=AMAP_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("高德接口返回无效 JSON")
    return payload


def _normalize_waypoints(waypoints: Sequence[Sequence[float]]) -> List[tuple[float, float]]:
    result: List[tuple[float, float]] = []
    for item in waypoints:
        if len(item) < 2:
            continue
        lng = round(float(item[0]), 6)
        lat = round(float(item[1]), 6)
        point = (lng, lat)
        if result and result[-1] == point:
            continue
        result.append(point)
    return result


def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    rad = math.pi / 180.0
    p1 = lat1 * rad
    p2 = lat2 * rad
    dp = (lat2 - lat1) * rad
    dl = (lng2 - lng1) * rad
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 6371.0 * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1.0 - a)))


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def save_offline_scenario(scale_name: str, scenario: ScenarioData) -> None:
    payload = {
        "schema_version": OFFLINE_CACHE_SCHEMA_VERSION,
        "scope": {
            "city_name": OFFLINE_SCOPE_CITY,
            "district_name": OFFLINE_SCOPE_DISTRICT,
        },
        "scale_name": scale_name,
        "config": {
            "name": scenario.config.name,
            "horizon": scenario.config.horizon,
            "depot_node": scenario.config.depot_node,
            "service_time": scenario.config.service_time,
            "overtime_penalty": scenario.config.overtime_penalty,
            "unserved_penalty": scenario.config.unserved_penalty,
            "allow_collaboration": scenario.config.allow_collaboration,
            "min_battery_reserve_ratio": scenario.config.min_battery_reserve_ratio,
            "task_end_target_ratio": scenario.config.task_end_target_ratio,
            "idle_recharge_trigger_ratio": scenario.config.idle_recharge_trigger_ratio,
            "idle_recharge_target_ratio": scenario.config.idle_recharge_target_ratio,
            "allow_depot_charging": scenario.config.allow_depot_charging,
            "depot_charge_rate": scenario.config.depot_charge_rate,
            "depot_charge_ports": scenario.config.depot_charge_ports,
        },
        "nodes": [
            {
                "node_id": node.node_id,
                "x": node.x,
                "y": node.y,
            }
            for node in sorted(scenario.graph.nodes.values(), key=lambda item: item.node_id)
        ],
        "edges": [
            {
                "a": src,
                "b": dst,
                "distance": distance,
            }
            for src, neighbors in scenario.graph._adj.items()  # pylint: disable=protected-access
            for dst, distance in neighbors
            if src < dst
        ],
        "tasks": [
            {
                "task_id": task.task_id,
                "release_time": task.release_time,
                "node_id": task.node_id,
                "x": task.x,
                "y": task.y,
                "weight": task.weight,
                "deadline": task.deadline,
            }
            for task in scenario.tasks
        ],
        "vehicles": [
            {
                "vehicle_id": vehicle.vehicle_id,
                "capacity": vehicle.capacity,
                "battery_capacity": vehicle.battery_capacity,
                "speed": vehicle.speed,
                "energy_per_distance": vehicle.energy_per_distance,
                "current_node": vehicle.current_node,
                "battery": vehicle.battery,
                "available_time": vehicle.available_time,
            }
            for vehicle in sorted(scenario.vehicles.values(), key=lambda item: item.vehicle_id)
        ],
        "stations": [
            {
                "station_id": station.station_id,
                "node_id": station.node_id,
                "charge_rate": station.charge_rate,
                "ports": station.ports,
            }
            for station in sorted(scenario.stations.values(), key=lambda item: item.station_id)
        ],
        "node_meta": {
            str(node_id): dict(meta)
            for node_id, meta in (scenario.node_meta or {}).items()
            if isinstance(meta, dict)
        },
    }
    _write_offline_payload(_offline_scenario_path(scale_name), payload)


def _offline_scenario_path(scale_name: str) -> Path:
    return OFFLINE_CACHE_DIR / f"scenario_{scale_name}.json"


def _offline_routes_path(scale_name: str) -> Path:
    return OFFLINE_CACHE_DIR / f"routes_{scale_name}.json"


def _offline_route_key(route_nodes: Sequence[int]) -> str:
    return "-".join(str(int(node_id)) for node_id in route_nodes)


def _build_offline_route_payload(scale_name: str) -> dict:
    return {
        "schema_version": OFFLINE_CACHE_SCHEMA_VERSION,
        "scope": {
            "city_name": OFFLINE_SCOPE_CITY,
            "district_name": OFFLINE_SCOPE_DISTRICT,
        },
        "scale_name": scale_name,
        "routes": {},
    }


def _normalize_coordinate_list(coordinates: object) -> List[List[float]]:
    normalized: List[List[float]] = []
    if not isinstance(coordinates, (list, tuple)):
        return normalized
    for item in coordinates:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        point = [round(float(item[0]), 6), round(float(item[1]), 6)]
        if normalized and normalized[-1] == point:
            continue
        normalized.append(point)
    return normalized


def _read_offline_payload(path: Path) -> dict | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("schema_version", 0) or 0) != OFFLINE_CACHE_SCHEMA_VERSION:
        return None
    return payload


def _write_offline_payload(path: Path, payload: dict) -> None:
    OFFLINE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_amap_key() -> str:
    return (os.environ.get("AMAP_KEY") or "").strip()
