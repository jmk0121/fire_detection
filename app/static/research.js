"use strict";
const $ = (id) => document.getElementById(id);
const labels = {unknown:"판단 자료 부족", below:"설정 기준 미도달", watch:"추가 확인 필요", criterion:"600°C 기준 도달", anomaly:"변형 이상 감지", estimated:"관성 위치 추정"};
const state = {catalog:null, data:null, module:"flashover", index:0, clock:0, playing:false, last:0, request:0};
const cache = new Map();
const fmt = (n, places=1) => Number.isFinite(n) ? n.toLocaleString("ko-KR", {maximumFractionDigits:places, minimumFractionDigits:places}) : "—";
const clock = (s) => `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,"0")}`;
const escape = (v) => String(v).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function json(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {let message = `HTTP ${response.status}`; try {message = (await response.json()).detail || message;} catch {} throw new Error(typeof message === "string" ? message : "입력값을 확인하세요.");}
  return response.json();
}
function pause() {state.playing=false; $("play").textContent="▶ 재생"; $("play").setAttribute("aria-label","실험 재생");}
function busy(value) {$("workspace").setAttribute("aria-busy",String(value)); ["experiment","play","timeline","jump"].forEach(id=>$(id).disabled=value);}
function showError(error) {pause(); $("load-error").hidden=false; $("load-error").textContent=`데이터를 불러오지 못했습니다. ${error.message} · 연결을 확인한 뒤 페이지를 새로 고침하세요.`;}
async function chooseModule(module) {
  pause(); state.module=module;
  document.querySelectorAll(".module").forEach(b=>{const active=b.dataset.module===module;b.classList.toggle("active",active);b.setAttribute("aria-pressed",String(active));});
  const items=state.catalog.experiments.filter(x=>x.module===module);
  $("experiment").replaceChildren(...items.map(x=>new Option(x.title,x.id)));
  $("experiment").value={flashover:"flash-4",position:"walk-3",collapse:"beam-9"}[module];
  await loadExperiment($("experiment").value);
}
async function loadExperiment(id) {
  const request=++state.request; pause(); busy(true); $("load-error").hidden=true;
  try {
    const data=cache.get(id)||await json(`/api/v1/research/experiments/${encodeURIComponent(id)}`);
    if(request!==state.request)return;
    cache.set(id,data);state.data=data;state.index=0;state.clock=data.points[0].t;
    $("split").textContent=data.split;$("data-kind").textContent=data.kind;
    $("csv-link").href=`/api/v1/research/experiments/${encodeURIComponent(id)}/csv`;
    $("timeline").max=data.points.length-1;$("timeline").value=0;
    $("duration").textContent=clock(data.duration_s);
    renderMethod();renderMetrics();render();busy(false);
  } catch(error) {if(request===state.request){busy(false);$("play").disabled=true;$("timeline").disabled=true;$("jump").disabled=true;showError(error);}}
}
function reading(name,value,unit,places=1) {return `<div><dt>${name}</dt><dd>${fmt(value,places)}<small>${unit}</small></dd></div>`;}
function render() {
  const d=state.data,p=d.points[state.index],module=d.module;
  $("timeline").value=state.index;$("timeline").setAttribute("aria-valuetext",`${clock(p.t)}、${labels[p.state]}`);
  $("time-label").textContent=`${clock(p.t)} / ${clock(d.duration_s)}`;
  $("status").dataset.state=p.state;$("status-text").textContent=labels[p.state];
  $("status-symbol").textContent={unknown:"○",below:"◇",watch:"△",criterion:"!",anomaly:"!",estimated:"⌖"}[p.state];
  if(module==="flashover") {
    $("plot-title").textContent="고온층 온도와 60초 전망";
    $("legend").innerHTML="<span>관측 기반 고온층 온도</span><span>각 시점의 60초 전망</span><span>600°C 대리지표</span>";
    $("readings").innerHTML=reading("현재 고온층",p.temperature_c,"°C")+reading("최근 온도 기울기",p.slope_c_min,"°C/min")+reading("60초 뒤 전망",p.predicted_c,"°C");
    $("reason").textContent=p.state==="unknown"?"60초 추세 구간이 부족하거나 원본 온도값이 누락되었습니다.":p.state==="criterion"?"현재 고온층 온도가 설정한 600°C 기준에 도달했습니다.":p.state==="watch"?"최근 상승 추세가 유지되면 60초 뒤 600°C 기준에 도달할 것으로 계산됩니다.":"현재 온도와 60초 전망이 모두 설정한 기준보다 낮습니다.";
    $("boundary").textContent="600°C는 검증용 대리지표입니다. 실제 플래시오버 확인·발생 확률이나 안전 보장을 뜻하지 않습니다.";
    $("chart-note").textContent="현재 시점까지의 데이터만 표시합니다. 점선은 각 시점에서 계산한 전망값이며, 센서 측정값이 아닙니다.";
    drawSeries([{key:"temperature_c",color:"#75bbef"},{key:"predicted_c",color:"#ffc16e",dash:true}],600,"°C");
  } else if(module==="collapse") {
    $("plot-title").textContent="구조 변위의 변화";
    $("legend").innerHTML="<span>초기 대비 수직 변위</span><span>변위 참고선</span>";
    $("readings").innerHTML=reading("초기 대비 변위",p.displacement_mm,"mm")+reading("20초 변위 기울기",p.rate_mm_min,"mm/min")+reading("보 온도 · tc17",p.temperature_c,"°C");
    $("reason").textContent=p.state==="unknown"?"초기 60초는 참조 구간입니다. 변위 또는 기울기가 없으면 판단을 보류합니다.":p.state==="anomaly"?"변위와 변화 속도가 참고 기준을 함께 5초 이상 초과한 이력이 있어 경보를 유지합니다.":p.state==="watch"?"변위 또는 변화 속도 중 하나가 참고 기준을 초과했습니다.":"현재 변위와 변화 속도가 설정한 참고 기준 아래에 있습니다.";
    $("boundary").textContent="강재 보 한 개의 변형 이상 감지입니다. 건물 붕괴 확률·붕괴 시각으로 해석할 수 없습니다. 미감지도 가능합니다.";
    $("chart-note").textContent="변위만 차트에 표시합니다. 온도는 기체가 아닌 보의 tc17 측정값이며 판정 입력으로 사용하지 않습니다.";
    drawSeries([{key:"displacement_mm",color:"#75bbef"}],d.thresholds.displacement_mm,"mm");
  } else {
    $("plot-title").textContent="보행 궤적과 누적 오차";
    $("legend").innerHTML="<span>발 부착 INS 기준 궤적</span><span>관성 보행 추정</span>";
    $("readings").innerHTML=reading("동쪽 좌표",p.east_m,"m")+reading("북쪽 좌표",p.north_m,"m")+reading("기준 궤적과 거리",p.error_m,"m");
    $("reason").textContent=p.state==="unknown"?"초기 10초 기준 경로로 시작 방향을 설정하고 있습니다. 이 구간은 평가에서 제외합니다.":"가속도에서 감지한 걸음마다 보폭을 더하고, 자이로 회전량으로 이동 방향을 갱신합니다.";
    $("boundary").textContent="기준 경로는 검증용 발 부착 INS 추정값입니다. 지도·UWB 보정이 없는 보행 실험이며 현재 오차는 사후 비교값입니다.";
    $("chart-note").textContent="동·북 좌표(m), 동일 축척. 초기 방향 보정 이후 기준 궤적은 위치 계산에 사용하지 않습니다. 건물 평면도가 아닙니다.";
    drawPosition();
  }
  renderEvents();
}
function pathFor(points,x,y) {let path="",open=false;for(const p of points){const a=x(p),b=y(p);if(!Number.isFinite(a)||!Number.isFinite(b)){open=false;continue;}path+=`${open?"L":"M"}${a.toFixed(2)},${b.toFixed(2)} `;open=true;}return path;}
function chartBase(title,desc,body) {$("chart").innerHTML=`<title id="chart-title">${escape(title)}</title><desc id="chart-desc">${escape(desc)}</desc>${body}`;}
function drawSeries(series,threshold,unit) {
  const d=state.data,points=d.points.slice(0,state.index+1),all=d.points;
  const values=all.flatMap(p=>series.map(s=>p[s.key])).filter(Number.isFinite);
  const ymin=Math.min(0,...values),ymax=Math.max(threshold*1.1,...values)*1.08;
  const x=t=>58+710*t/d.duration_s,y=v=>v===null?NaN:280-(v-ymin)/(ymax-ymin)*240;
  let body="";
  for(let i=0;i<=4;i++){const yy=40+60*i,value=ymax-(ymax-ymin)*i/4;body+=`<line x1="58" y1="${yy}" x2="768" y2="${yy}" stroke="#334150"/><text x="48" y="${yy+4}" fill="#acb9c8" text-anchor="end" font-size="11">${fmt(value,0)}</text>`;}
  for(let i=0;i<=4;i++){const at=d.duration_s*i/4;body+=`<text x="${x(at)}" y="307" fill="#acb9c8" text-anchor="middle" font-size="11">${clock(at)}</text>`;}
  body+=`<text x="20" y="20" fill="#acb9c8" font-size="11">${unit}</text><line x1="58" y1="${y(threshold)}" x2="768" y2="${y(threshold)}" stroke="${d.module==="flashover"?"#ff8f83":"#ffc16e"}" stroke-dasharray="5 5" opacity=".7"/>`;
  for(const s of series) body+=`<path d="${pathFor(points,p=>x(p.t),p=>y(p[s.key]))}" fill="none" stroke="${s.color}" stroke-width="2.5" ${s.dash?'stroke-dasharray="6 4"':""}/>`;
  const p=points.at(-1);body+=`<line x1="${x(p.t)}" x2="${x(p.t)}" y1="40" y2="280" stroke="#b5c1cf" stroke-dasharray="3 5" opacity=".6"/>`;
  for(const s of series) if(Number.isFinite(p[s.key]))body+=`<circle cx="${x(p.t)}" cy="${y(p[s.key])}" r="4" fill="${s.color}"/>`;
  chartBase($("plot-title").textContent,`${clock(p.t)}. ${$("reason").textContent} 정확한 수치는 현재 판단에서 확인할 수 있습니다.`,body);
}
function drawPosition() {
  const all=state.data.points,points=all.slice(0,state.index+1);
  const east=all.flatMap(p=>[p.east_m,p.ref_east_m]).filter(Number.isFinite),north=all.flatMap(p=>[p.north_m,p.ref_north_m]).filter(Number.isFinite);
  const emin=Math.min(...east),emax=Math.max(...east),nmin=Math.min(...north),nmax=Math.max(...north);
  const scale=Math.min(650/Math.max(emax-emin,1),230/Math.max(nmax-nmin,1)),ec=(emin+emax)/2,nc=(nmin+nmax)/2;
  const x=v=>v===null?NaN:410+(v-ec)*scale,y=v=>v===null?NaN:160-(v-nc)*scale;
  let body="";
  for(let i=0;i<=4;i++){let a=60+i*177.5,b=40+i*60;body+=`<line x1="${a}" y1="40" x2="${a}" y2="280" stroke="#334150"/><line x1="60" y1="${b}" x2="770" y2="${b}" stroke="#334150"/><text x="${a}" y="303" fill="#acb9c8" font-size="11" text-anchor="middle">${fmt((a-410)/scale+ec,0)}</text><text x="50" y="${b+4}" fill="#acb9c8" font-size="11" text-anchor="end">${fmt((160-b)/scale+nc,0)}</text>`;}
  body+='<text x="12" y="20" fill="#acb9c8" font-size="11">북 N (m)</text><text x="770" y="328" fill="#acb9c8" font-size="11" text-anchor="end">동 E (m)</text>';
  for(const [e,n,color] of [["ref_east_m","ref_north_m","#75bbef"],["east_m","north_m","#ffc16e"]]){body+=`<path d="${pathFor(points,p=>x(p[e]),p=>y(p[n]))}" stroke="${color}" stroke-width="2.5" fill="none"/>`;const p=points.at(-1);if(Number.isFinite(p[e]))body+=`<circle cx="${x(p[e])}" cy="${y(p[n])}" r="5" fill="${color}"/>`;}
  chartBase("관성 보행 추정과 기준 궤적",`${clock(points.at(-1).t)} 시점까지의 동쪽·북쪽 이동 경로. 파란색은 기준, 황색은 추정 경로입니다.`,body);
}
function renderEvents() {
  const points=state.data.points.slice(0,state.index+1),events=[];
  for(let i=1;i<points.length;i++)if(points[i].state!==points[i-1].state)events.push(points[i]);
  $("event-count").textContent=`${events.length}회 전환`;
  $("events").innerHTML=events.length?events.slice(-5).reverse().map(p=>`<li><time>${clock(p.t)}</time><span>${labels[p.state]}</span></li>`).join(""):'<li class="empty">아직 상태 변화가 없습니다.</li>';
}
const metric=(value,label,unit="")=>`<div class="metric"><strong>${value}<small> ${unit}</small></strong><span>${label}</span></div>`;
function renderMetrics() {
  const d=state.data,m=d.metrics;
  if(d.module==="flashover"){
    const c=m.confusion.trend,b=m.confusion.temperature_400;
    $("metrics").innerHTML=metric(`${c.tp} / ${c.tp+c.fn}`,"도달 전 60초 구간 탐지")+metric(c.fp,"기준 미도달 구간의 오탐","구간")+metric(fmt(m.lead_s,0),"유효 경보의 최대 선행 시간","초");
    const total=state.catalog.experiments.filter(x=>x.module==="flashover"&&x.id!=="flash-1").reduce((a,x)=>{for(const k of ["tp","fp","fn","tn"])a[k]+=x.metrics.confusion.trend[k];return a;},{tp:0,fp:0,fn:0,tn:0});
    $("metric-note").textContent=`이 실험의 현재 온도 400°C 비교 규칙: 탐지 ${b.tp}, 미탐 ${b.fn}, 오탐 ${b.fp} 구간. 분리 평가(Test 2–4) 추세 규칙 합계: 탐지 ${total.tp}, 미탐 ${total.fn}, 오탐 ${total.fp}. 구간은 서로 겹치며 독립 표본이 아닙니다. 기준 도달 실험은 1건뿐이므로 성능 일반화는 불가합니다. 마지막 60초·결측·첫 기준 도달 이후는 평가에서 제외합니다.`;
  }else if(d.module==="position"){
    $("metrics").innerHTML=metric(fmt(m.mean_error_m),"평균 위치 오차","m")+metric(fmt(m.p95_error_m),"오차 95백분위","m")+metric(fmt(m.end_error_m),"종료 지점 오차","m");
    $("metric-note").textContent=m.limitation;
  }else{
    $("metrics").innerHTML=metric(m.first_anomaly_s===null?"미감지":clock(m.first_anomaly_s),"첫 결합 기준 경보")+metric(fmt(m.max_displacement_mm),"최대 절대 변위","mm")+metric("평가 불가","붕괴 예측 정확도");
    $("metric-note").textContent=m.limitation+". Test 8은 기록된 변형에도 결합 경보가 발생하지 않았습니다. 범용 붕괴 기준으로 사용할 수 없음을 보여주는 사례입니다.";
  }
}
function renderMethod(){
  const d=state.data,k=d.thresholds;
  const methods={
    flashover:`<div class="formula">T̂(t+60) = T(t) + max(0, 최근 60초의 선형 기울기) × 60</div><div class="method-steps"><div><h3>01 · 변화 읽기</h3><p>과거 60초 고온층 온도에 최소제곱 직선을 맞춥니다. 현재 시점 이후의 측정은 입력하지 않습니다.</p></div><div><h3>02 · 조건 비교</h3><p>60초 전망 ≥ 600°C이면 추가 확인, 현재값 ≥ 600°C이면 기준 도달입니다. 값 누락·구간 부족은 판단 자료 부족으로 표시합니다.</p></div><div><h3>03 · 별도 실험 평가</h3><p>Test 1에서 동작을 확인하고 Test 2–4를 평가합니다. 비교 기준은 현재값 400°C 이상입니다. 경보 기준은 실험용 설계 선택입니다.</p></div></div><p>환기·연료가 바뀌면 직선 전망은 빗나갈 수 있습니다. 600°C 기준은 고온층에 관한 대리지표이며 임의 위치 센서나 체온에 적용하지 않습니다. 이 구현은 NIST P-Flash 모델의 재현이 아닙니다.</p>`,
    collapse:`<div class="formula">|Δ변위| ≥ ${fmt(k.displacement_mm)} mm AND |20초 기울기| ≥ ${fmt(k.rate_mm_min)} mm/min, 5초 지속</div><div class="method-steps"><div><h3>01 · 기준 보정</h3><p>Test 7 초기 60초의 중앙값 + 6 × 1.4826 × MAD로 기준을 고정합니다. 하한 3 mm, 0.5 mm/min은 시연용 설계값입니다.</p></div><div><h3>02 · 두 징후 결합</h3><p>변위와 변화 속도를 함께 확인해 순간 변화만으로 경보하지 않습니다. 결합 조건이 5초 지속되면 경보 이력을 유지합니다.</p></div><div><h3>03 · 적용 범위 확인</h3><p>Test 8·9에 같은 기준을 적용합니다. 초기 구간은 건강한 모든 구조물의 분포가 아니며, 미감지와 구조별 차이를 검토해야 합니다.</p></div></div><p>선행 보고서는 진동수·감쇠·변위 융합을 제안하지만, 이번 공개 데이터로는 진동 기반 붕괴 예측을 검증할 수 없습니다. 논문의 가정 임계값 −2.75도 가져오지 않았습니다.</p>`,
    position:`<div class="formula">N ← N + 보폭 × cos(방향) · E ← E + 보폭 × sin(방향)</div><div class="method-steps"><div><h3>01 · 걸음 감지</h3><p>가속도 크기에서 중력을 빼고 인과적 저역 통과 필터를 적용합니다. 1.0 m/s² 이상 봉우리, 최소 0.28초 간격을 걸음으로 셉니다.</p></div><div><h3>02 · 방향과 보폭</h3><p>처음 40초 정지 구간에서 자이로 바이어스를 보정합니다. 보폭 ${fmt(k.step_length_m,3)} m는 TEST 02에서만 맞추고 TEST 03·04에 고정합니다.</p></div><div><h3>03 · 오차 공개</h3><p>각 궤적 초기 10초의 기준 이동으로 시작 방향을 설정한 뒤 오차를 평가합니다. 이후 UWB/GNSS 보정은 없으므로 오차가 누적됩니다.</p></div></div><p>실내 절대 위치를 얻으려면 출입구 기준 좌표·방향 또는 UWB 앵커가 필요합니다. 자력계 교란, 센서 기울기, 포복·계단·무동작, 통신 단절은 추가 연구 과제입니다. 실제 UWB 관측은 이 데이터에 없습니다.</p>`};
  $("method-content").innerHTML=methods[d.module];
}
function renderSources(){
  const specs=[{id:"flashover_4",title:"UL/NIST 환기 실험",text:"가스버너 화재 4건 · 고온층 온도 · 공식 firemodels 원본. 아래 체크섬·다운로드는 실험 4 원본이며 전체 목록은 공개 출처에서 확인합니다.",download:"flashover_4"},{id:"position",title:"ULISS 보행 센서",text:"Fu, Hanyuan · Université Gustave Eiffel. IMU와 발 부착 기준 궤적. TEST 02·03·04를 사용했습니다. Etalab 2.0.",download:"position"},{id:"collapse",title:"NIST 강재 보 가열 실험",text:"수직 변위·온도 등 계측. Test 7 초기 기준 보정, Test 8·9에 분리 적용했습니다. NIST 공개 이용 조건.",download:"collapse"}];
  $("sources").innerHTML=specs.map(x=>{const s=state.catalog.sources.find(v=>v.id===x.id);return `<article class="source"><h3>${x.title}</h3><p>${x.text}</p><p>SHA-256 <code title="${s.sha256}">${s.sha256.slice(0,20)}…</code></p><a href="${escape(s.landing)}" target="_blank" rel="noopener noreferrer">공개 출처 ↗</a><a href="/api/v1/research/sources/${x.download}">원본 ↓</a><a href="${escape(s.license)}" target="_blank" rel="noopener noreferrer">이용 조건 ↗</a></article>`;}).join("");
}
document.querySelectorAll(".module").forEach(b=>b.addEventListener("click",()=>{if(state.catalog)chooseModule(b.dataset.module);}));
$("experiment").addEventListener("change",()=>loadExperiment($("experiment").value));
$("timeline").addEventListener("input",()=>{pause();state.index=Number($("timeline").value);state.clock=state.data.points[state.index].t;render();});
$("jump").addEventListener("click",()=>{pause();const d=state.data;const target=d.module==="flashover"?(d.metrics.first_600_s===null?d.duration_s*.6:Math.max(0,d.metrics.first_600_s-60)):d.module==="collapse"?(d.metrics.first_anomaly_s===null?d.duration_s*.9:Math.max(0,d.metrics.first_anomaly_s-20)):d.duration_s*.6;state.index=d.points.findIndex(p=>p.t>=target);state.clock=d.points[state.index].t;render();});
$("play").addEventListener("click",()=>{if(state.playing){pause();return;}if(state.index===state.data.points.length-1){state.index=0;state.clock=state.data.points[0].t;}state.playing=true;state.last=performance.now();$("play").textContent="Ⅱ 일시정지";$("play").setAttribute("aria-label","실험 일시정지");});
setInterval(()=>{if(!state.playing||!state.data)return;const now=performance.now();state.clock+=Math.min(now-state.last,1000)/1000*Number($("speed").value);state.last=now;let changed=false;while(state.index<state.data.points.length-1&&state.data.points[state.index+1].t<=state.clock){state.index++;changed=true;}if(changed)render();if(state.index===state.data.points.length-1)pause();},100);
document.addEventListener("visibilitychange",()=>{if(document.hidden)pause();});
$("uwb-form").addEventListener("submit",async e=>{e.preventDefault();const output=$("uwb-result");try{const result=await json("/api/v1/research/uwb",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({anchors:[[0,0],[10,0],[0,10]],ranges:["range-a","range-b","range-c"].map(id=>Number($(id).value))})});output.textContent=`추정 좌표 (${fmt(result.x,2)}, ${fmt(result.y,2)}) m · 거리 잔차 RMS ${fmt(result.residual_m,3)} m. ${result.residual_m>1?"거리 불일치가 큽니다. 장애물·앵커 배치를 확인해야 합니다.":"이 잔차는 위치 오차 보장값이 아닙니다."}`;}catch(error){output.textContent=`계산 불가: ${error.message}`;}});
(async()=>{try{busy(true);state.catalog=await json("/api/v1/research/catalog");renderSources();await chooseModule("flashover");}catch(error){busy(false);showError(error);}})();
