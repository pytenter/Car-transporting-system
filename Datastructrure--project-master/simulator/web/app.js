const SVG_NS = "http://www.w3.org/2000/svg";
const MAP_WIDTH = 1000;
const MAP_HEIGHT = 700;
const MAP_PADDING = 42;
const GEO_TILE_SIZE = 256;
const GEO_MAP_PADDING = 56;
const GEO_TILE_URL_TEMPLATE = "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}";
const GEO_TILE_SUBDOMAINS = ["1", "2", "3", "4"];
const GEO_ROUTE_FETCH_CONCURRENCY = 4;
const OFFLINE_CITY_NAME = "广州市";
const OFFLINE_DISTRICT_NAME = "番禺区";
const OFFLINE_SCOPE_LABEL = `${OFFLINE_CITY_NAME}${OFFLINE_DISTRICT_NAME}`;
const OFFLINE_BASEMAP_URL = "/assets/panyu-basemap.png";
const OFFLINE_ROUTE_PROVIDER = "offline_panyu";
const OFFLINE_BASEMAP_BOUNDS = {
  west: 113.15,
  east: 113.70,
  south: 22.86,
  north: 23.24
};
const REPLAY_SIM_TIME_TO_MS = 78;
/** 连续播放时降低侧栏刷新频率，减轻 DOM 压力，演示更流畅 */
const REPLAY_SIDE_PANEL_THROTTLE_MS = 120;

const VEHICLE_COLORS = [
  "#1F7EDD",
  "#FF6A1A",
  "#E84855",
  "#1FB77B",
  "#FFB221",
  "#0F4C81",
  "#FF8C42",
  "#2B66D9",
  "#C44230",
  "#3AAE95"
];

/** 界面中文：下拉框 value 仍为英文键，便于与后端 API 一致 */
const ALL_OPT = "全部";

const SCALE_ZH = {
  small: "小规模",
  medium: "中规模",
  large: "大规模"
};

const WEATHER_ZH = {
  normal: "晴朗",
  rain: "雨天",
  congestion: "拥堵"
};

const STRATEGY_ZH = {
  nearest_task_first: "最近任务优先",
  max_task_first: "大载重优先",
  urgency_distance: "紧急度-距离综合",
  auction_multi_agent: "多智能体拍卖",
  metaheuristic_sa: "模拟退火",
  reinforcement_q: "Q 学习派单",
  hyper_heuristic_ucb: "超启发式(UCB)",
  static_exact_fullinfo: "静态·全信息(精确解)",
  static_exact_fullinfo_reduced: "静态·全信息(缩减)"
};

const MODE_ZH = {
  dynamic: "动态仿真",
  static_exact_cplex: "静态·CPLEX",
  static_exact_cplex_reduced: "静态·CPLEX(缩减)",
  static_exact_cplex_failed: "静态·CPLEX(失败)",
  static_exact_cplex_reduced_failed: "静态·CPLEX缩减(失败)"
};

const VEHICLE_STATUS_ZH = {
  idle: "空闲",
  charging: "充电中",
  transporting: "运输中"
};

const TASK_STATUS_ZH = {
  pending: "待派发",
  delivering: "执行中",
  done: "已完成",
  unserved: "未完成"
};

function zhScale(value) {
  if (value === "all") {
    return ALL_OPT;
  }
  return SCALE_ZH[value] || String(value ?? "");
}

function zhWeather(value) {
  if (value === "all") {
    return ALL_OPT;
  }
  return WEATHER_ZH[value] || String(value ?? "");
}

function zhStrategy(value) {
  const key = String(value ?? "").trim();
  return STRATEGY_ZH[key] || cleanBenchmarkLabel(key);
}

function zhMode(value) {
  const key = String(value ?? "").trim();
  if (MODE_ZH[key]) {
    return MODE_ZH[key];
  }
  const lower = key.toLowerCase();
  if (lower.includes("static") && lower.includes("failed")) {
    return lower.includes("reduced") ? MODE_ZH.static_exact_cplex_reduced_failed : MODE_ZH.static_exact_cplex_failed;
  }
  if (lower.startsWith("static")) {
    return lower.includes("reduced") ? MODE_ZH.static_exact_cplex_reduced : MODE_ZH.static_exact_cplex;
  }
  if (lower === "dynamic") {
    return MODE_ZH.dynamic;
  }
  return cleanBenchmarkLabel(key);
}

const dom = {
  scaleSelect: document.getElementById("scaleSelect"),
  strategySelect: document.getElementById("strategySelect"),
  seedInput: document.getElementById("seedInput"),
  weatherSelect: document.getElementById("weatherSelect"),
  cityInput: document.getElementById("cityInput"),
  districtInput: document.getElementById("districtInput"),
  collabInput: document.getElementById("collabInput"),
  runBtn: document.getElementById("runBtn"),
  mapModeBtn: document.getElementById("mapModeBtn"),
  compareBtn: document.getElementById("compareBtn"),
  playBtn: document.getElementById("playBtn"),
  pauseBtn: document.getElementById("pauseBtn"),
  stepBtn: document.getElementById("stepBtn"),
  resetBtn: document.getElementById("resetBtn"),
  replaySpeedSelect: document.getElementById("replaySpeedSelect"),
  mapFullscreenBtn: document.getElementById("mapFullscreenBtn"),
  replayProgressFill: document.getElementById("replayProgressFill"),
  replayProgressLabel: document.getElementById("replayProgressLabel"),
  replayProgress: document.querySelector(".replay-progress"),
  mapWrap: document.querySelector(".map-wrap"),
  statusBar: document.getElementById("statusBar"),
  summaryBox: document.getElementById("summaryBox"),
  metricsList: document.getElementById("metricsList"),
  vehicleStatusList: document.getElementById("vehicleStatusList"),
  taskListBox: document.getElementById("taskListBox"),
  rankingList: document.getElementById("rankingList"),
  logBox: document.getElementById("logBox"),
  benchmarkDataset: document.getElementById("benchmarkDataset"),
  benchmarkScenario: document.getElementById("benchmarkScenario"),
  benchmarkMetric: document.getElementById("benchmarkMetric"),
  benchmarkTableScale: document.getElementById("benchmarkTableScale"),
  refreshBenchmarkBtn: document.getElementById("refreshBenchmarkBtn"),
  benchmarkStatus: document.getElementById("benchmarkStatus"),
  benchmarkChart: document.getElementById("benchmarkChart"),
  benchmarkTable: document.getElementById("benchmarkTable"),
  runWeatherStatsBtn: document.getElementById("runWeatherStatsBtn"),
  weatherStatsStatus: document.getElementById("weatherStatsStatus"),
  weatherStatsTable: document.getElementById("weatherStatsTable"),
  weatherStatsScale: document.getElementById("weatherStatsScale"),
  weatherStatsWeather: document.getElementById("weatherStatsWeather"),
  weatherFx: document.getElementById("weatherFx"),
  mapSvg: document.getElementById("mapSvg"),
  geoMapPanel: document.getElementById("geoMapPanel"),
  geoMapMeta: document.getElementById("geoMapMeta"),
  geoMapCloseBtn: document.getElementById("geoMapCloseBtn"),
  geoMapViewport: document.getElementById("geoMapViewport"),
  geoMapStaticBase: document.getElementById("geoMapStaticBase"),
  geoMapTiles: document.getElementById("geoMapTiles"),
  geoMapOverlay: document.getElementById("geoMapOverlay"),
  geoMapLoading: document.getElementById("geoMapLoading"),
  edgesLayer: document.getElementById("edgesLayer"),
  historyLayer: document.getElementById("historyLayer"),
  tasksLayer: document.getElementById("tasksLayer"),
  stationsLayer: document.getElementById("stationsLayer"),
  depotLayer: document.getElementById("depotLayer"),
  activeRouteLayer: document.getElementById("activeRouteLayer"),
  carLayer: document.getElementById("carLayer"),
  geoHistoryLayer: document.getElementById("geoHistoryLayer"),
  geoTasksLayer: document.getElementById("geoTasksLayer"),
  geoStationsLayer: document.getElementById("geoStationsLayer"),
  geoDepotLayer: document.getElementById("geoDepotLayer"),
  geoActiveRouteLayer: document.getElementById("geoActiveRouteLayer"),
  geoCarLayer: document.getElementById("geoCarLayer")
};

const state = {
  meta: null,
  scenario: null,
  summary: null,
  events: [],
  eventIndex: 0,
  playing: false,
  animating: false,
  scoreAcc: 0,
  taskState: new Map(),
  routeHistory: [],
  projection: null,
  nodeMap: new Map(),
  vehicleState: new Map(),
  currentTime: 0,
  recentTaskIds: new Set(),
  completedTaskIds: new Set(),
  lastVehiclePanelPaintAt: 0,
  activeReplayVehicleIds: new Set(),
  benchmarkData: null,
  initialVehicleState: new Map(),
  timelineMissions: [],
  timelineBreakpoints: [],
  replayEndTime: 0,
  replayRafId: null,
  replayLastFrameTs: 0,
  replayLoggedTaskIds: new Set(),
  preDispatchView: false,
  weatherStatsData: null,
  lastSidePanelPaintAt: 0,
  mapReplayEnabled: false,
  geoRouteCache: new Map(),
  geoRoutePending: new Map(),
  geoRouteFailures: new Set(),
  geoView: null,
  geoViewSignature: "",
  geoTilesSignature: "",
  lastMapRouteFailureCount: 0
};

window.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  initialize().catch((err) => {
    setStatus(`初始化失败：${err.message}`, true);
  });
});

function bindEvents() {
  dom.runBtn.addEventListener("click", () => void runSimulation());
  dom.mapModeBtn?.addEventListener("click", () => void runMapSimulation());
  dom.compareBtn.addEventListener("click", () => void compareStrategies());
  dom.playBtn.addEventListener("click", () => void playReplay());
  dom.pauseBtn.addEventListener("click", pauseReplay);
  dom.stepBtn.addEventListener("click", () => void stepReplay());
  dom.resetBtn.addEventListener("click", resetReplay);
  dom.mapFullscreenBtn?.addEventListener("click", () => void toggleMapFullscreen());
  dom.geoMapCloseBtn?.addEventListener("click", hideGeoMapPanel);
  document.addEventListener("keydown", onDemoHotkey);
  window.addEventListener("resize", () => {
    if (!isGeoReplayAvailable()) {
      return;
    }
    state.geoView = null;
    state.geoViewSignature = "";
    state.geoTilesSignature = "";
    renderGeoReplayFrame(state.routeHistory, []);
  });
  dom.refreshBenchmarkBtn.addEventListener("click", () => void loadBenchmarks());
  dom.runWeatherStatsBtn.addEventListener("click", () => void loadWeatherStats());
  dom.weatherSelect.addEventListener("change", () => {
    setWeatherEffect(dom.weatherSelect.value);
  });
  dom.benchmarkDataset.addEventListener("change", () => {
    renderBenchmarkTableScaleOptions();
    renderBenchmarkScenarioOptions();
    renderBenchmarkView();
  });
  dom.benchmarkScenario.addEventListener("change", renderBenchmarkView);
  dom.benchmarkMetric.addEventListener("change", renderBenchmarkView);
  dom.benchmarkTableScale.addEventListener("change", renderBenchmarkView);
  dom.weatherStatsScale.addEventListener("change", () => {
    renderWeatherStatsTable(state.weatherStatsData?.rows || []);
  });
  dom.weatherStatsWeather.addEventListener("change", () => {
    renderWeatherStatsTable(state.weatherStatsData?.rows || []);
  });
}

async function initialize() {
  const meta = await fetchJson("/api/meta");
  state.meta = meta;

  fillSelect(dom.scaleSelect, meta.scales, meta.defaults.scale, zhScale);
  fillSelect(dom.strategySelect, meta.strategies, meta.defaults.strategy, zhStrategy);
  fillSelect(
    dom.weatherSelect,
    meta.weather_modes || ["normal", "rain", "congestion"],
    meta.defaults.weather_mode || "normal",
    zhWeather
  );
  fillSelectByItems(
    dom.weatherStatsScale,
    [{ value: "all", label: ALL_OPT }, ...(meta.scales || []).map((value) => ({ value, label: zhScale(value) }))],
    "all"
  );
  fillSelectByItems(
    dom.weatherStatsWeather,
    [
      { value: "all", label: ALL_OPT },
      ...(meta.weather_modes || ["normal", "rain", "congestion"]).map((value) => ({ value, label: zhWeather(value) }))
    ],
    "all"
  );
  dom.seedInput.value = String(meta.defaults.seed);
  if (dom.cityInput) {
    dom.cityInput.value = OFFLINE_CITY_NAME;
    dom.cityInput.readOnly = true;
    dom.cityInput.title = "当前界面已固定为广州市番禺区";
  }
  if (dom.districtInput) {
    dom.districtInput.value = OFFLINE_DISTRICT_NAME;
    dom.districtInput.readOnly = true;
    dom.districtInput.title = "当前界面已固定为广州市番禺区";
  }
  dom.collabInput.checked = Boolean(meta.defaults.allow_collaboration);
  if (dom.mapModeBtn) {
    dom.mapModeBtn.disabled = !Boolean(meta.map_mode_available);
    dom.mapModeBtn.title = meta.map_mode_available ? "使用高德地图生成真实地点与路线回放" : "未检测到 AMAP_KEY，地图模式不可用";
  }
  setWeatherEffect(dom.weatherSelect.value);
  updateMapModeButton();

  await loadBenchmarks();
  await loadWeatherStats();
  setStatus("状态：请选择参数后点击「运行仿真」");
  updateReplayProgress(0, 0);
}

function fillSelect(el, values, defaultValue, labelFn) {
  el.innerHTML = "";
  const lf = labelFn || ((v) => String(v));
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = lf(value);
    option.selected = value === defaultValue;
    el.appendChild(option);
  });
}

async function loadBenchmarks() {
  dom.benchmarkStatus.textContent = "正在加载基准结果…";
  try {
    const payload = await fetchJson("/api/benchmarks");
    state.benchmarkData = payload;
    renderBenchmarkControls();
    renderBenchmarkView();
  } catch (err) {
    state.benchmarkData = null;
    dom.benchmarkStatus.textContent = `加载失败：${err.message}`;
    dom.benchmarkChart.className = "benchmark-chart empty";
    dom.benchmarkChart.textContent = "无法访问基准数据接口。";
    dom.benchmarkTable.innerHTML = "";
  }
}

function renderBenchmarkControls() {
  const datasets = state.benchmarkData?.datasets || [];
  const metrics = state.benchmarkData?.metrics || [];
  const defaults = state.benchmarkData?.defaults || {};

  if (!datasets.length) {
    dom.benchmarkDataset.innerHTML = "";
    dom.benchmarkScenario.innerHTML = "";
    dom.benchmarkMetric.innerHTML = "";
    dom.benchmarkStatus.textContent = "未在 results/ 目录找到 summary JSON，请先运行 main.py 生成结果。";
    dom.benchmarkChart.className = "benchmark-chart empty";
    dom.benchmarkChart.textContent = "请先在命令行运行基准测试，再点击「刷新数据」。";
    dom.benchmarkTable.innerHTML = "";
    return;
  }

  fillSelectByItems(
    dom.benchmarkDataset,
    datasets.map((item) => ({
      value: item.key,
      label: `${item.label} (${item.row_count})`
    })),
    defaults.dataset_key || datasets[0].key
  );

  fillSelectByItems(
    dom.benchmarkMetric,
    metrics.map((item) => ({
      value: item.id,
      label: item.label
    })),
    defaults.metric || "score"
  );

  renderBenchmarkTableScaleOptions();
  renderBenchmarkScenarioOptions();
}

function renderBenchmarkTableScaleOptions() {
  const dataset = getSelectedBenchmarkDataset();
  const scaleOptions = dataset
    ? Array.from(new Set((dataset.rows || []).map((row) => String(row.scenario || "")))).filter(Boolean).sort((a, b) => a.localeCompare(b))
    : (state.meta?.scales || []);
  const current = dom.benchmarkTableScale.value || "all";
  const options = [{ value: "all", label: ALL_OPT }, ...scaleOptions.map((value) => ({ value, label: zhScale(value) }))];
  const selected = options.some((item) => item.value === current) ? current : "all";
  fillSelectByItems(dom.benchmarkTableScale, options, selected);
}

function renderBenchmarkScenarioOptions() {
  const dataset = getSelectedBenchmarkDataset();
  if (!dataset) {
    dom.benchmarkScenario.innerHTML = "";
    return;
  }

  const values = Array.from(
    new Set((dataset.rows || []).map((row) => String(row.scenario || "all")))
  ).sort((a, b) => a.localeCompare(b));

  const current = dom.benchmarkScenario.value || "all";
  const options = [
    { value: "all", label: ALL_OPT },
    ...values.map((value) => ({ value, label: value === "all" ? ALL_OPT : zhScale(value) }))
  ];
  fillSelectByItems(dom.benchmarkScenario, options, options.some((item) => item.value === current) ? current : "all");
}

function renderBenchmarkView() {
  const dataset = getSelectedBenchmarkDataset();
  if (!dataset) {
    dom.benchmarkStatus.textContent = "未选择基准数据集。";
    dom.benchmarkChart.className = "benchmark-chart empty";
    dom.benchmarkChart.textContent = "暂无数据。";
    dom.benchmarkTable.innerHTML = "";
    return;
  }

  const scenario = dom.benchmarkScenario.value || "all";
  const metricId = dom.benchmarkMetric.value || "score";
  const metricMeta = getBenchmarkMetricMeta(metricId);
  const direction = metricMeta.direction || "desc";

  const filteredRows = (dataset.rows || []).filter((row) => scenario === "all" || row.scenario === scenario);
  if (!filteredRows.length) {
    dom.benchmarkStatus.textContent =
      scenario === "all"
        ? `${dataset.label} 在当前数据集中没有可用行。`
        : `${dataset.label} 在场景「${zhScale(scenario)}」下没有数据行。`;
    dom.benchmarkChart.className = "benchmark-chart empty";
    dom.benchmarkChart.textContent = "当前筛选条件下没有可用数据。";
    dom.benchmarkTable.innerHTML = "";
    return;
  }

  const prepared = prepareBenchmarkRowsForDisplay(dataset, filteredRows, metricId);
  const sorted = [...prepared.rows].sort((a, b) => {
    const va = numberValue(a.__displayMetric);
    const vb = numberValue(b.__displayMetric);
    return direction === "asc" ? va - vb : vb - va;
  });

  const metricValues = sorted.map((row) => numberValue(row.__displayMetric));
  const minVal = Math.min(...metricValues);
  const maxVal = Math.max(...metricValues);
  const span = Math.max(1e-9, maxVal - minVal);

  dom.benchmarkChart.className = "benchmark-chart";
  dom.benchmarkChart.innerHTML = "";
  sorted.forEach((row) => {
    const val = numberValue(row.__displayMetric);
    const ratio =
      direction === "asc"
        ? (maxVal - val) / span
        : (val - minVal) / span;
    const width = 15 + ratio * 85;

    const line = document.createElement("div");
    line.className = "benchmark-row";

    const label = document.createElement("div");
    label.className = "benchmark-label";
    label.textContent = `${zhScale(row.scenario)} | ${zhStrategy(row.strategy)} | ${zhMode(row.mode)}`;

    const track = document.createElement("div");
    track.className = "benchmark-track";
    const fill = document.createElement("div");
    fill.className = `benchmark-fill ${String(row.mode).startsWith("static") ? "static" : "dynamic"}`;
    fill.style.width = `${width}%`;
    track.appendChild(fill);

    const value = document.createElement("div");
    value.className = "benchmark-value";
    value.textContent = formatMetricValue(metricId, val);

    line.appendChild(label);
    line.appendChild(track);
    line.appendChild(value);
    dom.benchmarkChart.appendChild(line);
  });

  renderBenchmarkTable(sorted, metricId);
  const updated = dataset.updated_at ? dataset.updated_at.replace("T", " ") : "未知";
  dom.benchmarkStatus.textContent = `${dataset.label} | 文件=${dataset.filename} | 行数=${filteredRows.length} | 更新=${updated}`;
}

function renderBenchmarkTable(rows, metricId) {
  const tableScale = dom.benchmarkTableScale.value || "all";
  const displayRows = rows.filter((row) => tableScale === "all" || String(row.scenario) === tableScale);

  const table = document.createElement("table");
  table.className = "benchmark-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["场景", "策略", "模式", "指标值", "完成", "未完成", "超时"].forEach((text) => {
    const th = document.createElement("th");
    th.textContent = text;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);

  const tbody = document.createElement("tbody");
  displayRows.forEach((row) => {
    const tr = document.createElement("tr");
    const cells = [
      zhScale(row.scenario),
      zhStrategy(row.strategy),
      zhMode(row.mode),
      formatMetricValue(metricId, numberValue(row.__displayMetric)),
      String(Math.round(numberValue(row.__displayCompleted))),
      String(Math.round(numberValue(row.__displayUnserved))),
      String(Math.round(numberValue(row.__displayOvertime)))
    ];
    cells.forEach((text) => {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  table.appendChild(thead);
  table.appendChild(tbody);
  dom.benchmarkTable.innerHTML = "";
  dom.benchmarkTable.appendChild(table);
}

function fillSelectByItems(el, items, defaultValue) {
  el.innerHTML = "";
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    option.selected = item.value === defaultValue;
    el.appendChild(option);
  });
}

function getSelectedBenchmarkDataset() {
  const datasets = state.benchmarkData?.datasets || [];
  const key = dom.benchmarkDataset.value;
  return datasets.find((item) => item.key === key) || datasets[0] || null;
}

function getBenchmarkMetricMeta(metricId) {
  const metrics = state.benchmarkData?.metrics || [];
  return metrics.find((item) => item.id === metricId) || { id: metricId, label: metricId, direction: "desc" };
}

function prepareBenchmarkRowsForDisplay(_dataset, rows, metricId) {
  return {
    rows: rows.map((row) => ({
      ...row,
      __displayMetric: numberValue(row[metricId]),
      __displayCompleted: Math.max(0, Math.round(numberValue(row.completed))),
      __displayUnserved: Math.max(0, Math.round(numberValue(row.unserved))),
      __displayOvertime: Math.max(0, Math.round(numberValue(row.overtime)))
    }))
  };
}

function numberValue(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function formatMetricValue(metricId, value) {
  if (["completed", "unserved", "overtime"].includes(metricId)) {
    return `${Math.round(value)}`;
  }
  return `${value.toFixed(2)}`;
}

function cleanBenchmarkLabel(value) {
  return String(value ?? "")
    .replace(/reduced/gi, "")
    .replace(/__+/g, "_")
    .replace(/\s{2,}/g, " ")
    .replace(/^[_\-\s|]+/, "")
    .replace(/[_\-\s|]+$/, "");
}

function readCommonPayload() {
  return {
    scale: dom.scaleSelect.value,
    strategy: dom.strategySelect.value,
    seed: Number(dom.seedInput.value),
    allow_collaboration: dom.collabInput.checked,
    weather_mode: dom.weatherSelect.value
  };
}

function readMapPayload() {
  return {
    ...readCommonPayload(),
    map_mode: true,
    city_name: OFFLINE_CITY_NAME,
    district_name: OFFLINE_DISTRICT_NAME
  };
}

function isGeoScenario() {
  const mode = String(state.scenario?.map_mode || "");
  return Boolean(state.scenario && (mode === "amap" || mode === "local_mask"));
}

function isGeoReplayAvailable() {
  return Boolean(state.mapReplayEnabled && isGeoScenario());
}

function updateMapModeButton() {
  if (!dom.mapModeBtn) {
    return;
  }
  const active = isGeoReplayAvailable();
  dom.mapModeBtn.textContent = active ? "地图模式中" : "地图模式";
  dom.mapModeBtn.classList.toggle("active", active);
  dom.mapModeBtn.setAttribute("aria-pressed", active ? "true" : "false");
}

function showGeoMapPanel() {
  state.mapReplayEnabled = true;
  dom.mapWrap?.classList.add("geo-active");
  if (dom.geoMapPanel) {
    dom.geoMapPanel.hidden = false;
    dom.geoMapPanel.setAttribute("aria-hidden", "false");
  }
  updateMapModeButton();
}

function hideGeoMapPanel() {
  state.mapReplayEnabled = false;
  dom.mapWrap?.classList.remove("geo-active");
  if (dom.geoMapPanel) {
    dom.geoMapPanel.hidden = true;
    dom.geoMapPanel.setAttribute("aria-hidden", "true");
  }
  updateMapModeButton();
}

function setGeoLoading(message = "", visible = true) {
  if (!dom.geoMapLoading) {
    return;
  }
  dom.geoMapLoading.hidden = !visible;
  if (message) {
    dom.geoMapLoading.textContent = message;
  }
}

function refreshCurrentReplayFrame() {
  if (!state.scenario) {
    return;
  }
  renderReplayAt(state.currentTime, {
    appendLogs: false,
    initialSummary: state.currentTime <= 1e-9,
    preDispatch: state.preDispatchView,
    throttleSidePanels: true
  });
}

async function runMapSimulation() {
  if (!state.meta?.map_mode_available) {
    setStatus("状态：地图模式不可用，请先配置 AMAP_KEY", true);
    return;
  }

  const payload = readMapPayload();
  const scopeLabel = payload.district_name ? `${payload.city_name}${payload.district_name}` : payload.city_name;
  showGeoMapPanel();
  setGeoLoading("正在生成地图场景...", true);
  setStatus(`状态：正在生成 ${scopeLabel} 的高德地图仿真...`);

  try {
    const data = await postJson("/api/run", payload);
    hydrateRunData(data);
    showGeoMapPanel();
    await ensureGeoReplayReady();
    renderStaticMapBase();
    renderReplayAt(0, { appendLogs: false, initialSummary: true, preDispatch: true });
    dom.logBox.textContent = "";
    const fallbackMsg =
      state.lastMapRouteFailureCount > 0 ? `，其中 ${state.lastMapRouteFailureCount} 条路线回退为节点连线` : "";
    setStatus(`状态：高德地图回放已生成，范围=${scopeLabel}，事件数=${state.events.length}${fallbackMsg}`);
  } catch (err) {
    hideGeoMapPanel();
    setGeoLoading("", false);
    setStatus(`状态：地图模式失败 - ${err.message}`, true);
  }
}

async function runSimulation() {
  const payload = readCommonPayload();
  hideGeoMapPanel();
  setStatus("状态：仿真运行中…");

  try {
    const data = await postJson("/api/run", payload);
    hydrateRunData(data);
    renderStaticMapBase();
    renderReplayAt(0, { appendLogs: false, initialSummary: true, preDispatch: true });
    dom.logBox.textContent = "";
    setStatus(`状态：仿真完成，共 ${state.events.length} 条派单事件`);
  } catch (err) {
    setStatus(`状态：仿真失败 — ${err.message}`, true);
  }
}

function hydrateRunData(data) {
  pauseReplay(true);
  state.scenario = data.scenario;
  state.summary = data.summary;
  state.events = Array.isArray(data.events) ? data.events : [];
  state.eventIndex = 0;
  state.playing = false;
  state.animating = false;
  state.scoreAcc = 0;
  state.routeHistory = [];
  state.currentTime = 0;
  state.recentTaskIds = new Set();
  state.completedTaskIds = new Set(
    state.events.map((event) => Number(event.task_id))
  );
  state.lastVehiclePanelPaintAt = 0;
  state.activeReplayVehicleIds = new Set();
  state.replayLoggedTaskIds = new Set();
  state.replayLastFrameTs = 0;
  state.replayRafId = null;
  state.preDispatchView = false;
  state.geoRouteCache = new Map();
  state.geoRoutePending = new Map();
  state.geoRouteFailures = new Set();
  state.geoView = null;
  state.geoViewSignature = "";
  state.geoTilesSignature = "";
  state.lastMapRouteFailureCount = 0;

  state.nodeMap = new Map();
  state.scenario.nodes.forEach((node) => state.nodeMap.set(node.node_id, node));

  state.taskState = new Map();
  state.scenario.tasks.forEach((task) => state.taskState.set(task.task_id, "pending"));

  state.vehicleState = new Map();
  (state.scenario.vehicles || []).forEach((vehicle) => {
    state.vehicleState.set(vehicle.vehicle_id, {
      vehicleId: vehicle.vehicle_id,
      capacity: Number(vehicle.capacity),
      batteryCapacity: Number(vehicle.battery_capacity),
      battery: Number(vehicle.battery),
      status: "idle",
      busyUntil: 0,
      currentNode: vehicle.current_node,
      assignedWeight: 0,
      lastTaskId: null,
      chargeAmount: 0,
      chargeStartTime: null,
      chargeEndTime: null
    });
  });
  state.initialVehicleState = cloneVehicleStateMap(state.vehicleState);

  state.projection = buildProjection(state.scenario.nodes);
  setWeatherEffect(state.scenario.weather_mode || dom.weatherSelect.value);
  prepareReplayTimeline();
  setGeoLoading("", false);
}

async function compareStrategies() {
  const payload = readCommonPayload();
  setStatus("状态：正在对比各策略…");

  try {
    const data = await postJson("/api/compare", payload);
    renderRanking(data.ranking || []);
    if (data.ranking && data.ranking.length > 0) {
      const best = data.ranking[0];
      setStatus(`状态：最优策略为「${zhStrategy(best.strategy)}」，得分 ${best.score.toFixed(2)}`);
    } else {
      setStatus("状态：未返回排名数据", true);
    }
  } catch (err) {
    setStatus(`状态：策略对比失败 — ${err.message}`, true);
  }
}

function renderRanking(ranking) {
  dom.rankingList.innerHTML = "";

  if (!ranking.length) {
    dom.rankingList.className = "ranking-list empty";
    dom.rankingList.textContent = "暂无数据";
    return;
  }

  dom.rankingList.className = "ranking-list";

  const scores = ranking.map((item) => item.score);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);
  const span = Math.max(1, maxScore - minScore);

  ranking.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "rank-row";

    const order = document.createElement("div");
    order.textContent = String(index + 1);

    const bar = document.createElement("div");
    bar.className = "rank-bar";

    const fill = document.createElement("div");
    fill.className = "rank-fill";
    const width = 18 + ((item.score - minScore) / span) * 82;
    fill.style.width = `${width}%`;

    const label = document.createElement("div");
    label.className = "rank-label";
    label.textContent = `${zhStrategy(item.strategy)} | 完成 ${item.completed} | 超时 ${item.overtime}`;

    bar.appendChild(fill);
    bar.appendChild(label);

    const score = document.createElement("div");
    score.textContent = item.score.toFixed(1);

    row.appendChild(order);
    row.appendChild(bar);
    row.appendChild(score);

    dom.rankingList.appendChild(row);
  });
}

async function playReplay() {
  if (!state.scenario || !state.events.length) {
    setStatus("状态：请先运行仿真", true);
    return;
  }
  if (!state.timelineBreakpoints.length || !Number.isFinite(state.replayEndTime)) {
    prepareReplayTimeline();
  }
  if (!state.timelineBreakpoints.length || state.replayEndTime <= 0) {
    setStatus("状态：当前运行无法生成回放时间轴", true);
    return;
  }
  if (state.playing) {
    return;
  }
  if (state.currentTime >= state.replayEndTime - 1e-9) {
    state.currentTime = 0;
    state.replayLoggedTaskIds = new Set();
    dom.logBox.textContent = "";
    renderReplayAt(0, { appendLogs: false, initialSummary: true, preDispatch: true });
  }
  if (state.preDispatchView && state.currentTime <= 1e-9) {
    const firstDispatch = (state.timelineMissions || [])
      .map((mission) => numberValue(mission.dispatch))
      .filter((t) => t >= 0)
      .sort((a, b) => a - b)[0];
    if (Number.isFinite(firstDispatch)) {
      renderReplayAt(firstDispatch, { appendLogs: false, initialSummary: false });
    } else {
      renderReplayAt(0, { appendLogs: false, initialSummary: false });
    }
  }

  state.playing = true;
  state.animating = true;
  state.replayLastFrameTs = 0;
  setStatus("状态：回放进行中…");

  const tick = (ts) => {
    if (!state.playing) {
      state.animating = false;
      state.replayRafId = null;
      return;
    }
    if (!state.replayLastFrameTs) {
      state.replayLastFrameTs = ts;
    }
    const deltaMs = Math.max(0, ts - state.replayLastFrameTs);
    state.replayLastFrameTs = ts;
    const speed = Math.max(0.25, Math.min(4, Number(dom.replaySpeedSelect?.value ?? 1) || 1));
    const nextSimTime = state.currentTime + (deltaMs * speed) / Math.max(1e-6, REPLAY_SIM_TIME_TO_MS);
    renderReplayAt(nextSimTime, { appendLogs: true, initialSummary: false, throttleSidePanels: true });

    if (state.currentTime >= state.replayEndTime - 1e-9) {
      state.playing = false;
      state.animating = false;
      state.replayRafId = null;
      finalizeReplayTaskStates();
      renderSummary(false);
      renderStatusPanels();
      const doneCount = Array.from(state.taskState.values()).filter((s) => s === "done").length;
      setStatus(`状态：回放结束，已完成 ${doneCount}/${state.scenario.tasks.length} 个任务`);
      return;
    }
    state.replayRafId = requestAnimationFrame(tick);
  };
  state.replayRafId = requestAnimationFrame(tick);
}

function pauseReplay(silent = false) {
  if (state.replayRafId !== null) {
    cancelAnimationFrame(state.replayRafId);
    state.replayRafId = null;
  }
  state.replayLastFrameTs = 0;
  state.playing = false;
  state.animating = false;
  if (!silent) {
    setStatus("状态：回放已暂停");
    state.lastSidePanelPaintAt = 0;
    renderSummary(false);
    renderStatusPanels();
  }
}

async function stepReplay() {
  if (!state.scenario || !state.events.length) {
    return false;
  }
  pauseReplay(true);
  const nextTime = findNextReplayBreakpoint(state.currentTime);
  if (nextTime === null) {
    if (state.currentTime < state.replayEndTime - 1e-9) {
      renderReplayAt(state.replayEndTime, { appendLogs: true, initialSummary: false });
      finalizeReplayTaskStates();
      renderSummary(false);
      renderStatusPanels();
      const doneCount = Array.from(state.taskState.values()).filter((s) => s === "done").length;
      setStatus(`状态：回放结束，已完成 ${doneCount}/${state.scenario.tasks.length} 个任务`);
      return true;
    }
    return false;
  }
  renderReplayAt(nextTime, { appendLogs: true, initialSummary: false });
  if (state.currentTime >= state.replayEndTime - 1e-9) {
    finalizeReplayTaskStates();
    renderSummary(false);
    renderStatusPanels();
    const doneCount = Array.from(state.taskState.values()).filter((s) => s === "done").length;
    setStatus(`状态：回放结束，已完成 ${doneCount}/${state.scenario.tasks.length} 个任务`);
  } else {
    setStatus(`状态：回放时刻 ${state.currentTime.toFixed(1)}`);
  }
  return true;
}

function resetReplay() {
  if (!state.scenario) {
    return;
  }

  pauseReplay();
  state.eventIndex = 0;
  state.scoreAcc = 0;
  state.routeHistory = [];
  state.currentTime = 0;
  state.recentTaskIds = new Set();
  state.lastVehiclePanelPaintAt = 0;
  state.activeReplayVehicleIds = new Set();
  state.replayLoggedTaskIds = new Set();
  state.preDispatchView = false;
  state.scenario.tasks.forEach((task) => state.taskState.set(task.task_id, "pending"));
  restoreVehicleStateToInitial();

  dom.logBox.textContent = "";
  renderStaticMapBase();
  renderReplayAt(0, { appendLogs: false, initialSummary: true, preDispatch: true });
  setStatus("状态：回放已重置");
  state.lastSidePanelPaintAt = 0;
  updateReplayProgress(0, state.replayEndTime);
}

function cloneVehicleStateMap(sourceMap) {
  const out = new Map();
  sourceMap.forEach((value, key) => {
    out.set(key, { ...value });
  });
  return out;
}

function restoreVehicleStateToInitial() {
  state.vehicleState = cloneVehicleStateMap(state.initialVehicleState);
}

function renderStaticMapBase() {
  if (!state.scenario || !state.projection) {
    clearMapLayers();
    clearGeoMapLayers();
    return;
  }
  clearMapLayers();
  drawEdges();
  drawStations();
  drawDepot();
  if (isGeoReplayAvailable()) {
    renderGeoReplayFrame([], []);
  } else {
    clearGeoMapLayers();
  }
}

async function ensureGeoReplayReady() {
  if (!isGeoScenario()) {
    clearGeoMapLayers();
    setGeoLoading("", false);
    return;
  }

  showGeoMapPanel();
  updateGeoMapMeta();
  state.geoView = null;
  state.geoViewSignature = "";
  state.geoTilesSignature = "";
  prepareReplayTimeline();
  renderGeoReplayFrame([], []);
  setGeoLoading("", false);
}

function collectUniqueGeoRoutes() {
  const unique = new Map();
  (state.events || []).forEach((event) => {
    const routes = Array.isArray(event.routes) ? event.routes : [];
    routes.forEach((route) => {
      const routeNodes = Array.isArray(route.route_nodes) ? route.route_nodes.map((nodeId) => Number(nodeId)) : [];
      if (routeNodes.length < 2) {
        return;
      }
      const routeKey = String(route.route_key || routeNodes.join("-"));
      if (!unique.has(routeKey)) {
        unique.set(routeKey, { routeKey, routeNodes });
      }
    });
  });
  return Array.from(unique.values());
}

function applyGeoRoutesToEvents() {
  (state.events || []).forEach((event) => {
    const routes = Array.isArray(event.routes) ? event.routes : [];
    routes.forEach((route) => {
      const routeNodes = Array.isArray(route.route_nodes) ? route.route_nodes.map((nodeId) => Number(nodeId)) : [];
      const routeKey = String(route.route_key || routeNodes.join("-"));
      const cached = state.geoRouteCache.get(routeKey);
      route.display_points = cached?.coordinates ? cached.coordinates.map((point) => [...point]) : routeNodePairs(routeNodes);
    });
  });
}

async function loadGeoRoute(routeKey, routeNodes) {
  const cached = state.geoRouteCache.get(routeKey);
  if (cached) {
    return cached;
  }
  const pending = state.geoRoutePending.get(routeKey);
  if (pending) {
    return pending;
  }

  const task = (async () => {
    const fallbackCoordinates = routeNodePairs(routeNodes);
    if (fallbackCoordinates.length < 2) {
      const result = { coordinates: fallbackCoordinates, fallback: true };
      state.geoRouteCache.set(routeKey, result);
      state.geoRouteFailures.add(routeKey);
      return result;
    }

    try {
      const data = await postJson("/api/route-geometry", { waypoints: fallbackCoordinates });
      const coordinates = normalizeGeoCoordinatePairs(data.coordinates);
      const result = {
        coordinates: coordinates.length >= 2 ? coordinates : fallbackCoordinates,
        fallback: coordinates.length < 2,
        distance_km: Number(data.distance_km || 0),
        duration_min: Number(data.duration_min || 0)
      };
      state.geoRouteCache.set(routeKey, result);
      if (!result.fallback && isOfflinePanyuScenario()) {
        void cacheGeoRouteOffline(routeNodes, result);
      }
      if (result.fallback) {
        state.geoRouteFailures.add(routeKey);
      } else {
        state.geoRouteFailures.delete(routeKey);
      }
      applyGeoRoutesToEvents();
      state.lastMapRouteFailureCount = state.geoRouteFailures.size;
      if (isGeoReplayAvailable()) {
        refreshCurrentReplayFrame();
      }
      return result;
    } catch (_err) {
      const result = { coordinates: fallbackCoordinates, fallback: true };
      state.geoRouteCache.set(routeKey, result);
      state.geoRouteFailures.add(routeKey);
      applyGeoRoutesToEvents();
      state.lastMapRouteFailureCount = state.geoRouteFailures.size;
      if (isGeoReplayAvailable()) {
        refreshCurrentReplayFrame();
      }
      return result;
    } finally {
      state.geoRoutePending.delete(routeKey);
    }
  })();

  state.geoRoutePending.set(routeKey, task);
  return task;
}

async function cacheGeoRouteOffline(routeNodes, routeData) {
  if (!Array.isArray(routeNodes) || routeNodes.length < 2) {
    return;
  }
  if (!routeData || !Array.isArray(routeData.coordinates) || routeData.coordinates.length < 2) {
    return;
  }
  try {
    await postJson("/api/cache-route", {
      scale: String(state.scenario?.name || dom.scaleSelect?.value || "").trim(),
      route_nodes: routeNodes,
      coordinates: routeData.coordinates,
      distance_km: Number(routeData.distance_km || 0),
      duration_min: Number(routeData.duration_min || 0)
    });
  } catch (_err) {
    // Ignore persistence failures and keep replay running with the in-memory route.
  }
}

async function runConcurrent(items, limit, worker) {
  const total = Array.isArray(items) ? items.length : 0;
  if (!total) {
    return;
  }
  let cursor = 0;
  const runners = Array.from({ length: Math.min(Math.max(1, limit), total) }, async () => {
    while (cursor < total) {
      const index = cursor;
      cursor += 1;
      await worker(items[index], index, total);
    }
  });
  await Promise.all(runners);
}

function normalizeGeoCoordinatePairs(points) {
  if (!Array.isArray(points)) {
    return [];
  }
  const normalized = [];
  points.forEach((point) => {
    if (!Array.isArray(point) || point.length < 2) {
      return;
    }
    const lng = numberValue(point[0]);
    const lat = numberValue(point[1]);
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
      return;
    }
    const pair = [Number(lng.toFixed(6)), Number(lat.toFixed(6))];
    const previous = normalized[normalized.length - 1];
    if (!previous || previous[0] !== pair[0] || previous[1] !== pair[1]) {
      normalized.push(pair);
    }
  });
  return normalized;
}

function routeNodePairs(routeNodes) {
  if (!Array.isArray(routeNodes)) {
    return [];
  }
  const pairs = [];
  routeNodes.forEach((nodeId) => {
    const node = state.nodeMap.get(Number(nodeId));
    if (!node) {
      return;
    }
    const pair = [numberValue(node.x), numberValue(node.y)];
    const previous = pairs[pairs.length - 1];
    if (!previous || previous[0] !== pair[0] || previous[1] !== pair[1]) {
      pairs.push(pair);
    }
  });
  return pairs;
}

function updateGeoMapMeta() {
  if (!dom.geoMapMeta || !state.scenario) {
    return;
  }
  const city = state.scenario.city_name || "高德城市";
  const district = String(state.scenario.district_name || "").trim();
  const scope = district ? `${city}${district}` : city;
  const prefix = isOfflinePanyuScenario() ? "固定底图" : "地图回放";
  dom.geoMapMeta.textContent = `${prefix}：${scope} | ${zhScale(state.scenario.map_mode === "amap" ? state.summary?.scenario || dom.scaleSelect.value : dom.scaleSelect.value)} | ${zhWeather(state.scenario.weather_mode || dom.weatherSelect.value)}`;
}

function prepareReplayTimeline() {
  if (!state.scenario) {
    state.timelineMissions = [];
    state.timelineBreakpoints = [];
    state.replayEndTime = 0;
    return;
  }

  const normalizedEvents = (state.events || [])
    .map((event) => ({
      ...event,
      dispatch_time: numberValue(event.dispatch_time ?? 0),
      completion_time: numberValue(event.completion_time ?? event.dispatch_time ?? 0),
      task_id: Number(event.task_id)
    }))
    .sort((a, b) => {
      const da = Number(a.dispatch_time ?? 0);
      const db = Number(b.dispatch_time ?? 0);
      if (Math.abs(da - db) > 1e-9) {
        return da - db;
      }
      const ca = Number(a.completion_time ?? da);
      const cb = Number(b.completion_time ?? db);
      if (Math.abs(ca - cb) > 1e-9) {
        return ca - cb;
      }
      return Number(a.task_id ?? 0) - Number(b.task_id ?? 0);
    });
  state.events = normalizedEvents;

  const breakpoints = [0];
  const missions = [];
  normalizedEvents.forEach((event) => {
    const dispatch = numberValue(event.dispatch_time ?? 0);
    let completion = numberValue(event.completion_time ?? dispatch + 1e-6);
    if (!Number.isFinite(completion) || completion < dispatch + 1e-6) {
      completion = dispatch + 1e-6;
    }
    breakpoints.push(dispatch, completion);

    const routes = Array.isArray(event.routes) ? event.routes : [];
    routes.forEach((route) => {
      const routeNodes = Array.isArray(route.route_nodes) ? route.route_nodes.map((nodeId) => Number(nodeId)) : [];
      const points = routeToPoints(routeNodes, route);
      if (!points.length) {
        return;
      }
      const metrics = pathMetrics(points);
      const vehicleId = Number(route.vehicle_id);
      const taskId = Number(route.task_id ?? event.task_id);
      const initialVehicle = state.initialVehicleState.get(vehicleId);
      const routeStartBattery = Number(route.start_battery);
      const startBattery =
        Number.isFinite(routeStartBattery)
          ? routeStartBattery
          : initialVehicle
          ? Number(initialVehicle.battery)
          : Number(route.final_battery ?? 0);
      const finalBattery = numberValue(route.final_battery ?? startBattery);
      const chargeAmount = numberValue(route.charge_amount ?? 0);
      const chargeStartTime = route.charge_start_time == null ? null : Number(route.charge_start_time);
      const chargeEndTime = route.charge_end_time == null ? null : Number(route.charge_end_time);
      const preChargeRatio = estimatePreChargeDistanceRatio(
        {
          ...route,
          route_nodes: routeNodes
        },
        points,
        metrics.total
      );
      const batteryAtTime = buildBatteryInterpolator(
        startBattery,
        finalBattery,
        chargeAmount,
        dispatch,
        completion,
        chargeStartTime,
        chargeEndTime,
        preChargeRatio
      );

      missions.push({
        vehicleId,
        taskId,
        dispatch,
        completion,
        routeRef: route,
        routeNodes,
        points,
        cumulative: metrics.cumulative,
        totalDistancePx: metrics.total,
        batteryAtTime,
        finalBattery,
        finalNode: Number(route.final_node ?? state.scenario.depot_node),
        assignedWeight: Number(route.assigned_weight ?? 0),
        chargeAmount,
        chargeStartTime,
        chargeEndTime
      });
    });
  });

  missions.sort((a, b) => {
    if (Math.abs(a.dispatch - b.dispatch) > 1e-9) {
      return a.dispatch - b.dispatch;
    }
    if (Math.abs(a.completion - b.completion) > 1e-9) {
      return a.completion - b.completion;
    }
    return a.vehicleId - b.vehicleId;
  });

  state.timelineMissions = missions;
  state.timelineBreakpoints = Array.from(
    new Set(
      breakpoints
        .filter((item) => Number.isFinite(item))
        .map((item) => Number(item.toFixed(3)))
    )
  ).sort((a, b) => a - b);
  state.replayEndTime = state.timelineBreakpoints.length ? state.timelineBreakpoints[state.timelineBreakpoints.length - 1] : 0;
}

function findNextReplayBreakpoint(now) {
  const cur = Number(now ?? 0);
  for (const t of state.timelineBreakpoints) {
    if (t > cur + 1e-9) {
      return t;
    }
  }
  return null;
}

function updateReplayProgress(simTime, replayEnd) {
  if (!dom.replayProgressFill || !dom.replayProgressLabel) {
    return;
  }
  const end = Number(replayEnd);
  if (!state.scenario || !Number.isFinite(end) || end <= 1e-9) {
    dom.replayProgressFill.style.width = "0%";
    dom.replayProgressLabel.textContent = state.scenario ? "准备就绪，点击「播放回放」" : "尚未加载回放";
    dom.replayProgress?.setAttribute("aria-valuenow", "0");
    return;
  }
  const t = clamp(numberValue(simTime), 0, end);
  const pct = (t / end) * 100;
  dom.replayProgressFill.style.width = `${pct}%`;
  dom.replayProgressLabel.textContent = `仿真时刻 ${t.toFixed(0)} / ${end.toFixed(0)}（${pct.toFixed(0)}%）`;
  dom.replayProgress?.setAttribute("aria-valuenow", String(Math.round(Math.min(100, Math.max(0, pct)))));
}

function toggleMapFullscreen() {
  const el = dom.mapWrap;
  if (!el) {
    return;
  }
  const run = async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (el.requestFullscreen) {
        await el.requestFullscreen();
      }
    } catch {
      setStatus("状态：无法进入全屏（浏览器可能已禁止）", true);
    }
  };
  void run();
}

function onDemoHotkey(e) {
  const target = e.target;
  if (
    target &&
    (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable)
  ) {
    return;
  }
  if (e.code === "Space") {
    e.preventDefault();
    if (state.playing) {
      pauseReplay();
    } else {
      void playReplay();
    }
    return;
  }
  if (e.code === "ArrowRight") {
    e.preventDefault();
    void stepReplay();
    return;
  }
  if (e.key === "r" || e.key === "R") {
    if (e.ctrlKey || e.metaKey || e.altKey) {
      return;
    }
    resetReplay();
    return;
  }
  if (e.key === "f" || e.key === "F") {
    if (e.ctrlKey || e.metaKey || e.altKey) {
      return;
    }
    e.preventDefault();
    toggleMapFullscreen();
  }
}

function renderReplayAt(simTime, options = {}) {
  if (!state.scenario) {
    return;
  }
  const appendLogs = Boolean(options.appendLogs);
  const initialSummary = Boolean(options.initialSummary);
  const preDispatch = Boolean(options.preDispatch);
  const throttleSidePanels = Boolean(options.throttleSidePanels);
  const replayEnd = Number.isFinite(state.replayEndTime) ? state.replayEndTime : 0;
  const target = clamp(numberValue(simTime ?? 0), 0, Math.max(0, replayEnd));
  const eventTime = preDispatch ? -1e-6 : target;
  state.preDispatchView = preDispatch && target <= 1e-9;
  state.currentTime = target;

  const dispatchedEvents = state.events.filter((event) => Number(event.dispatch_time) <= eventTime + 1e-9);
  const completedEvents = state.events.filter((event) => Number(event.completion_time) <= eventTime + 1e-9);
  const activeEvents = state.events.filter(
    (event) => Number(event.dispatch_time) <= eventTime + 1e-9 && Number(event.completion_time) > eventTime + 1e-9
  );
  const dispatchedRoutes = [];
  dispatchedEvents.forEach((event) => {
    const routes = Array.isArray(event.routes) ? event.routes : [];
    routes.forEach((route) => {
      dispatchedRoutes.push({
        vehicle_id: Number(route.vehicle_id),
        route_nodes: Array.isArray(route.route_nodes) ? route.route_nodes : [],
        display_points: Array.isArray(route.display_points) ? route.display_points : []
      });
    });
  });
  state.routeHistory = dispatchedRoutes.slice(-160);

  const activeMissions = state.timelineMissions.filter(
    (mission) => mission.dispatch <= eventTime + 1e-9 && mission.completion > eventTime + 1e-9
  );
  const finishedMissions = state.timelineMissions.filter((mission) => mission.completion <= eventTime + 1e-9);

  state.scenario.tasks.forEach((task) => state.taskState.set(task.task_id, "pending"));
  activeEvents.forEach((event) => state.taskState.set(Number(event.task_id), "delivering"));
  completedEvents.forEach((event) => state.taskState.set(Number(event.task_id), "done"));
  if (target >= replayEnd - 1e-9) {
    finalizeReplayTaskStates();
  }

  state.recentTaskIds = new Set(activeEvents.map((event) => Number(event.task_id)));
  state.eventIndex = completedEvents.length;
  state.scoreAcc = completedEvents.reduce((acc, item) => acc + Number(item.score || 0), 0);

  restoreVehicleStateToInitial();
  state.activeReplayVehicleIds = new Set();

  finishedMissions.forEach((mission) => {
    const vehicle = state.vehicleState.get(mission.vehicleId);
    if (!vehicle) {
      return;
    }
    vehicle.battery = mission.finalBattery;
    vehicle.currentNode = mission.finalNode;
    vehicle.lastTaskId = mission.taskId;
    vehicle.assignedWeight = 0;
    vehicle.busyUntil = Math.max(Number(vehicle.busyUntil ?? 0), mission.completion);
    vehicle.chargeAmount = 0;
    vehicle.chargeStartTime = null;
    vehicle.chargeEndTime = null;
  });

  const cars = [];
  activeMissions.forEach((mission) => {
    const vehicle = state.vehicleState.get(mission.vehicleId);
    const progress = clamp(
      (target - mission.dispatch) / Math.max(1e-6, mission.completion - mission.dispatch),
      0,
      1
    );
    const dist = mission.totalDistancePx * progress;
    const point = sampleAtDistance(mission.points, mission.cumulative, dist);
    const geoCoordinates = routeCoordinates(mission.routeRef);
    const geoProjected = geoCoordinates.map((pair) => projectGeoPoint(pair[0], pair[1])).filter(Boolean);
    const geoMetrics = pathMetrics(geoProjected.length ? geoProjected : mission.points);
    const geoDist = geoMetrics.total * progress;
    const geoPoint = sampleAtDistance(
      geoProjected.length ? geoProjected : mission.points,
      geoMetrics.cumulative.length ? geoMetrics.cumulative : mission.cumulative,
      geoDist
    );
    cars.push({ vehicleId: mission.vehicleId, point, geoPoint });

    if (vehicle) {
      vehicle.battery = mission.batteryAtTime(target);
      vehicle.lastTaskId = mission.taskId;
      vehicle.assignedWeight = mission.assignedWeight;
      vehicle.busyUntil = Math.max(Number(vehicle.busyUntil ?? 0), mission.completion);
      vehicle.chargeAmount = mission.chargeAmount;
      vehicle.chargeStartTime = mission.chargeStartTime;
      vehicle.chargeEndTime = mission.chargeEndTime;
    }
    state.activeReplayVehicleIds.add(mission.vehicleId);
  });

  renderReplayLayers(
    activeMissions.map((mission) => ({
      vehicle_id: mission.vehicleId,
      route_nodes: mission.routeNodes,
      display_points: Array.isArray(mission.routeRef?.display_points) ? mission.routeRef.display_points : []
    })),
    cars
  );

  if (appendLogs) {
    completedEvents.forEach((event) => {
      const taskId = Number(event.task_id);
      if (state.replayLoggedTaskIds.has(taskId)) {
        return;
      }
      state.replayLoggedTaskIds.add(taskId);
      appendLog(event);
    });
  }

  updateReplayProgress(target, replayEnd);

  if (!throttleSidePanels) {
    state.lastSidePanelPaintAt = performance.now();
    renderSummary(initialSummary);
    renderStatusPanels();
  } else {
    const now = performance.now();
    if (now - state.lastSidePanelPaintAt >= REPLAY_SIDE_PANEL_THROTTLE_MS) {
      state.lastSidePanelPaintAt = now;
      renderSummary(initialSummary);
      renderStatusPanels();
    }
  }
}

function renderReplayLayers(activeRoutes, cars) {
  dom.historyLayer.innerHTML = "";
  dom.tasksLayer.innerHTML = "";
  dom.activeRouteLayer.innerHTML = "";
  dom.carLayer.innerHTML = "";
  drawRouteHistory();
  drawTasks();
  drawActiveRoutes(activeRoutes);
  cars.forEach((carInfo) => {
    const car = createCar(carInfo.vehicleId);
    placeCar(car, carInfo.point);
    dom.carLayer.appendChild(car);
  });
  renderGeoReplayFrame(activeRoutes, cars);
}

function clearGeoMapLayers() {
  dom.geoHistoryLayer && (dom.geoHistoryLayer.innerHTML = "");
  dom.geoTasksLayer && (dom.geoTasksLayer.innerHTML = "");
  dom.geoStationsLayer && (dom.geoStationsLayer.innerHTML = "");
  dom.geoDepotLayer && (dom.geoDepotLayer.innerHTML = "");
  dom.geoActiveRouteLayer && (dom.geoActiveRouteLayer.innerHTML = "");
  dom.geoCarLayer && (dom.geoCarLayer.innerHTML = "");
}

function renderGeoReplayFrame(activeRoutes, cars) {
  if (!dom.geoMapOverlay || !dom.geoMapViewport) {
    return;
  }
  clearGeoMapLayers();
  if (!isGeoReplayAvailable() || !state.scenario) {
    if (dom.geoMapTiles) {
      dom.geoMapTiles.innerHTML = "";
    }
    return;
  }
  const view = ensureGeoView();
  if (!view) {
    return;
  }
  renderGeoTiles(view);
  queueGeoRouteRequests(activeRoutes);
  dom.geoMapOverlay.setAttribute("viewBox", `0 0 ${view.width} ${view.height}`);

  state.routeHistory.forEach((route) => {
    const points = routeToGeoPoints(route.route_nodes, route);
    if (points.length < 2) {
      return;
    }
    const polyline = svg("polyline", {
      points: formatPoints(points),
      fill: "none",
      stroke: vehicleColor(route.vehicle_id),
      "stroke-width": 2,
      class: "route-history"
    });
    dom.geoHistoryLayer.appendChild(polyline);
  });

  state.scenario.tasks.forEach((task) => {
    const node = state.nodeMap.get(task.node_id);
    const point = node ? projectGeoPoint(node.x, node.y) : null;
    if (!point) {
      return;
    }
    const status = state.taskState.get(task.task_id) || "pending";
    const dot = svg("circle", {
      cx: point.x,
      cy: point.y,
      r: 5,
      fill: status === "done" ? "#1D9B78" : status === "delivering" ? "#F4A23B" : "#DF5A67",
      stroke: "#173954",
      "stroke-width": 0.8
    });
    dom.geoTasksLayer.appendChild(dot);
  });

  state.scenario.stations.forEach((station) => {
    const node = state.nodeMap.get(station.node_id);
    const point = node ? projectGeoPoint(node.x, node.y) : null;
    if (!point) {
      return;
    }
    dom.geoStationsLayer.appendChild(stationIcon(point.x, point.y, station.station_id));
  });

  const depotNode = state.nodeMap.get(state.scenario.depot_node);
  const depotPoint = depotNode ? projectGeoPoint(depotNode.x, depotNode.y) : null;
  if (depotPoint) {
    const depot = svg("g", { transform: `translate(${depotPoint.x} ${depotPoint.y})` });
    depot.appendChild(
      svg("path", {
        d: "M-10 5 L0 -10 L10 5 V12 H-10 Z",
        fill: "#1D3557",
        stroke: "#14243D",
        "stroke-width": 1
      })
    );
    depot.appendChild(
      svg("rect", {
        x: -3,
        y: 5,
        width: 6,
        height: 7,
        fill: "#D9E6F2"
      })
    );
    dom.geoDepotLayer.appendChild(depot);
  }

  activeRoutes.forEach((route) => {
    const points = routeToGeoPoints(route.route_nodes, route);
    if (points.length < 2) {
      return;
    }
    const polyline = svg("polyline", {
      points: formatPoints(points),
      fill: "none",
      stroke: vehicleColor(route.vehicle_id),
      "stroke-width": 3.2,
      class: "route-active"
    });
    dom.geoActiveRouteLayer.appendChild(polyline);
  });

  cars.forEach((carInfo) => {
    const car = createCar(carInfo.vehicleId);
    placeCar(car, carInfo.geoPoint || carInfo.point);
    dom.geoCarLayer.appendChild(car);
  });
}

async function renderScene(activeEvent, animateCars) {
  if (!state.scenario || !state.projection) {
    clearMapLayers();
    return;
  }

  clearMapLayers();
  drawEdges();
  drawRouteHistory();
  drawTasks();
  drawStations();
  drawDepot();

  const activeRoutes = activeEvent && Array.isArray(activeEvent.routes) ? activeEvent.routes : [];
  drawActiveRoutes(activeRoutes);

  if (animateCars && activeRoutes.length) {
    state.animating = true;
    try {
      const dispatchTime = Number(activeEvent?.dispatch_time ?? state.currentTime);
      await animateCarsAlongRoutes(activeRoutes, dispatchTime);
    } finally {
      state.animating = false;
    }
  } else {
    state.animating = false;
    drawRouteEndCars(activeRoutes);
  }
}

function clearMapLayers() {
  dom.edgesLayer.innerHTML = "";
  dom.historyLayer.innerHTML = "";
  dom.tasksLayer.innerHTML = "";
  dom.stationsLayer.innerHTML = "";
  dom.depotLayer.innerHTML = "";
  dom.activeRouteLayer.innerHTML = "";
  dom.carLayer.innerHTML = "";
}

function drawEdges() {
  state.scenario.edges.forEach((edge) => {
    const a = projectNode(edge.a);
    const b = projectNode(edge.b);
    if (!a || !b) {
      return;
    }
    const line = svg("line", {
      x1: a.x,
      y1: a.y,
      x2: b.x,
      y2: b.y,
      stroke: "#D6DFE7",
      "stroke-width": 1.1
    });
    dom.edgesLayer.appendChild(line);
  });
}

function drawRouteHistory() {
  state.routeHistory.forEach((route) => {
    const points = routeToPoints(route.route_nodes);
    if (points.length < 2) {
      return;
    }

    const polyline = svg("polyline", {
      points: formatPoints(points),
      fill: "none",
      stroke: vehicleColor(route.vehicle_id),
      "stroke-width": 2,
      class: "route-history"
    });
    dom.historyLayer.appendChild(polyline);
  });
}

function drawActiveRoutes(routes) {
  routes.forEach((route) => {
    const points = routeToPoints(route.route_nodes);
    if (points.length < 2) {
      return;
    }

    const polyline = svg("polyline", {
      points: formatPoints(points),
      fill: "none",
      stroke: vehicleColor(route.vehicle_id),
      "stroke-width": 3.2,
      class: "route-active"
    });
    dom.activeRouteLayer.appendChild(polyline);
  });
}

function drawTasks() {
  state.scenario.tasks.forEach((task) => {
    const point = projectNode(task.node_id);
    if (!point) {
      return;
    }

    const status = state.taskState.get(task.task_id) || "pending";
    const isDone = status === "done";
    const isDelivering = status === "delivering";
    const isUnserved = status === "unserved";
    const dot = svg("circle", {
      cx: point.x,
      cy: point.y,
      r: 4.5,
      fill: isDone ? "#1D9B78" : isDelivering ? "#F4A23B" : isUnserved ? "#8C98A4" : "#DF5A67",
      stroke: isDone ? "#126B54" : isDelivering ? "#A76816" : isUnserved ? "#5F6B76" : "#A23B45",
      "stroke-width": 0.7
    });

    dom.tasksLayer.appendChild(dot);
  });
}

function drawStations() {
  state.scenario.stations.forEach((station) => {
    const point = projectNode(station.node_id);
    if (!point) {
      return;
    }
    dom.stationsLayer.appendChild(stationIcon(point.x, point.y, station.station_id));
  });
}

function stationIcon(x, y, stationId) {
  const group = svg("g", { transform: `translate(${x - 9} ${y - 14})` });
  group.appendChild(
    svg("rect", {
      x: 0,
      y: 0,
      width: 18,
      height: 28,
      rx: 4,
      fill: "#FFF4E1",
      stroke: "#DD9B38",
      "stroke-width": 1.3
    })
  );
  group.appendChild(
    svg("path", {
      d: "M10 4 L6 14 H10 L8 24 L13 12 H9 Z",
      fill: "#E28413"
    })
  );
  group.appendChild(
    svg("text", {
      x: 9,
      y: 34,
      "text-anchor": "middle",
      "font-size": 8,
      fill: "#A35E0B"
    }, `S${stationId}`)
  );
  return group;
}

function drawDepot() {
  const point = projectNode(state.scenario.depot_node);
  if (!point) {
    return;
  }

  const group = svg("g", { transform: `translate(${point.x} ${point.y})` });
  group.appendChild(
    svg("path", {
      d: "M-10 5 L0 -10 L10 5 V12 H-10 Z",
      fill: "#1D3557",
      stroke: "#14243D",
      "stroke-width": 1
    })
  );
  group.appendChild(
    svg("rect", {
      x: -3,
      y: 5,
      width: 6,
      height: 7,
      fill: "#D9E6F2"
    })
  );
  group.appendChild(
    svg("text", {
      x: 0,
      y: -14,
      "text-anchor": "middle",
      "font-size": 10,
      fill: "#1D3557",
      "font-weight": 700
    }, "车库")
  );

  dom.depotLayer.appendChild(group);
}

function drawRouteEndCars(routes) {
  routes.forEach((route) => {
    const points = routeToPoints(route.route_nodes);
    if (!points.length) {
      return;
    }
    const car = createCar(route.vehicle_id);
    placeCar(car, points[points.length - 1]);
    dom.carLayer.appendChild(car);
  });
}

async function animateCarsAlongRoutes(routes, dispatchTime) {
  state.activeReplayVehicleIds = new Set();
  const jobs = routes
    .map((route) => {
      const points = routeToPoints(route.route_nodes);
      if (!points.length) {
        return null;
      }
      return animateSingleCar(route, points, dispatchTime);
    })
    .filter(Boolean);

  await Promise.all(jobs);
  renderVehicleStatuses();
}

async function animateSingleCar(route, points, dispatchTime) {
  const vehicleId = Number(route.vehicle_id);
  const car = createCar(vehicleId);
  dom.carLayer.appendChild(car);
  const vehicle = state.vehicleState.get(vehicleId);
  const routeStartBattery = Number(route.start_battery);
  const startBattery =
    Number.isFinite(routeStartBattery)
      ? routeStartBattery
      : vehicle
      ? Number(vehicle.battery)
      : Number(route.final_battery ?? 0);
  const finalBattery = Number(route.final_battery ?? startBattery);
  const chargeAmount = Number(route.charge_amount ?? 0);
  const dispatch = Number(dispatchTime ?? state.currentTime);
  const completion = Number(route.completion_time ?? dispatch + 1);

  if (points.length === 1) {
    state.activeReplayVehicleIds.delete(vehicleId);
    placeCar(car, points[0]);
    if (vehicle) {
      vehicle.battery = finalBattery;
      vehicle.currentNode = Number(route.final_node ?? vehicle.currentNode);
      renderVehicleStatuses();
    }
    return;
  }

  const metrics = pathMetrics(points);
  const simDuration = Math.max(1, completion - dispatch);
  const durationByTime = simDuration * REPLAY_SIM_TIME_TO_MS;
  const durationByGeometry = metrics.total * 7;
  const durationMs = clamp(Math.max(durationByTime, durationByGeometry), 900, 12000);
  const preChargeRatio = estimatePreChargeDistanceRatio(route, points, metrics.total);
  const batteryAtTime = buildBatteryInterpolator(
    startBattery,
    finalBattery,
    chargeAmount,
    dispatch,
    completion,
    route.charge_start_time == null ? null : Number(route.charge_start_time),
    route.charge_end_time == null ? null : Number(route.charge_end_time),
    preChargeRatio
  );

  state.activeReplayVehicleIds.add(vehicleId);
  renderVehicleStatuses();

  return new Promise((resolve) => {
    const start = performance.now();

    function frame(frameNow) {
      const elapsed = frameNow - start;
      const progress = Math.min(1, elapsed / durationMs);
      const dist = metrics.total * progress;
      const point = sampleAtDistance(points, metrics.cumulative, dist);
      placeCar(car, point);

      if (vehicle) {
        const simTime = dispatch + (completion - dispatch) * progress;
        state.currentTime = Math.max(state.currentTime, simTime);
        vehicle.battery = batteryAtTime(simTime);
        if (frameNow - state.lastVehiclePanelPaintAt > 90) {
          state.lastVehiclePanelPaintAt = frameNow;
          renderVehicleStatuses();
        }
      }

      if (progress < 1) {
        requestAnimationFrame(frame);
      } else {
        state.activeReplayVehicleIds.delete(vehicleId);
        if (vehicle) {
          vehicle.battery = finalBattery;
          vehicle.currentNode = Number(route.final_node ?? vehicle.currentNode);
          state.currentTime = Math.max(state.currentTime, completion);
          renderVehicleStatuses();
        }
        resolve();
      }
    }

    requestAnimationFrame(frame);
  });
}

function createCar(vehicleId) {
  const color = vehicleColor(vehicleId);
  const group = svg("g");

  group.appendChild(
    svg("rect", {
      x: -10,
      y: -8,
      width: 20,
      height: 10,
      rx: 3,
      fill: color,
      stroke: "#0D2035",
      "stroke-width": 0.7
    })
  );
  group.appendChild(
    svg("rect", {
      x: -5,
      y: -13,
      width: 10,
      height: 6,
      rx: 2,
      fill: "#DDE8F2"
    })
  );
  group.appendChild(
    svg("circle", {
      cx: -6,
      cy: 3,
      r: 3,
      fill: "#1A1A1A"
    })
  );
  group.appendChild(
    svg("circle", {
      cx: 6,
      cy: 3,
      r: 3,
      fill: "#1A1A1A"
    })
  );
  group.appendChild(
    svg("text", {
      x: 0,
      y: -15,
      "text-anchor": "middle",
      "font-size": 8,
      fill: "#1B2A3B",
      "font-weight": 700
    }, `V${vehicleId}`)
  );

  return group;
}

function placeCar(car, point) {
  car.setAttribute("transform", `translate(${point.x} ${point.y})`);
}

function estimatePreChargeDistanceRatio(route, points, totalDistance) {
  if (!route || route.station_id == null || !state.scenario || !Array.isArray(route.route_nodes)) {
    return 0.5;
  }
  let stationNodeId = null;
  if (Number(route.station_id) === -1) {
    stationNodeId = Number(state.scenario.depot_node);
  } else {
    const station = (state.scenario.stations || []).find((item) => Number(item.station_id) === Number(route.station_id));
    if (!station) {
      return 0.5;
    }
    stationNodeId = Number(station.node_id);
  }
  const idx = route.route_nodes.findIndex((nodeId) => Number(nodeId) === stationNodeId);
  if (idx <= 0) {
    return 0.5;
  }
  const prefixNodes = route.route_nodes.slice(0, idx + 1);
  const prefixPoints = routeToPoints(prefixNodes);
  const prefixDist = pathMetrics(prefixPoints).total;
  return clamp(prefixDist / Math.max(totalDistance, 1e-6), 0.05, 0.95);
}

function buildBatteryInterpolator(
  startBattery,
  finalBattery,
  chargeAmount,
  dispatchTime,
  completionTime,
  chargeStartTime,
  chargeEndTime,
  preChargeTravelRatio
) {
  const travelEnergy = Math.max(0, startBattery + Math.max(0, chargeAmount) - finalBattery);
  const beforeEnergy = travelEnergy * clamp(preChargeTravelRatio, 0, 1);
  const afterEnergy = Math.max(0, travelEnergy - beforeEnergy);

  const dispatch = Number(dispatchTime);
  const completion = Math.max(dispatch + 1e-6, Number(completionTime));
  const hasChargeWindow =
    chargeAmount > 1e-9 &&
    chargeStartTime !== null &&
    chargeEndTime !== null &&
    Number(chargeStartTime) < Number(chargeEndTime);

  const chargeStart = hasChargeWindow ? Number(chargeStartTime) : null;
  const chargeEnd = hasChargeWindow ? Number(chargeEndTime) : null;

  return (simTime) => {
    const t = clamp(Number(simTime), dispatch, completion);
    if (!hasChargeWindow) {
      const p = (t - dispatch) / Math.max(1e-6, completion - dispatch);
      return startBattery - travelEnergy * p;
    }

    const preEnd = clamp(chargeStart, dispatch, completion);
    const midEnd = clamp(chargeEnd, preEnd, completion);

    if (t <= preEnd + 1e-9) {
      const p = (t - dispatch) / Math.max(1e-6, preEnd - dispatch);
      return startBattery - beforeEnergy * p;
    }

    const afterPre = startBattery - beforeEnergy;
    if (t <= midEnd + 1e-9) {
      const p = (t - preEnd) / Math.max(1e-6, midEnd - preEnd);
      return afterPre + chargeAmount * p;
    }

    const afterCharge = afterPre + chargeAmount;
    const p = (t - midEnd) / Math.max(1e-6, completion - midEnd);
    return afterCharge - afterEnergy * p;
  };
}

function renderSummary(initial) {
  if (!state.summary || !state.scenario) {
    dom.summaryBox.textContent = "状态：尚未开始";
    dom.metricsList.innerHTML = "";
    return;
  }

  const doneCount = Array.from(state.taskState.values()).filter((s) => s === "done").length;
  const replayCompletionRate = state.summary.total_tasks > 0 ? (doneCount / state.summary.total_tasks) * 100 : 0;
  const finalCompletionRate = state.summary.total_tasks > 0
    ? (numberValue(state.summary.completed_tasks) / state.summary.total_tasks) * 100
    : 0;
  const completedEvents = state.events.filter((event) => numberValue(event.completion_time) <= state.currentTime + 1e-9);
  const activeEvents = state.events.filter(
    (event) =>
      numberValue(event.dispatch_time) <= state.currentTime + 1e-9 &&
      numberValue(event.completion_time) > state.currentTime + 1e-9
  );
  const multiTotal = state.events.filter((event) => (event.vehicle_ids || []).length > 1).length;
  const multiCompleted = completedEvents.filter((event) => (event.vehicle_ids || []).length > 1).length;
  const multiActive = activeEvents.filter((event) => (event.vehicle_ids || []).length > 1).length;
  const vehicles = Array.from(state.vehicleState.values());
  let activeVehicles = 0;
  vehicles.forEach((vehicle) => {
    if (state.currentTime < vehicle.busyUntil - 1e-9) {
      activeVehicles += 1;
    }
  });
  const utilization = vehicles.length > 0 ? (activeVehicles / vehicles.length) * 100 : 0;

  dom.summaryBox.textContent = `策略=${zhStrategy(state.summary.strategy)} | 场景=${zhScale(state.summary.scenario)} | 天气=${zhWeather(state.scenario.weather_mode || "normal")} | 进度=${state.eventIndex}/${state.events.length}`;

  const items = [
    `当前仿真时刻：${state.currentTime.toFixed(1)}`,
    `累计得分：${state.scoreAcc.toFixed(2)}`,
    `任务完成率（终态）：${finalCompletionRate.toFixed(1)}%`,
    `车辆利用率：${utilization.toFixed(1)}%`,
    `任务总数：${state.summary.total_tasks}`,
    `已完成（终态）：${state.summary.completed_tasks}`,
    `回放已完成：${doneCount}（${replayCompletionRate.toFixed(1)}%）`,
    `多车协同任务（回放）：${multiCompleted}/${multiTotal} | 当前进行中 ${multiActive}`,
    `未完成（终态）：${state.summary.unserved_tasks}`,
    `超时（终态）：${state.summary.overtime_tasks}`,
    `终态总分：${Number(state.summary.final_score).toFixed(2)}`,
    `总行驶距离：${Number(state.summary.total_distance).toFixed(2)}`,
    `充电等待合计：${Number(state.summary.total_charging_wait).toFixed(2)}`,
    `平均响应时间：${Number(state.summary.avg_response_time).toFixed(2)}`
  ];

  if (initial) {
    items.unshift(`随机种子：${dom.seedInput.value}`);
  }

  dom.metricsList.innerHTML = "";
  items.forEach((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    dom.metricsList.appendChild(li);
  });
}

function renderStatusPanels() {
  renderVehicleStatuses();
  renderTaskList();
}

function renderVehicleStatuses() {
  if (!state.scenario || !state.vehicleState.size) {
    dom.vehicleStatusList.className = "status-list empty";
    dom.vehicleStatusList.textContent = "暂无车辆数据";
    return;
  }

  dom.vehicleStatusList.className = "status-list";
  dom.vehicleStatusList.innerHTML = "";

  const vehicles = Array.from(state.vehicleState.values()).sort((a, b) => {
    const statusA = resolveVehicleStatus(a, state.currentTime);
    const statusB = resolveVehicleStatus(b, state.currentTime);
    const pri = { transporting: 0, charging: 1, idle: 2 };
    const pa = pri[statusA] ?? 3;
    const pb = pri[statusB] ?? 3;
    if (pa !== pb) {
      return pa - pb;
    }
    return a.vehicleId - b.vehicleId;
  });
  vehicles.forEach((vehicle) => {
    const status = resolveVehicleStatus(vehicle, state.currentTime);
    vehicle.status = status;

    const batteryPct = vehicle.batteryCapacity > 0 ? (vehicle.battery / vehicle.batteryCapacity) * 100 : 0;

    const card = document.createElement("div");
    card.className = "vehicle-item";

    const head = document.createElement("div");
    head.className = "head";
    head.innerHTML = `<span>车辆 #${vehicle.vehicleId}</span><span class=\"status-pill ${status}\">${VEHICLE_STATUS_ZH[status] || status}</span>`;

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.innerHTML = [
      `电量：${batteryPct.toFixed(1)}%（${vehicle.battery.toFixed(1)}/${vehicle.batteryCapacity.toFixed(1)}）`,
      `载重：${vehicle.assignedWeight.toFixed(1)}/${vehicle.capacity.toFixed(1)}`,
      `上一任务：${vehicle.lastTaskId === null ? "—" : `#${vehicle.lastTaskId}`}`,
      `所在节点：${vehicle.currentNode}`
    ].join("<br>");

    card.appendChild(head);
    card.appendChild(meta);
    dom.vehicleStatusList.appendChild(card);
  });
}

function resolveVehicleStatus(vehicle, now) {
  const vehicleId = Number(vehicle.vehicleId);
  const busyUntil = Number(vehicle.busyUntil ?? 0);
  const isAnimating = state.activeReplayVehicleIds.has(vehicleId);
  const isBusyBySchedule = Number.isFinite(busyUntil) && now < busyUntil - 1e-9;
  if (!isAnimating && !isBusyBySchedule) {
    return "idle";
  }
  if (
    vehicle.chargeStartTime !== null &&
    vehicle.chargeEndTime !== null &&
    now >= vehicle.chargeStartTime - 1e-9 &&
    now < vehicle.chargeEndTime - 1e-9
  ) {
    return "charging";
  }
  return "transporting";
}

function renderTaskList() {
  if (!state.scenario) {
    dom.taskListBox.className = "status-list empty";
    dom.taskListBox.textContent = "暂无任务数据";
    return;
  }

  dom.taskListBox.className = "status-list";
  dom.taskListBox.innerHTML = "";

  const tasks = [...state.scenario.tasks].sort((a, b) => {
    const ra = state.recentTaskIds.has(a.task_id) ? 0 : 1;
    const rb = state.recentTaskIds.has(b.task_id) ? 0 : 1;
    if (ra !== rb) {
      return ra - rb;
    }
    const sa = taskStatusOrder(state.taskState.get(a.task_id) || "pending");
    const sb = taskStatusOrder(state.taskState.get(b.task_id) || "pending");
    if (sa !== sb) {
      return sa - sb;
    }
    return a.release_time - b.release_time || a.task_id - b.task_id;
  });
  const limit = tasks.length;

  for (let i = 0; i < limit; i += 1) {
    const task = tasks[i];
    const status = state.taskState.get(task.task_id) || "pending";
    const card = document.createElement("div");
    card.className = `task-item ${status}`;

    const isRecent = state.recentTaskIds.has(task.task_id);
    const head = document.createElement("div");
    head.className = "head";
    head.innerHTML = `<span>任务 #${task.task_id}</span><span>${isRecent ? `刚更新（${TASK_STATUS_ZH[status] || status}）` : TASK_STATUS_ZH[status] || status}</span>`;

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.innerHTML = [
      `节点：${task.node_id}`,
      `重量：${Number(task.weight || 0).toFixed(1)}`,
      `释放时刻：${task.release_time}`,
      `截止时刻：${task.deadline}`
    ].join("<br>");

    card.appendChild(head);
    card.appendChild(meta);
    dom.taskListBox.appendChild(card);
  }
}

function taskStatusOrder(status) {
  if (status === "delivering") {
    return 0;
  }
  if (status === "done") {
    return 1;
  }
  if (status === "pending") {
    return 2;
  }
  return 3;
}

function finalizeReplayTaskStates() {
  state.scenario.tasks.forEach((task) => {
    const status = state.taskState.get(task.task_id) || "pending";
    if (status === "done") {
      return;
    }
    if (state.completedTaskIds.has(task.task_id)) {
      state.taskState.set(task.task_id, "done");
      return;
    }
    state.taskState.set(task.task_id, "unserved");
  });
}

function appendLog(event) {
  const line = `任务#${event.task_id} | 车辆=${(event.vehicle_ids || []).join(",")} | 派发=${Number(event.dispatch_time).toFixed(1)} | 完成=${Number(event.completion_time).toFixed(1)} | 得分=${Number(event.score).toFixed(2)} | 里程=${Number(event.total_distance).toFixed(2)}`;
  dom.logBox.textContent += `${line}\n`;
  dom.logBox.scrollTop = dom.logBox.scrollHeight;
}

function setStatus(message, isError = false) {
  dom.statusBar.textContent = message;
  dom.statusBar.style.color = isError ? "#A22A39" : "#3F556A";
}

function normalizeWeatherMode(mode) {
  const m = String(mode || "normal").toLowerCase();
  if (m === "rain" || m === "congestion") {
    return m;
  }
  return "normal";
}

function setWeatherEffect(mode) {
  const weatherMode = normalizeWeatherMode(mode);
  if (!dom.weatherFx) {
    return;
  }
  dom.weatherFx.classList.remove("normal", "rain", "congestion");
  dom.weatherFx.classList.add(weatherMode);
}

async function loadWeatherStats() {
  dom.weatherStatsStatus.textContent = "正在加载天气统计缓存…";
  dom.weatherStatsTable.innerHTML = "";
  try {
    const data = await fetchJson("/api/weather-stats");
    state.weatherStatsData = data;
    if (Array.isArray(data.weather_modes) && data.weather_modes.length) {
      const currentWeather = dom.weatherStatsWeather.value || "all";
      const options = [{ value: "all", label: "all" }, ...data.weather_modes.map((value) => ({ value, label: value }))];
      const selected = options.some((item) => item.value === currentWeather) ? currentWeather : "all";
      fillSelectByItems(dom.weatherStatsWeather, options, selected);
    }
    if (Array.isArray(data.scales) && data.scales.length) {
      const currentScale = dom.weatherStatsScale.value || "all";
      const options = [{ value: "all", label: "all" }, ...data.scales.map((value) => ({ value, label: value }))];
      const selected = options.some((item) => item.value === currentScale) ? currentScale : "all";
      fillSelectByItems(dom.weatherStatsScale, options, selected);
    }
    renderWeatherStatsTable(data.rows || []);
    const saved = data.saved_file ? ` | 文件=${data.saved_file}` : "";
    const updated = data.updated_at ? ` | 更新=${String(data.updated_at).replace("T", " ")}` : "";
    const err = data.error ? ` | 说明=${data.error}` : "";
    dom.weatherStatsStatus.textContent = `已加载天气统计：行数=${(data.rows || []).length}${saved}${updated}${err}`;
  } catch (err) {
    dom.weatherStatsStatus.textContent = `天气统计加载失败：${err.message}`;
    dom.weatherStatsTable.innerHTML = "";
  }
}

function renderWeatherStatsTable(rows) {
  const scale = dom.weatherStatsScale.value || "all";
  const weather = dom.weatherStatsWeather.value || "all";
  const filtered = rows.filter(
    (row) =>
      (scale === "all" || String(row.scenario) === scale) &&
      (weather === "all" || String(row.weather) === weather)
  );
  if (!filtered.length) {
    dom.weatherStatsTable.innerHTML = "<div style=\"padding:10px;color:#5d7387;font-size:13px;\">暂无天气统计数据。</div>";
    return;
  }
  const sorted = [...filtered].sort((a, b) => {
    const sa = String(a.scenario || "");
    const sb = String(b.scenario || "");
    if (sa !== sb) {
      return sa.localeCompare(sb);
    }
    const wa = String(a.weather || "");
    const wb = String(b.weather || "");
    if (wa !== wb) {
      return wa.localeCompare(wb);
    }
    const ma = String(a.mode || "");
    const mb = String(b.mode || "");
    if (ma !== mb) {
      return ma.localeCompare(mb);
    }
    return String(a.strategy || "").localeCompare(String(b.strategy || ""));
  });

  const table = document.createElement("table");
  table.className = "benchmark-table";
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  ["场景", "天气", "策略", "模式", "完成", "超时", "未完成"].forEach((name) => {
    const th = document.createElement("th");
    th.textContent = name;
    trh.appendChild(th);
  });
  thead.appendChild(trh);
  const tbody = document.createElement("tbody");
  sorted.forEach((row) => {
    const tr = document.createElement("tr");
    [
      zhScale(row.scenario),
      zhWeather(row.weather),
      zhStrategy(row.strategy),
      zhMode(row.mode),
      String(numberValue(row.completed).toFixed(0)),
      String(numberValue(row.overtime).toFixed(0)),
      String(numberValue(row.unserved).toFixed(0))
    ].forEach((text) => {
      const td = document.createElement("td");
      td.textContent = String(text);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(thead);
  table.appendChild(tbody);
  dom.weatherStatsTable.innerHTML = "";
  dom.weatherStatsTable.appendChild(table);
}

function vehicleColor(vehicleId) {
  return VEHICLE_COLORS[vehicleId % VEHICLE_COLORS.length];
}

function buildProjection(nodes) {
  const xs = nodes.map((n) => n.x);
  const ys = nodes.map((n) => n.y);

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const spanX = Math.max(1e-6, maxX - minX);
  const spanY = Math.max(1e-6, maxY - minY);

  const scaleX = (MAP_WIDTH - 2 * MAP_PADDING) / spanX;
  const scaleY = (MAP_HEIGHT - 2 * MAP_PADDING) / spanY;
  const scale = Math.min(scaleX, scaleY);

  const usedW = spanX * scale;
  const usedH = spanY * scale;
  const offsetX = (MAP_WIDTH - usedW) / 2;
  const offsetY = (MAP_HEIGHT - usedH) / 2;

  return { minX, minY, scale, offsetX, offsetY };
}

function clampLatitude(lat) {
  return Math.max(-85.05112878, Math.min(85.05112878, numberValue(lat)));
}

function lngLatToWorld(lng, lat, zoom) {
  const scale = GEO_TILE_SIZE * (2 ** zoom);
  const x = ((numberValue(lng) + 180) / 360) * scale;
  const sinLat = Math.sin((clampLatitude(lat) * Math.PI) / 180);
  const y = (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale;
  return { x, y };
}

function geoViewportSize() {
  const width = Math.max(320, Math.round(dom.geoMapViewport?.clientWidth || dom.mapSvg?.clientWidth || MAP_WIDTH));
  const height = Math.max(240, Math.round(dom.geoMapViewport?.clientHeight || dom.mapSvg?.clientHeight || MAP_HEIGHT));
  return { width, height };
}

function buildGeoView(nodes) {
  if (!Array.isArray(nodes) || !nodes.length) {
    return null;
  }
  const viewport = geoViewportSize();
  let best = null;
  for (let zoom = 15; zoom >= 3; zoom -= 1) {
    const projected = nodes.map((node) => lngLatToWorld(node.x, node.y, zoom));
    const xs = projected.map((point) => point.x);
    const ys = projected.map((point) => point.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const spanX = Math.max(1, maxX - minX);
    const spanY = Math.max(1, maxY - minY);
    const fits = spanX <= viewport.width - GEO_MAP_PADDING * 2 && spanY <= viewport.height - GEO_MAP_PADDING * 2;
    best = { zoom, minX, maxX, minY, maxY, spanX, spanY, width: viewport.width, height: viewport.height };
    if (fits) {
      break;
    }
  }
  if (!best) {
    return null;
  }
  const offsetX = (best.width - best.spanX) / 2 - best.minX;
  const offsetY = (best.height - best.spanY) / 2 - best.minY;
  return { ...best, offsetX, offsetY };
}

function isOfflinePanyuScenario() {
  if (!state.scenario) {
    return false;
  }
  return String(state.scenario.city_name || "").trim() === OFFLINE_CITY_NAME
    && String(state.scenario.district_name || "").trim() === OFFLINE_DISTRICT_NAME;
}

function buildOfflineStaticView() {
  const viewport = geoViewportSize();
  const zoom = 12;
  const topLeft = lngLatToWorld(OFFLINE_BASEMAP_BOUNDS.west, OFFLINE_BASEMAP_BOUNDS.north, zoom);
  const bottomRight = lngLatToWorld(OFFLINE_BASEMAP_BOUNDS.east, OFFLINE_BASEMAP_BOUNDS.south, zoom);
  return {
    kind: "static-image",
    zoom,
    width: viewport.width,
    height: viewport.height,
    minX: topLeft.x,
    maxX: bottomRight.x,
    minY: topLeft.y,
    maxY: bottomRight.y,
    spanX: Math.max(1, bottomRight.x - topLeft.x),
    spanY: Math.max(1, bottomRight.y - topLeft.y),
    offsetX: 0,
    offsetY: 0
  };
}

function ensureGeoView() {
  if (!state.scenario?.nodes?.length) {
    return null;
  }
  const viewport = geoViewportSize();
  const signature = `${state.scenario.nodes.length}:${viewport.width}x${viewport.height}:${isOfflinePanyuScenario() ? "offline" : "tiles"}`;
  if (state.geoView && state.geoViewSignature === signature) {
    return state.geoView;
  }
  const view = isOfflinePanyuScenario() ? buildOfflineStaticView() : buildGeoView(state.scenario.nodes);
  state.geoView = view;
  state.geoViewSignature = signature;
  state.geoTilesSignature = "";
  return view;
}

function projectGeoPoint(xValue, yValue) {
  const view = state.geoView || ensureGeoView();
  if (!view) {
    return null;
  }
  if (view.kind === "static-image") {
    const world = lngLatToWorld(xValue, yValue, view.zoom);
    return {
      x: ((world.x - view.minX) / Math.max(1e-6, view.spanX)) * view.width,
      y: ((world.y - view.minY) / Math.max(1e-6, view.spanY)) * view.height
    };
  }
  const world = lngLatToWorld(xValue, yValue, view.zoom);
  return {
    x: world.x + view.offsetX,
    y: world.y + view.offsetY
  };
}

function geoTileUrl(x, y, zoom) {
  const subdomain = GEO_TILE_SUBDOMAINS[Math.abs(x + y) % GEO_TILE_SUBDOMAINS.length];
  return GEO_TILE_URL_TEMPLATE
    .replace("{s}", subdomain)
    .replace("{x}", String(x))
    .replace("{y}", String(y))
    .replace("{z}", String(zoom));
}

function renderGeoTiles(view) {
  if (!dom.geoMapTiles || !view) {
    return;
  }
  if (dom.geoMapViewport) {
    dom.geoMapViewport.classList.toggle("static-image", view.kind === "static-image");
  }
  if (dom.geoMapStaticBase) {
    dom.geoMapStaticBase.src = OFFLINE_BASEMAP_URL;
  }
  if (view.kind === "static-image") {
    dom.geoMapTiles.innerHTML = "";
    return;
  }
  const left = -view.offsetX;
  const top = -view.offsetY;
  const right = left + view.width;
  const bottom = top + view.height;
  const tileCount = 2 ** view.zoom;
  const minTileX = Math.floor(left / GEO_TILE_SIZE);
  const maxTileX = Math.floor(right / GEO_TILE_SIZE);
  const minTileY = Math.max(0, Math.floor(top / GEO_TILE_SIZE));
  const maxTileY = Math.min(tileCount - 1, Math.floor(bottom / GEO_TILE_SIZE));
  const signature = `${view.zoom}:${view.width}x${view.height}:${minTileX}-${maxTileX}:${minTileY}-${maxTileY}`;
  if (state.geoTilesSignature === signature) {
    return;
  }
  state.geoTilesSignature = signature;
  dom.geoMapTiles.innerHTML = "";
  for (let tileY = minTileY; tileY <= maxTileY; tileY += 1) {
    for (let tileX = minTileX; tileX <= maxTileX; tileX += 1) {
      const wrappedX = ((tileX % tileCount) + tileCount) % tileCount;
      const img = document.createElement("img");
      img.className = "geo-map-tile";
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.src = geoTileUrl(wrappedX, tileY, view.zoom);
      img.style.left = `${tileX * GEO_TILE_SIZE + view.offsetX}px`;
      img.style.top = `${tileY * GEO_TILE_SIZE + view.offsetY}px`;
      dom.geoMapTiles.appendChild(img);
    }
  }
}

function queueGeoRouteRequests(activeRoutes) {
  if (!isGeoReplayAvailable()) {
    return;
  }
  if (String(state.scenario?.route_provider || "") !== "amap") {
    return;
  }
  const visible = new Map();
  const history = state.routeHistory.slice(-24);
  [...history, ...(activeRoutes || [])].forEach((route) => {
    const routeNodes = Array.isArray(route.route_nodes) ? route.route_nodes.map((nodeId) => Number(nodeId)) : [];
    if (routeNodes.length < 2) {
      return;
    }
    const routeKey = String(route.route_key || routeNodes.join("-"));
    if (Array.isArray(route.display_points) && route.display_points.length >= 2) {
      return;
    }
    if (state.geoRouteCache.has(routeKey) || state.geoRoutePending.has(routeKey)) {
      return;
    }
    visible.set(routeKey, routeNodes);
  });
  const pendingRoutes = Array.from(visible.entries()).slice(0, GEO_ROUTE_FETCH_CONCURRENCY);
  pendingRoutes.forEach(([routeKey, routeNodes]) => {
    void loadGeoRoute(routeKey, routeNodes);
  });
}

function projectRawPoint(xValue, yValue) {
  if (!state.projection) {
    return null;
  }
  const x = state.projection.offsetX + (numberValue(xValue) - state.projection.minX) * state.projection.scale;
  const y = MAP_HEIGHT - (state.projection.offsetY + (numberValue(yValue) - state.projection.minY) * state.projection.scale);
  return { x, y };
}

function projectNode(nodeId) {
  const node = state.nodeMap.get(nodeId);
  if (!node || !state.projection) {
    return null;
  }
  return projectRawPoint(node.x, node.y);
}

function routeCoordinates(routeOrNodes) {
  if (routeOrNodes && !Array.isArray(routeOrNodes) && Array.isArray(routeOrNodes.display_points) && routeOrNodes.display_points.length) {
    return normalizeGeoCoordinatePairs(routeOrNodes.display_points);
  }
  const routeNodes = Array.isArray(routeOrNodes)
    ? routeOrNodes
    : Array.isArray(routeOrNodes?.route_nodes)
    ? routeOrNodes.route_nodes
    : [];
  return routeNodePairs(routeNodes);
}

function routeToPoints(routeNodes, routeMeta = null) {
  const points = [];
  const coordinates = routeMeta ? routeCoordinates(routeMeta) : [];
  if (coordinates.length) {
    coordinates.forEach((pair) => {
      const point = projectRawPoint(pair[0], pair[1]);
      if (!point) {
        return;
      }
      const prev = points[points.length - 1];
      if (!prev || prev.x !== point.x || prev.y !== point.y) {
        points.push(point);
      }
    });
    return points;
  }
  if (!Array.isArray(routeNodes)) {
    return points;
  }
  routeNodes.forEach((nodeId) => {
    const point = projectNode(nodeId);
    if (!point) {
      return;
    }
    const prev = points[points.length - 1];
    if (!prev || prev.x !== point.x || prev.y !== point.y) {
      points.push(point);
    }
  });
  return points;
}

function routeToGeoPoints(routeNodes, routeMeta = null) {
  const coordinates = routeMeta ? routeCoordinates(routeMeta) : routeNodePairs(routeNodes);
  const points = [];
  coordinates.forEach((pair) => {
    const point = projectGeoPoint(pair[0], pair[1]);
    if (!point) {
      return;
    }
    const prev = points[points.length - 1];
    if (!prev || prev.x !== point.x || prev.y !== point.y) {
      points.push(point);
    }
  });
  return points;
}

function formatPoints(points) {
  return points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
}

function pathMetrics(points) {
  const cumulative = [0];
  for (let i = 1; i < points.length; i += 1) {
    const dx = points[i].x - points[i - 1].x;
    const dy = points[i].y - points[i - 1].y;
    cumulative.push(cumulative[i - 1] + Math.hypot(dx, dy));
  }
  return {
    cumulative,
    total: cumulative[cumulative.length - 1]
  };
}

function sampleAtDistance(points, cumulative, dist) {
  if (!points.length) {
    return { x: 0, y: 0 };
  }
  if (dist <= 0) {
    return points[0];
  }

  const total = cumulative[cumulative.length - 1];
  if (dist >= total) {
    return points[points.length - 1];
  }

  for (let i = 1; i < cumulative.length; i += 1) {
    if (dist <= cumulative[i]) {
      const segStart = cumulative[i - 1];
      const segEnd = cumulative[i];
      const ratio = (dist - segStart) / Math.max(1e-6, segEnd - segStart);
      return {
        x: points[i - 1].x + (points[i].x - points[i - 1].x) * ratio,
        y: points[i - 1].y + (points[i].y - points[i - 1].y) * ratio
      };
    }
  }

  return points[points.length - 1];
}

function svg(tag, attrs = {}, text = "") {
  const el = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => {
    el.setAttribute(key, String(value));
  });
  if (text) {
    el.textContent = text;
  }
  return el;
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`请求失败（HTTP ${response.status}）`);
  }
  return response.json();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`请求失败（HTTP ${response.status}）`);
  }

  return response.json();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
