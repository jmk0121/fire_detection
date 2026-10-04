"use strict";

const state = { liveTimer: null, isLoading: false };
const $ = (id) => document.getElementById(id);
const ui = {
  main: $("main-content"),
  loading: $("loading-layer"),
  loadingMessage: $("loading-message"),
  errorBanner: $("error-banner"),
  errorMessage: $("error-message"),
};

function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function setLoading(isLoading, message = "분석 중") {
  state.isLoading = isLoading;
  ui.main.setAttribute("aria-busy", String(isLoading));
  ui.loadingMessage.textContent = message;
  ui.loading.hidden = !isLoading;
}

function showError(message) {
  ui.errorMessage.textContent = message;
  ui.errorBanner.hidden = false;
}

function clearError() {
  ui.errorBanner.hidden = true;
}

async function fetchJson(url, options = {}, timeoutMs = 25000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(body?.detail || `요청 실패 (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("응답 시간이 초과되었습니다.");
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

function updateClock() {
  setText("current-time", new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date()));
}

function buildSamples(scenario) {
  const phase = Date.now() / 10000;
  return Array.from({ length: 16 }, (_, index) => {
    const wave = Math.sin(phase + index * 0.72);
    let temperature;
    let humidity;
    let gas1;
    let gas2;
    if (scenario === "stable") {
      temperature = 21.8 + index * 0.035 + wave * 0.18;
      humidity = 51.5 - index * 0.02 - wave * 0.25;
      gas1 = 1.02 + index * 0.003 + wave * 0.015;
      gas2 = 1.01 + index * 0.002 + wave * 0.012;
    } else if (scenario === "rapid") {
      temperature = 29 + index * 2.65 + wave * 0.7;
      humidity = 49 - index * 1.05 - wave * 0.4;
      gas1 = 1.08 + index * 0.27 + wave * 0.06;
      gas2 = 1.04 + index * 0.22 + wave * 0.05;
    } else {
      temperature = 23.5 + index * 1.35 + wave * 0.45;
      humidity = 51 - index * 0.55 - wave * 0.35;
      gas1 = 1.03 + index * 0.12 + wave * 0.035;
      gas2 = 1.01 + index * 0.095 + wave * 0.03;
    }
    return {
      temperature: Number(temperature.toFixed(3)),
      humidity: Number(Math.max(0, humidity).toFixed(3)),
      gas1_ratio: Number(Math.max(0, gas1).toFixed(4)),
      gas2_ratio: Number(Math.max(0, gas2).toFixed(4)),
    };
  });
}

async function runSimulation() {
  if (state.isLoading) return;
  clearError();
  setLoading(true, "상황 분석 중");
  const samples = buildSamples("rising");
  try {
    const result = await fetchJson("/api/v1/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ context_row: 0, samples, generate_briefing: true }),
    }, 30000);
    renderDashboard(result);
  } catch (error) {
    showError(error.message || "분석 요청에 실패했습니다.");
  } finally {
    setLoading(false);
  }
}

async function pollLive() {
  try {
    const result = await fetchJson("/api/v1/live", {}, 6500);
    clearError();
    renderDashboard(result);
    return true;
  } catch {
    return false;
  }
}

function number(value, digits = 1) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "--";
}

function signed(value, digits = 1) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(digits)}`;
}

function setDelta(id, value, unit = "") {
  const element = $(id);
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    element.textContent = "변화 --";
    return;
  }
  const arrow = numeric > 0.01 ? "↑" : numeric < -0.01 ? "↓" : "→";
  const sign = numeric > 0 ? "+" : "";
  element.textContent = `${arrow} ${sign}${numeric.toFixed(1)}${unit}`;
  element.classList.toggle("is-rising", numeric > 0.01);
  element.classList.toggle("is-falling", numeric < -0.01);
}

function renderSensors(summary) {
  setText("temperature-value", number(summary.latest_temperature));
  setText("humidity-value", number(summary.latest_humidity));
  setText("gas1-value", number(summary.latest_gas1_ratio, 2));
  setText("gas2-value", number(summary.latest_gas2_ratio, 2));
  setDelta("temperature-change", summary.temperature_change, "°C");
  setText("humidity-change", `현재 ${number(summary.latest_humidity)}%`);
  setDelta("gas1-change", summary.gas1_ratio_change, "배");
  setDelta("gas2-change", summary.gas2_ratio_change, "배");
}

function firstSentence(text, maxLength = 115) {
  const cleaned = String(text || "").replace(/\s+/g, " ").trim();
  const sentence = cleaned.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() || cleaned;
  return sentence.length > maxLength ? `${sentence.slice(0, maxLength - 1)}…` : sentence;
}

function limitText(text, maxLength = 190) {
  const cleaned = String(text || "").replace(/\s+/g, " ").trim();
  return cleaned.length > maxLength ? `${cleaned.slice(0, maxLength - 1).trim()}…` : cleaned;
}

function operationalText(text) {
  return String(text || "")
    .replace(/LSTM\s*모델|LSTM|AI/gi, "분석 결과")
    .replace(/모델\s*추론|모델\s*결과|모델/g, "분석 결과")
    .replace(/분석 결과\s+분석 결과/g, "분석 결과")
    .replace(/분석 결과 피해등급은/g, "분석 결과는 피해등급")
    .replace(/(-?\d+\.\d+)(?=℃)/g, (value) => Number(value).toFixed(1))
    .replace(/(-?\d+\.\d+)(?=배)/g, (value) => Number(value).toFixed(2))
    .replace(/(-?\d+\.\d+)(?=%)/g, (value) => Number(value).toFixed(1));
}

function renderGuidance(items = []) {
  const container = $("guidance-list");
  container.replaceChildren();
  const priority = { "즉시": 0, "우선": 1, "참고": 2 };
  const selected = [...items].sort((a, b) => priority[a.priority] - priority[b.priority]).slice(0, 3);
  if (!selected.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "확인 항목 없음";
    container.append(empty);
    return;
  }
  selected.forEach((item) => {
    const row = document.createElement("article");
    row.className = "guidance-item";
    const level = document.createElement("span");
    level.className = "priority-label";
    level.dataset.priority = item.priority;
    level.textContent = item.priority;
    const titleWrap = document.createElement("div");
    const title = document.createElement("h3");
    title.className = "guidance-title";
    title.textContent = item.title;
    const category = document.createElement("p");
    category.className = "guidance-category";
    category.textContent = `${item.category} · ${item.trigger}`;
    titleWrap.append(title, category);
    const action = document.createElement("p");
    action.className = "guidance-action";
    action.textContent = firstSentence(item.action, 135);
    row.append(level, titleWrap, action);
    container.append(row);
  });
}

function valueText(value) {
  if (value === null || value === undefined || value === "") return "미확인";
  if (typeof value === "number") return String(Number(value.toFixed(1)));
  return String(value);
}

function areaText(value) {
  const text = valueText(value);
  return text === "미확인" ? text : `${text}㎡`;
}

function renderBuilding(context = {}, contextRow) {
  const items = [
    ["구조", context["건물구조"]],
    ["용도", [context["장소중분류"], context["장소소분류"]].filter(Boolean).join(" · ") || context["장소대분류"]],
    ["층수", `지상 ${valueText(context["지상층수"])} / 지하 ${valueText(context["지하층수"])}`],
    ["연면적", areaText(context["건물연면적"])],
    ["지붕", context["지붕구조"]],
    ["상태", context["건물상태"]],
  ];
  const summary = $("building-summary");
  summary.replaceChildren();
  items.forEach(([term, value]) => {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = term;
    dd.textContent = valueText(value);
    row.append(dt, dd);
    summary.append(row);
  });
}

function renderBriefing(briefing, data = {}) {
  if (!briefing) {
    setText("briefing-headline", "상황 분석 중");
    setText("situation-summary", "");
    renderGuidance([]);
    return;
  }
  const guidance = briefing.operational_guidance || [];
  const firstAction = guidance[0]?.title;
  const sensor = data.sensor_summary || {};
  const context = data.static_context || {};
  const place = context["장소중분류"] || context["장소대분류"] || "대상 건물";
  const above = valueText(context["지상층수"]);
  const below = valueText(context["지하층수"]);
  const sensorLine = [
    `30초 온도 ${number(sensor.latest_temperature)}℃ (${signed(sensor.temperature_change)}℃)`,
    `가스1 ${signed(sensor.gas1_ratio_change, 2)}배`,
    `가스2 ${signed(sensor.gas2_ratio_change, 2)}배`,
    `${place} 지상 ${above}층·지하 ${below}층`,
  ].join(" · ");
  setText("briefing-headline", firstAction ? `${firstAction} 우선` : "현장 확인 우선");
  setText("situation-summary", sensorLine);
  renderGuidance(guidance);
}

function renderDashboard(data) {
  const confidence = Math.max(0, Math.min(1, Number(data.prediction.confidence)));
  const grade = String(data.prediction.grade_code);
  $("grade-card").dataset.grade = grade;
  setText("grade-code", grade);
  setText("grade-label", `피해등급 ${grade}`);
  setText("confidence-value", `${(confidence * 100).toFixed(1)}%`);
  $("confidence-meter").style.width = `${confidence * 100}%`;
  renderBriefing(data.briefing, data);
  renderSensors(data.sensor_summary);
  renderBuilding(data.static_context, data.context_row);
  ui.main.setAttribute("aria-busy", "false");
}

async function initialize() {
  updateClock();
  window.setInterval(updateClock, 1000);
  const liveConnected = await pollLive();
  if (!liveConnected) await runSimulation();
  state.liveTimer = window.setInterval(() => void pollLive(), 2000);
}

void initialize();
