from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .graph import WeightedGraph
from .models import ChargingStation, SimulationConfig, Task, Vehicle
from .simulation import SCENARIO_SCALES, ScenarioData, _build_weather_rush_windows


AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"
AMAP_DIRECTION_URL = "https://restapi.amap.com/v3/direction/driving"
AMAP_TIMEOUT_SEC = 12.0
AMAP_MAX_WAYPOINTS = 16
DEFAULT_CITY_NAME = "上海"

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

_ROUTE_CACHE: Dict[tuple[tuple[float, float], ...], dict] = {}


@dataclass(frozen=True)
class AmapPoi:
    poi_id: str
    name: str
    address: str
    lng: float
    lat: float
    typecode: str


def has_amap_key() -> bool:
    return bool(_get_amap_key())


def build_amap_scenario(
    scale_name: str,
    seed: int,
    allow_collaboration: bool = False,
    weather_mode: str = "normal",
    city_name: str = DEFAULT_CITY_NAME,
) -> ScenarioData:
    if not has_amap_key():
        raise RuntimeError("地图模式需要配置高德 Web 服务 Key。请设置环境变量 AMAP_KEY。")
    if scale_name not in SCENARIO_SCALES:
        raise ValueError(f"Unknown scale: {scale_name}")

    scale = SCENARIO_SCALES[scale_name]
    rnd = random.Random(seed)
    city = (city_name or DEFAULT_CITY_NAME).strip() or DEFAULT_CITY_NAME

    depot_pool = _collect_city_pois(city=city, keywords=DEPOT_KEYWORDS, target_count=18, seed=seed + 11)
    task_pool = _collect_city_pois(city=city, keywords=TASK_KEYWORDS, target_count=max(scale.tasks * 2, 60), seed=seed + 29)
    station_pool = _collect_city_pois(
        city=city,
        keywords=STATION_KEYWORDS,
        target_count=max(scale.stations * 4, 24),
        seed=seed + 41,
    )

    depot_poi = _pick_distinct_poi(depot_pool, excluded_ids=set(), rnd=rnd)
    if depot_poi is None:
        raise RuntimeError(f"未能从高德地点检索到城市“{city}”的车库候选点。")

    excluded_ids = {depot_poi.poi_id}
    selected_task_pois = _pick_many_distinct(task_pool, scale.tasks, excluded_ids, rnd)
    if len(selected_task_pois) < scale.tasks:
        raise RuntimeError(f"城市“{city}”可用任务地点不足，当前仅找到 {len(selected_task_pois)} 个。")

    selected_station_pois = _pick_many_distinct(station_pool, scale.stations, excluded_ids, rnd)
    if len(selected_station_pois) < scale.stations:
        selected_station_pois.extend(_pick_many_distinct(task_pool, scale.stations - len(selected_station_pois), excluded_ids, rnd))
    if len(selected_station_pois) < scale.stations:
        raise RuntimeError(f"城市“{city}”可用充电站地点不足，当前仅找到 {len(selected_station_pois)} 个。")

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
            energy_per_distance=rnd.uniform(0.82, 1.08),
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
        collab_ratio = 0.08 if scale.name == "small" else 0.16
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
        city_name=city,
        route_provider="amap",
    )

    tasks.sort(key=lambda item: (item.release_time, item.task_id))
    return ScenarioData(graph=graph, tasks=tasks, vehicles=vehicles, stations=stations, config=config, node_meta=node_meta)


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


def _collect_city_pois(city: str, keywords: Iterable[str], target_count: int, seed: int) -> List[AmapPoi]:
    rnd = random.Random(seed)
    merged: List[AmapPoi] = []
    seen: set[str] = set()
    for keyword in keywords:
        for page in range(1, 5):
            rows = _search_text_pois(city=city, keyword=keyword, page=page, offset=25)
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


def _search_text_pois(city: str, keyword: str, page: int, offset: int) -> List[AmapPoi]:
    payload = _amap_request(
        AMAP_PLACE_TEXT_URL,
        {
            "key": _get_amap_key(),
            "city": city,
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


def _get_amap_key() -> str:
    return (os.environ.get("AMAP_KEY") or "").strip()
