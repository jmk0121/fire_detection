const MODEL_PROFILE = {
  source: "data/processed/강릉시_기상+산불_최종.csv",
  rows: 9626,
  fireRows: 82,
  damageQuantiles: {
    p50: 0.07,
    p90: 1,
    p95: 30.89,
  },
};

const LABELS = {
  buildingUse: {
    residential: "주거시설",
    commercial: "상업시설",
    factory: "공장",
    warehouse: "창고/물류",
    medical: "병원/요양시설",
    school: "학교/공공시설",
  },
  structureType: {
    concrete: "철근콘크리트",
    steel: "철골",
    lightSteel: "경량철골",
    wood: "목조",
    sandwich: "샌드위치 패널",
  },
};

const WEIGHTS = {
  buildingUse: {
    residential: 5,
    commercial: 7,
    factory: 12,
    warehouse: 13,
    medical: 12,
    school: 9,
  },
  structureType: {
    concrete: 4,
    steel: 8,
    lightSteel: 13,
    wood: 16,
    sandwich: 15,
  },
  occupancy: {
    low: 0,
    medium: 3,
    high: 7,
    vulnerable: 12,
  },
  flameLevel: {
    small: 2,
    visible: 8,
    large: 16,
    flashover: 24,
  },
  smokeLevel: {
    light: 1,
    medium: 5,
    dense: 11,
    zero: 16,
  },
  spreadLevel: {
    contained: 1,
    room: 6,
    floor: 13,
    exposure: 20,
  },
};

const PRESETS = {
  initial: {
    buildingUse: "residential",
    structureType: "concrete",
    floors: 3,
    fireFloor: 1,
    hasBasement: "no",
    area: 900,
    occupancy: "medium",
    flameLevel: "small",
    smokeLevel: "medium",
    spreadLevel: "contained",
    avgTemp: 9,
    avgHumidity: 48,
    rainfall: 0,
    maxWind: 4.2,
    effectiveHumidity: 48,
    responseDelay: 7,
  },
  spreading: {
    buildingUse: "commercial",
    structureType: "sandwich",
    floors: 5,
    fireFloor: 2,
    hasBasement: "no",
    area: 3200,
    occupancy: "medium",
    flameLevel: "visible",
    smokeLevel: "dense",
    spreadLevel: "room",
    avgTemp: 14,
    avgHumidity: 32,
    rainfall: 0,
    maxWind: 8.8,
    effectiveHumidity: 33.7,
    responseDelay: 12,
  },
  critical: {
    buildingUse: "warehouse",
    structureType: "lightSteel",
    floors: 8,
    fireFloor: 3,
    hasBasement: "yes",
    area: 9500,
    occupancy: "high",
    flameLevel: "flashover",
    smokeLevel: "zero",
    spreadLevel: "exposure",
    avgTemp: 18,
    avgHumidity: 22,
    rainfall: 0,
    maxWind: 11.4,
    effectiveHumidity: 25,
    responseDelay: 22,
  },
};

const form = document.querySelector("#incident-form");
const presetButtons = document.querySelectorAll("[data-preset]");
const planButtons = document.querySelectorAll("[data-plan]");
let selectedPlan = "main-floor";

const PLAN_CONFIG = {
  "main-floor": {
    title: "1층 평면도",
    alt: "구 마산헌병 분견대 1층 평면도",
    src: "./assets/plans/main-floor.svg",
    location: "1층 중앙부",
    entry: { left: "8%", top: "82%" },
    markers: {
      small: { left: "50%", top: "58%" },
      visible: { left: "57%", top: "52%" },
      large: { left: "63%", top: "46%" },
      flashover: { left: "66%", top: "42%" },
    },
  },
  basement: {
    title: "지하 평면도",
    alt: "구 마산헌병 분견대 지하평면도",
    src: "./assets/plans/basement.svg",
    location: "지하 동측 구획",
    entry: { left: "12%", top: "84%" },
    markers: {
      small: { left: "54%", top: "62%" },
      visible: { left: "61%", top: "56%" },
      large: { left: "67%", top: "49%" },
      flashover: { left: "72%", top: "44%" },
    },
  },
};

function toNumber(formData, key) {
  return Number(formData.get(key)) || 0;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function getInput() {
  const data = new FormData(form);
  return {
    buildingUse: data.get("buildingUse"),
    structureType: data.get("structureType"),
    floors: toNumber(data, "floors"),
    fireFloor: toNumber(data, "fireFloor"),
    hasBasement: data.get("hasBasement"),
    area: toNumber(data, "area"),
    occupancy: data.get("occupancy"),
    flameLevel: data.get("flameLevel"),
    smokeLevel: data.get("smokeLevel"),
    spreadLevel: data.get("spreadLevel"),
    avgTemp: toNumber(data, "avgTemp"),
    avgHumidity: toNumber(data, "avgHumidity"),
    rainfall: toNumber(data, "rainfall"),
    maxWind: toNumber(data, "maxWind"),
    effectiveHumidity: toNumber(data, "effectiveHumidity"),
    responseDelay: toNumber(data, "responseDelay"),
  };
}

function scoreWeather(input) {
  let score = 0;
  const reasons = [];

  if (input.avgHumidity < 25) {
    score += 16;
    reasons.push("평균습도 25% 미만");
  } else if (input.avgHumidity < 35) {
    score += 11;
    reasons.push("낮은 평균습도");
  } else if (input.avgHumidity < 45) {
    score += 6;
    reasons.push("건조한 대기");
  }

  if (input.effectiveHumidity < 30) {
    score += 16;
    reasons.push("실효습도 30% 미만");
  } else if (input.effectiveHumidity < 40) {
    score += 10;
    reasons.push("낮은 실효습도");
  } else if (input.effectiveHumidity < 50) {
    score += 5;
    reasons.push("실효습도 주의 구간");
  }

  if (input.rainfall === 0) {
    score += 8;
    reasons.push("최근 강수 없음");
  } else if (input.rainfall < 1) {
    score += 4;
    reasons.push("강수량 미미");
  } else if (input.rainfall >= 5) {
    score -= 8;
  }

  if (input.maxWind >= 10) {
    score += 18;
    reasons.push("최대풍속 10m/s 이상");
  } else if (input.maxWind >= 7) {
    score += 12;
    reasons.push("강한 바람");
  } else if (input.maxWind >= 4) {
    score += 7;
    reasons.push("풍속에 의한 확산 가능성");
  }

  if (input.avgTemp >= 25) {
    score += 5;
  } else if (input.avgTemp >= 15) {
    score += 3;
  } else if (input.avgTemp <= 0 && input.avgHumidity < 45) {
    score += 2;
  }

  return { score: clamp(score, 0, 55), reasons };
}

function scoreScene(input) {
  let score = 0;
  const reasons = [];

  score += WEIGHTS.buildingUse[input.buildingUse] ?? 0;
  score += WEIGHTS.structureType[input.structureType] ?? 0;
  score += WEIGHTS.occupancy[input.occupancy] ?? 0;
  score += WEIGHTS.flameLevel[input.flameLevel] ?? 0;
  score += WEIGHTS.smokeLevel[input.smokeLevel] ?? 0;
  score += WEIGHTS.spreadLevel[input.spreadLevel] ?? 0;

  if (["factory", "warehouse", "medical"].includes(input.buildingUse)) {
    reasons.push(`${LABELS.buildingUse[input.buildingUse]} 용도`);
  }

  if (["wood", "lightSteel", "sandwich"].includes(input.structureType)) {
    reasons.push(`${LABELS.structureType[input.structureType]} 구조`);
  }

  if (input.floors >= 11) {
    score += 11;
    reasons.push("고층 건물");
  } else if (input.floors >= 6) {
    score += 7;
    reasons.push("중층 이상 건물");
  }

  if (input.hasBasement === "yes") {
    score += 9;
    reasons.push("지하층 존재");
  }

  if (input.fireFloor < 0) {
    score += 13;
    reasons.push("지하층 화재");
  } else if (input.fireFloor >= 5) {
    score += 5;
    reasons.push("상층부 화재");
  }

  if (input.area >= 10000) {
    score += 10;
    reasons.push("대형 연면적");
  } else if (input.area >= 3000) {
    score += 6;
    reasons.push("넓은 연면적");
  }

  if (input.responseDelay >= 20) {
    score += 10;
    reasons.push("대응 지연 20분 이상");
  } else if (input.responseDelay >= 10) {
    score += 5;
    reasons.push("초기 대응 지연");
  }

  if (input.flameLevel === "flashover") {
    reasons.push("급격 확산 징후");
  }
  if (["dense", "zero"].includes(input.smokeLevel)) {
    reasons.push("농연/시야 제한");
  }
  if (input.spreadLevel === "exposure") {
    reasons.push("인접 건물 확산 우려");
  }

  return { score: clamp(score, 0, 75), reasons };
}

function estimateDamage(input, totalScore) {
  const areaHa = Math.max(input.area / 10000, 0.02);
  const structureFactor = {
    concrete: 0.75,
    steel: 1.05,
    lightSteel: 1.35,
    wood: 1.5,
    sandwich: 1.45,
  }[input.structureType];
  const flameFactor = {
    small: 0.45,
    visible: 1,
    large: 1.9,
    flashover: 3.1,
  }[input.flameLevel];
  const spreadFactor = {
    contained: 0.5,
    room: 1,
    floor: 1.8,
    exposure: 3.2,
  }[input.spreadLevel];
  const windFactor = 1 + input.maxWind / 18;
  const drynessFactor = 1 + clamp((50 - input.effectiveHumidity) / 55, -0.2, 0.7);
  const delayFactor = 1 + input.responseDelay / 75;
  const dataTailBoost = Math.pow(totalScore / 100, 3) * MODEL_PROFILE.damageQuantiles.p95;

  const estimate = areaHa * structureFactor * flameFactor * spreadFactor * windFactor * drynessFactor * delayFactor + dataTailBoost;
  const low = Math.max(0.01, estimate * 0.72);
  const high = Math.max(low + 0.02, estimate * 1.28);

  return {
    estimate,
    low,
    high,
  };
}

function gradePrediction(totalScore, damage) {
  if (totalScore >= 85 || damage.estimate >= 30) {
    return {
      key: "critical",
      label: "매우 위험",
      description: "대형 피해 가능성이 높음",
    };
  }
  if (totalScore >= 68 || damage.estimate >= 1) {
    return {
      key: "high",
      label: "대규모",
      description: "확산 및 추가 지원 필요",
    };
  }
  if (totalScore >= 42 || damage.estimate >= 0.1) {
    return {
      key: "medium",
      label: "중규모",
      description: "초기 확대 방지 필요",
    };
  }
  return {
    key: "low",
    label: "소규모",
    description: "국소 대응 가능",
  };
}

function recommendResources(input, grade, totalScore) {
  const base = {
    low: { crew: 8, engines: 2, waterTenders: 0, rescue: 0, ambulances: 1 },
    medium: { crew: 16, engines: 3, waterTenders: 1, rescue: 1, ambulances: 1 },
    high: { crew: 28, engines: 5, waterTenders: 2, rescue: 1, ambulances: 2 },
    critical: { crew: 44, engines: 7, waterTenders: 3, rescue: 2, ambulances: 3 },
  }[grade.key];

  let crew = base.crew;
  const equipment = [
    `펌프차 ${base.engines}대`,
    `물탱크차 ${base.waterTenders}대`,
  ];

  if (input.floors >= 4 || input.fireFloor >= 4) {
    equipment.push("고가/굴절차 1대");
  }
  if (["dense", "zero"].includes(input.smokeLevel)) {
    equipment.push("배연 장비 및 열화상 카메라");
  }
  if (input.occupancy === "vulnerable" || input.occupancy === "high") {
    crew += 4;
    equipment.push(`구급대 ${base.ambulances + 1}대`);
  } else {
    equipment.push(`구급대 ${base.ambulances}대`);
  }
  if (totalScore >= 55) {
    equipment.push("RIT/신속동료구조팀 대기");
  }
  if (input.hasBasement === "yes" || input.fireFloor < 0) {
    equipment.push("지하층 진입 안전 확인조");
  }
  if (input.spreadLevel === "exposure") {
    equipment.push("인접 건물 방어 라인");
  }

  return {
    crew,
    engines: base.engines,
    waterTenders: base.waterTenders,
    rescue: base.rescue,
    ambulances: base.ambulances,
    equipment,
  };
}

function updatePlanView(input) {
  if (input.fireFloor < 0) {
    selectedPlan = "basement";
  }

  const config = PLAN_CONFIG[selectedPlan] ?? PLAN_CONFIG["main-floor"];
  const image = document.querySelector("#plan-image");
  const title = document.querySelector("#plan-title");
  const location = document.querySelector("#fire-location-readout");
  const entry = document.querySelector(".entry-marker");
  const fireMarker = document.querySelector("#fire-marker");
  const smoke = document.querySelector("#smoke-cloud");

  image.src = config.src;
  image.alt = config.alt;
  title.textContent = config.title;
  location.textContent = selectedPlan === "basement" ? config.location : `${input.fireFloor}층 중앙부`;

  entry.style.left = config.entry.left;
  entry.style.top = config.entry.top;
  entry.style.bottom = "auto";

  const marker = config.markers[input.flameLevel] ?? config.markers.visible;
  fireMarker.style.left = marker.left;
  fireMarker.style.top = marker.top;

  const smokeScale = {
    light: { width: 120, height: 82, opacity: 0.28 },
    medium: { width: 160, height: 105, opacity: 0.46 },
    dense: { width: 210, height: 136, opacity: 0.72 },
    zero: { width: 260, height: 166, opacity: 0.88 },
  }[input.smokeLevel];

  smoke.style.left = marker.left;
  smoke.style.top = marker.top;
  smoke.style.width = `${smokeScale.width}px`;
  smoke.style.height = `${smokeScale.height}px`;
  smoke.style.opacity = smokeScale.opacity;

  planButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.plan === selectedPlan);
  });
}

function formatHa(value) {
  if (value >= 10) {
    return `${value.toFixed(1)}ha`;
  }
  if (value >= 1) {
    return `${value.toFixed(2)}ha`;
  }
  return `${value.toFixed(3)}ha`;
}

function renderList(selector, items) {
  const list = document.querySelector(selector);
  list.innerHTML = "";

  const uniqueItems = [...new Set(items)].slice(0, 7);
  for (const item of uniqueItems) {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  }
}

function render(input, prediction) {
  const { weather, scene, totalScore, damage, grade, resources } = prediction;

  const gradeBadge = document.querySelector("#grade-badge");
  gradeBadge.className = `grade-badge ${grade.key}`;
  gradeBadge.textContent = `${grade.label} · ${grade.description}`;

  document.querySelector("#risk-score").textContent = String(totalScore);
  document.querySelector("#risk-fill").style.width = `${totalScore}%`;
  document.querySelector("#damage-range").textContent = `${formatHa(damage.low)} ~ ${formatHa(damage.high)}`;
  document.querySelector("#crew-count").textContent = `${resources.crew}명+`;
  document.querySelector("#engine-count").textContent = `${resources.engines}/${resources.waterTenders}대`;
  document.querySelector("#rescue-count").textContent = `${resources.rescue}팀 · ${resources.ambulances}대`;
  document.querySelector("#wind-label").textContent = `${input.maxWind.toFixed(1)} m/s`;
  document.querySelector("#mode-label").textContent = LABELS.buildingUse[input.buildingUse];

  const risks = [...weather.reasons, ...scene.reasons];
  renderList("#resource-list", resources.equipment);
  renderList("#risk-list", risks.length ? risks : ["현재 입력값 기준 특이 위험 요인은 낮음"]);

  updatePlanView(input);

  const coreReasons = risks.slice(0, 4).join(", ");
  const commanderAlert =
    `${LABELS.buildingUse[input.buildingUse]} ${input.fireFloor}층 화재는 ${grade.label} 단계로 추정됩니다. ` +
    `${resources.crew}명 이상과 ${resources.equipment.slice(0, 3).join(", ")} 투입을 검토하세요.`;

  document.querySelector("#commander-alert").textContent = commanderAlert;
  document.querySelector("#copilot-text").textContent =
    `현재 입력 기준 피해 규모는 ${grade.label}로 추정됩니다. ` +
    `예상 피해 영향면적은 ${formatHa(damage.low)}에서 ${formatHa(damage.high)} 범위이며, ` +
    `종합 위험도는 ${totalScore}점입니다. 주요 근거는 ${coreReasons || "화재 양상과 기상 조건"}입니다. ` +
    `초기 대응은 ${resources.crew}명 이상, ${resources.equipment.join(", ")} 중심으로 편성하는 것이 적절합니다. ` +
    `이 결과는 ${MODEL_PROFILE.rows.toLocaleString("ko-KR")}건의 강릉시 기상+산불 데이터 분포와 현장 보정 규칙을 사용한 MVP 추정입니다.`;
}

function predict(input) {
  const weather = scoreWeather(input);
  const scene = scoreScene(input);
  const totalScore = clamp(Math.round(weather.score * 0.55 + scene.score * 0.75), 0, 100);
  const damage = estimateDamage(input, totalScore);
  const grade = gradePrediction(totalScore, damage);
  const resources = recommendResources(input, grade, totalScore);

  return {
    weather,
    scene,
    totalScore,
    damage,
    grade,
    resources,
  };
}

function update() {
  const input = getInput();
  render(input, predict(input));
}

function applyPreset(name) {
  const preset = PRESETS[name];
  if (!preset) return;

  for (const [key, value] of Object.entries(preset)) {
    const field = form.elements[key];
    if (field) {
      field.value = value;
    }
  }

  presetButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.preset === name);
  });
  update();
}

form.addEventListener("input", update);
form.addEventListener("change", update);

presetButtons.forEach((button) => {
  button.addEventListener("click", () => applyPreset(button.dataset.preset));
});

planButtons.forEach((button) => {
  button.addEventListener("click", () => {
    selectedPlan = button.dataset.plan;
    update();
  });
});

applyPreset("spreading");
