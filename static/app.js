/* 주린이 뉴스 번역기 프론트엔드 */
"use strict";

// API URL 동적 설정 (Vercel 배포 시 환경 변수 사용)
const API_BASE_URL = window.__API_BASE_URL__ || '';

// ---------------------------------------------------------------------------
// 샘플 기사
// ---------------------------------------------------------------------------
const SAMPLES = [
  "미국 연준이 매파적 기조를 이어가면서 기준금리 인하 기대가 후퇴했다. 이에 따라 글로벌 증시의 밸류에이션 부담이 다시 부각되고 있다. 다만 삼성전자와 SK하이닉스는 HBM 수요 확대에 힘입어 실적 컨센서스가 상향 조정되는 중이다. 외국인 투자자들은 반도체 업종을 중심으로 순매수를 이어갔다. 일각에서는 공매도 재개와 환율 변동성이 단기 조정의 빌미가 될 수 있다는 지적도 나온다.",
  "전기차 캐즘 우려에도 불구하고 LG에너지솔루션은 북미 신규 수주 모멘텀이 부각되며 강세를 보였다. 2차전지 소재주인 에코프로비엠과 포스코퓨처엠도 동반 상승했다. 현대차와 기아는 어닝서프라이즈를 기록하며 주주환원 확대 기대감을 키웠다. 증권가는 배당수익률과 자사주 소각 규모를 근거로 완성차 업종의 목표주가를 리레이팅하고 있다.",
  "한화에어로스페이스는 폴란드향 수출 계약이 반영되며 방산 업종 수주 잔고가 사상 최대치를 경신했다. LIG넥스원과 현대로템도 국방 예산 확대의 수혜주로 꼽힌다. 한편 조선 업종에서는 한화오션이 LNG선 수주 소식에 급등했고, 삼성중공업은 해양플랜트 수주 기대감이 유효하다. 다만 일부 종목은 단기 급등에 따른 밸류에이션 부담으로 블록딜 매물이 출회될 수 있다는 경계감도 있다.",
];

// ---------------------------------------------------------------------------
// 공통 유틸
// ---------------------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function fmtPrice(n) {
  return n.toLocaleString("ko-KR");
}
function changeClass(v) {
  return v > 0 ? "up" : v < 0 ? "down" : "flat";
}
function changeSign(v) {
  return v > 0 ? "▲" : v < 0 ? "▼" : "―";
}

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// 실행 모드
// ---------------------------------------------------------------------------
const actionBtn = $("#action-btn");
const articleInput = $("#article-input");
const errorBox = $("#error-box");
const modeButtons = document.querySelectorAll(".mode-btn");
const quizCountSelect = $("#quiz-count");
const resultSection = $("#result-section");
const quizSection = $("#quiz-section");
const quizList = $("#quiz-list");
const quizMeta = $("#quiz-meta");
const quizResult = $("#quiz-result");
const quizSubmitBtn = $("#quiz-submit");

let appMode = "translate";
let currentQuiz = [];
let selectedAnswers = {};

function setMode(nextMode) {
  appMode = nextMode;
  modeButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === nextMode);
  });
  actionBtn.textContent = nextMode === "translate" ? "쉬운 말로 번역하기" : "퀴즈 만들어 보기";
  quizCountSelect.closest(".quiz-controls").classList.toggle("hidden", nextMode !== "quiz");
  errorBox.hidden = true;
}

modeButtons.forEach((btn) => {
  btn.addEventListener("click", () => setMode(btn.dataset.mode));
});

setMode("translate");

document.querySelectorAll(".sample-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    articleInput.value = SAMPLES[Number(btn.dataset.sample)];
    articleInput.focus();
  });
});

actionBtn.addEventListener("click", async () => {
  if (appMode === "translate") {
    await runTranslate();
    return;
  }
  await runQuiz();
});

async function runTranslate() {
  const text = articleInput.value.trim();
  errorBox.hidden = true;
  if (!text) {
    errorBox.textContent = "먼저 기사를 붙여넣어 주세요.";
    errorBox.hidden = false;
    return;
  }

  actionBtn.disabled = true;
  actionBtn.textContent = "번역 중…";
  try {
    const data = await fetchJSON(API_BASE_URL + "/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    resultSection.hidden = false;
    quizSection.hidden = true;
    renderResult(data);
  } catch (err) {
    errorBox.textContent = `번역에 실패했어요: ${err.message}`;
    errorBox.hidden = false;
  } finally {
    actionBtn.disabled = false;
    actionBtn.textContent = "쉬운 말로 번역하기";
  }
}

async function runQuiz() {
  const text = articleInput.value.trim();
  errorBox.hidden = true;
  if (!text) {
    errorBox.textContent = "먼저 기사를 붙여넣어 주세요.";
    errorBox.hidden = false;
    return;
  }

  actionBtn.disabled = true;
  actionBtn.textContent = "퀴즈 생성 중…";
  selectedAnswers = {};

  try {
    const data = await fetchJSON(API_BASE_URL + "/api/quiz", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        question_count: Number(quizCountSelect.value || 10),
      }),
    });
    resultSection.hidden = true;
    quizSection.hidden = false;
    renderQuiz(data);
  } catch (err) {
    errorBox.textContent = `퀴즈 생성 실패: ${err.message}`;
    errorBox.hidden = false;
  } finally {
    actionBtn.disabled = false;
    actionBtn.textContent = "퀴즈 만들어 보기";
  }
}

// ---------------------------------------------------------------------------
// 결과 렌더링
// ---------------------------------------------------------------------------
function decorateText(text, mentions, terms) {
  const pats = [];
  for (const m of mentions) {
    pats.push({ t: m.text, type: "ticker", data: m });
  }
  for (const t of terms) {
    pats.push({ t: t.term, type: "term", data: t });
  }
  pats.sort((a, b) => b.t.length - a.t.length);
  if (!pats.length) return escapeHtml(text);

  const re = new RegExp(pats.map((p) => escapeRegex(p.t)).join("|"), "g");
  let out = "";
  let last = 0;
  for (const m of text.matchAll(re)) {
    out += escapeHtml(text.slice(last, m.index));
    const p = pats.find((p) => p.t === m[0]);
    if (p.type === "ticker") {
      out += `<span class="ticker" data-code="${escapeHtml(p.data.code)}" title="클릭하면 차트가 열려요">${escapeHtml(m[0])}</span>`;
    } else {
      out += `<span class="term" data-term="${escapeHtml(p.data.term)}" data-easy="${escapeHtml(p.data.easy)}" data-desc="${escapeHtml(p.data.desc)}">${escapeHtml(m[0])}</span>`;
    }
    last = m.index + m[0].length;
  }
  out += escapeHtml(text.slice(last));
  return out;
}

function renderResult(data) {
  resultSection.hidden = false;
  quizSection.hidden = true;

  const noticeBox = $("#notice-box");
  noticeBox.hidden = !data.notice;
  noticeBox.textContent = data.notice || "";

  const summaryCard = $("#summary-card");
  summaryCard.hidden = !data.summary;
  $("#summary-text").textContent = data.summary || "";

  const container = $("#sentences");
  container.innerHTML = "";

  for (const s of data.sentences) {
    const block = document.createElement("div");
    block.className = "sentence-block" + (s.hard ? " hard" : "");
    block._related = s.related;
    block._products = s.products || [];

    let html = "";
    if (s.hard) html += `<span class="hard-chip">🔥 특히 어려운 문장</span>`;
    html += `<div class="sentence-original">${decorateText(s.original, s.mentions, s.terms)}</div>`;
    html += `<div class="sentence-easy">${decorateText(s.easy, s.mentions, s.terms)}</div>`;
    if (s.related.length) {
      html += `<span class="related-badge">📈 관련 종목 ${s.related.length}개 — 마우스를 올려보세요</span>`;
    }
    block.innerHTML = html;

    block.addEventListener("mouseenter", () => schedulePopover(block));
    block.addEventListener("mouseleave", scheduleHidePopover);
    container.appendChild(block);
  }

  resultSection.scrollIntoView({ behavior: "smooth" });
}

function renderQuiz(data) {
  currentQuiz = data.questions || [];
  quizList.innerHTML = "";
  selectedAnswers = {};
  quizSubmitBtn.disabled = true;
  quizResult.hidden = true;

  if (!currentQuiz.length) {
    quizMeta.textContent = "현재 문장으로 생성 가능한 퀴즈가 없습니다.";
    quizList.innerHTML = `<p class="quiz-empty">기사 내용을 바꿔서 다시 시도해 보세요.</p>`;
    quizSubmitBtn.disabled = true;
    return;
  }

  quizMeta.textContent = `총 ${currentQuiz.length}문항`;
  currentQuiz.forEach((q, idx) => {
    const item = document.createElement("div");
    item.className = "quiz-item";
    item.dataset.qid = q.id;

    const prompt = document.createElement("div");
    prompt.className = "quiz-prompt";
    prompt.textContent = `${idx + 1}. ${q.prompt}`;
    item.appendChild(prompt);

    const optionWrap = document.createElement("div");
    optionWrap.className = "quiz-option-list";

    q.options.forEach((opt, optionIndex) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "quiz-choice";
      btn.dataset.qid = q.id;
      btn.dataset.index = String(optionIndex);
      btn.textContent = opt;
      optionWrap.appendChild(btn);
    });

    const hint = document.createElement("div");
    hint.className = "quiz-feedback";
    hint.dataset.qid = q.id;
    hint.hidden = true;

    item.appendChild(optionWrap);
    item.appendChild(hint);
    quizList.appendChild(item);
  });

  quizList.scrollIntoView({ behavior: "smooth" });
}

// ---------------------------------------------------------------------------
// 관련 종목 팝오버
// ---------------------------------------------------------------------------
const popover = $("#stock-popover");
let popShowTimer = null;
let popHideTimer = null;
let popToken = 0;

const quoteCache = new Map();
async function getQuote(code) {
  if (!quoteCache.has(code)) {
    quoteCache.set(code, fetchJSON(API_BASE_URL + `/api/stocks/${code}`).catch((e) => {
      quoteCache.delete(code);
      throw e;
    }));
  }
  return quoteCache.get(code);
}

popover.addEventListener("mouseenter", () => clearTimeout(popHideTimer));
popover.addEventListener("mouseleave", scheduleHidePopover);

function schedulePopover(block) {
  clearTimeout(popShowTimer);
  clearTimeout(popHideTimer);
  const hasContent = (block._related && block._related.length) || (block._products && block._products.length);
  if (!hasContent) return;
  popShowTimer = setTimeout(() => showPopover(block), 220);
}

function scheduleHidePopover() {
  clearTimeout(popShowTimer);
  clearTimeout(popHideTimer);
  popHideTimer = setTimeout(() => { popover.hidden = true; }, 250);
}

function riskClass(risk) { return risk <= 2 ? "low" : risk <= 4 ? "mid" : "high"; }

function productsHtml(products) {
  if (!products.length) return "";
  return (
    `<div class="popover-title">🧺 관련 금융상품 (ETF·펀드)</div>` +
    products.map((p) => `
      <div class="product-row" data-code="${escapeHtml(p.code)}" title="${escapeHtml(p.desc)}">
        <div>
          <div class="name">${escapeHtml(p.name)}
            <span class="type-chip${p.type === "펀드" ? " fund" : ""}">${escapeHtml(p.type)}</span></div>
          <div class="reason">${escapeHtml(p.reason)} · ${escapeHtml(p.asset)}</div>
        </div>
        <div class="prod-meta">
          <span class="risk-chip ${riskClass(p.risk)}">위험 ${p.risk}등급</span>
          <span class="prod-expense">연보수 ${p.expense}%</span>
        </div>
      </div>`).join("") +
    `<div class="disclaimer">※ 투자 권유가 아닌 참고 정보예요.</div>`
  );
}

async function showPopover(block) {
  const token = ++popToken;
  const related = block._related || [];
  const products = block._products || [];

  popover.innerHTML =
    `<div class="popover-title">📈 이 문장과 관련된 종목</div>` +
    `<div class="popover-loading">시세를 불러오는 중…</div>`;
  popover.hidden = false;
  positionPopover(block);

  let quotes;
  try {
    quotes = await Promise.all(related.map((r) =>
      getQuote(r.code).then((q) => ({ ...q, reason: r.reason })).catch(() => null)
    ));
  } catch (_) {
    quotes = [];
  }
  if (token !== popToken || popover.hidden) return;

  const rows = quotes.filter(Boolean);
  if (!rows.length && !products.length) {
    popover.innerHTML = `<div class="popover-empty">시세를 불러오지 못했어요.</div>`;
    return;
  }

  let html = "";
  if (rows.length) {
    html +=
      `<div class="popover-title">📈 이 문장과 관련된 종목 — 누르면 차트가 열려요</div>` +
      rows.map((q) => `
        <div class="stock-row" data-code="${q.code}">
          <div>
            <div class="name">${escapeHtml(q.name)}</div>
            <div class="reason">${escapeHtml(q.reason)} · ${q.code}</div>
          </div>
          <canvas class="spark" width="64" height="26" data-spark="${q.spark.join(",")}" data-dir="${changeClass(q.change)}"></canvas>
          <div class="quote ${changeClass(q.change)}">
            ${fmtPrice(q.price)}
            <span class="pct">${changeSign(q.change)} ${Math.abs(q.change_pct)}%</span>
          </div>
        </div>`).join("");
  }
  html += productsHtml(products);
  popover.innerHTML = html;

  popover.querySelectorAll("canvas.spark").forEach(drawSparkline);
  popover.querySelectorAll(".stock-row, .product-row").forEach((row) => {
    row.addEventListener("click", () => {
      popover.hidden = true;
      openChart(row.dataset.code);
    });
  });
  positionPopover(block);
}

function positionPopover(block) {
  const rect = block.getBoundingClientRect();
  const popW = popover.offsetWidth || 320;
  const popH = popover.offsetHeight || 200;
  let left = window.scrollX + rect.right - popW;
  left = Math.max(window.scrollX + 8, Math.min(left, window.scrollX + window.innerWidth - popW - 8));
  let top = window.scrollY + rect.bottom + 6;
  if (rect.bottom + popH + 16 > window.innerHeight) {
    top = window.scrollY + rect.top - popH - 6;
  }
  popover.style.left = `${left}px`;
  popover.style.top = `${Math.max(window.scrollY + 8, top)}px`;
}

function drawSparkline(canvas) {
  const values = canvas.dataset.spark.split(",").map(Number);
  const dir = canvas.dataset.dir;
  const dpr = window.devicePixelRatio || 1;
  const w = 64, h = 26;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const color = dir === "up" ? "#d93025" : dir === "down" ? "#1a73e8" : "#9ca3af";

  ctx.beginPath();
  values.forEach((v, i) => {
    const x = (i / (values.length - 1)) * (w - 2) + 1;
    const y = h - 3 - ((v - min) / span) * (h - 6);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

// ---------------------------------------------------------------------------
// 용어 툴팁
// ---------------------------------------------------------------------------
const tooltip = $("#term-tooltip");

document.addEventListener("mouseover", (e) => {
  const term = e.target.closest(".term");
  if (!term) return;
  tooltip.innerHTML =
    `<span class="tt-term">${escapeHtml(term.dataset.term)}</span>` +
    `<span class="tt-easy">= ${escapeHtml(term.dataset.easy)}</span>` +
    `<span class="tt-desc">${escapeHtml(term.dataset.desc)}</span>`;
  tooltip.hidden = false;
  const rect = term.getBoundingClientRect();
  const ttW = tooltip.offsetWidth;
  let left = window.scrollX + rect.left;
  left = Math.min(left, window.scrollX + window.innerWidth - ttW - 8);
  tooltip.style.left = `${Math.max(8, left)}px`;
  tooltip.style.top = `${window.scrollY + rect.bottom + 6}px`;
});
document.addEventListener("mouseout", (e) => {
  if (e.target.closest && e.target.closest(".term")) tooltip.hidden = true;
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest(".quiz-choice");
  if (!btn) return;

  const qid = btn.dataset.qid;
  const index = Number(btn.dataset.index);
  selectedAnswers[qid] = index;

  const item = btn.closest(".quiz-item");
  item.querySelectorAll(".quiz-choice").forEach((choice) => {
    choice.classList.toggle("active", choice === btn);
  });

  quizSubmitBtn.disabled = currentQuiz.every((q) => selectedAnswers[q.id] !== undefined);
});

quizSubmitBtn.addEventListener("click", () => {
  let correct = 0;
  for (const q of currentQuiz) {
    const item = quizList.querySelector(`.quiz-item[data-qid="${q.id}"]`);
    const user = selectedAnswers[q.id];
    const hint = item.querySelector(`.quiz-feedback[data-qid="${q.id}"]`);

    item.querySelectorAll(".quiz-choice").forEach((choice) => {
      const idx = Number(choice.dataset.index);
      choice.classList.toggle("correct", idx === q.answer);
      choice.classList.toggle("wrong", user !== undefined && idx === user && idx !== q.answer);
      choice.disabled = true;
    });

    if (user === q.answer) {
      correct += 1;
      hint.textContent = "정답이에요." + (q.explanation ? ` ${q.explanation}` : "");
      hint.className = "quiz-feedback is-correct";
      hint.hidden = false;
    } else {
      const expected = q.options[q.answer];
      if (user === undefined) {
        hint.textContent = `미응답: 정답은 "${expected}" 입니다.`;
      } else {
        hint.textContent = `틀렸어요. 정답은 "${expected}" 입니다.`;
      }
      hint.className = "quiz-feedback is-wrong";
      hint.hidden = false;
      if (q.explanation) {
        hint.innerHTML += `<br><span class="quiz-explain">${q.explanation}</span>`;
      }
    }
  }

  const score = currentQuiz.length ? Math.round((correct / currentQuiz.length) * 100) : 0;
  quizResult.textContent = `점수: ${correct}/${currentQuiz.length} 정답 (${score}점)`;
  quizResult.hidden = false;
  quizSubmitBtn.disabled = true;
});

// ---------------------------------------------------------------------------
// 종목명/코드 클릭 → 차트 모달
// ---------------------------------------------------------------------------
document.addEventListener("click", (e) => {
  const ticker = e.target.closest(".ticker");
  if (ticker) openChart(ticker.dataset.code);
});

const modal = $("#chart-modal");
const chartCanvas = $("#chart-canvas");
const chartState = { code: null, range: "3m", candles: [], hoverIndex: -1 };

$("#chart-close").addEventListener("click", closeChart);
modal.addEventListener("click", (e) => { if (e.target === modal) closeChart(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !modal.hidden) closeChart();
});

$("#range-buttons").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-range]");
  if (!btn || !chartState.code) return;
  document.querySelectorAll("#range-buttons button").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  chartState.range = btn.dataset.range;
  loadChart(chartState.code, chartState.range);
});

async function openChart(code) {
  modal.hidden = false;
  chartState.code = code;
  document.querySelectorAll("#range-buttons button").forEach((b) => {
    b.classList.toggle("active", b.dataset.range === chartState.range);
  });

  try {
    const q = await getQuote(code);
    $("#chart-name").textContent = q.name;
    $("#chart-code").textContent = `${q.code} · ${q.market}`;
    $("#chart-sector").textContent = q.sector;
    $("#chart-price").textContent = fmtPrice(q.price);
    $("#chart-price").className = changeClass(q.change);
    $("#chart-change").textContent =
      `${changeSign(q.change)} ${fmtPrice(Math.abs(q.change))} (${Math.abs(q.change_pct)}%)`;
    $("#chart-change").className = changeClass(q.change);
  } catch (_) { /* 헤더 없이도 차트는 시도 */ }

  loadChart(code, chartState.range);
}

function closeChart() {
  modal.hidden = true;
  chartState.code = null;
}

async function loadChart(code, range) {
  $("#chart-loading").hidden = false;
  try {
    const data = await fetchJSON(API_BASE_URL + `/api/stocks/${code}/chart?range=${range}`);
    if (chartState.code !== code) return;
    chartState.candles = data.candles;
    chartState.hoverIndex = -1;
    $("#chart-source").textContent =
      data.source === "live" ? "데이터: Yahoo Finance (지연 시세)" : "데이터: 데모용 모의 시세";
    drawChart();
  } catch (err) {
    $("#chart-source").textContent = `차트를 불러오지 못했어요: ${err.message}`;
  } finally {
    $("#chart-loading").hidden = true;
  }
}

chartCanvas.addEventListener("mousemove", (e) => {
  if (!chartState.candles.length) return;
  const rect = chartCanvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const L = chartLayout(rect.width, rect.height);
  const idx = Math.round((x - L.left) / L.step);
  const clamped = Math.max(0, Math.min(chartState.candles.length - 1, idx));
  if (clamped !== chartState.hoverIndex) {
    chartState.hoverIndex = clamped;
    drawChart();
  }
});
chartCanvas.addEventListener("mouseleave", () => {
  chartState.hoverIndex = -1;
  drawChart();
});

function chartLayout(w, h) {
  const left = 10, right = 64, top = 16, volH = h * 0.18, gap = 24;
  const priceH = h - top - volH - gap - 8;
  const n = chartState.candles.length;
  const step = (w - left - right) / Math.max(1, n - 1);
  return { left, right, top, volH, gap, priceH, step, w, h };
}

function drawChart() {
  const candles = chartState.candles;
  if (!candles.length) return;

  const cssW = chartCanvas.clientWidth;
  const cssH = chartCanvas.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  chartCanvas.width = cssW * dpr;
  chartCanvas.height = cssH * dpr;
  const ctx = chartCanvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, cssW, cssH);

  const L = chartLayout(cssW, cssH);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  let min = Math.min(...lows), max = Math.max(...highs);
  const pad = (max - min) * 0.06 || max * 0.01;
  min -= pad; max += pad;
  const maxVol = Math.max(...candles.map((c) => c.volume)) || 1;

  const px = (i) => L.left + i * L.step;
  const py = (v) => L.top + (1 - (v - min) / (max - min)) * L.priceH;

  // 가격 눈금선 + 라벨
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "#9ca3af";
  ctx.strokeStyle = "#f3f4f6";
  ctx.lineWidth = 1;
  const gridN = 4;
  for (let g = 0; g <= gridN; g++) {
    const v = min + ((max - min) * g) / gridN;
    const y = py(v);
    ctx.beginPath();
    ctx.moveTo(L.left, y);
    ctx.lineTo(cssW - L.right + 8, y);
    ctx.stroke();
    ctx.fillText(fmtPrice(Math.round(v)), cssW - L.right + 12, y + 4);
  }

  // 캔들 (상승=빨강, 하락=파랑)
  const candleW = Math.max(1, Math.min(12, L.step * 0.62));
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const x = px(i);
    const up = c.close >= c.open;
    const color = up ? "#d93025" : "#1a73e8";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    // 심지
    ctx.beginPath();
    ctx.moveTo(x, py(c.high));
    ctx.lineTo(x, py(c.low));
    ctx.stroke();
    // 몸통
    const yO = py(c.open), yC = py(c.close);
    const bodyTop = Math.min(yO, yC);
    const bodyH = Math.max(1, Math.abs(yO - yC));
    ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyH);
  }

  // 거래량
  const volTop = L.top + L.priceH + L.gap;
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const up = c.close >= c.open;
    ctx.fillStyle = up ? "rgba(217,48,37,0.35)" : "rgba(26,115,232,0.35)";
    const vh = (c.volume / maxVol) * L.volH;
    ctx.fillRect(px(i) - candleW / 2, volTop + L.volH - vh, candleW, vh);
  }

  // 날짜 라벨
  ctx.fillStyle = "#9ca3af";
  const labelEvery = Math.ceil(candles.length / 6);
  for (let i = 0; i < candles.length; i += labelEvery) {
    ctx.fillText(candles[i].date.slice(5), px(i) - 14, cssH - 2);
  }

  // 크로스헤어 + 정보
  const hi = chartState.hoverIndex;
  if (hi >= 0 && hi < candles.length) {
    const c = candles[hi];
    const x = px(hi);
    ctx.strokeStyle = "#9ca3af";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(x, L.top);
    ctx.lineTo(x, volTop + L.volH);
    ctx.stroke();
    ctx.setLineDash([]);

    const info = `${c.date}  시 ${fmtPrice(c.open)}  고 ${fmtPrice(c.high)}  저 ${fmtPrice(c.low)}  종 ${fmtPrice(c.close)}  량 ${fmtPrice(c.volume)}`;
    ctx.font = "12px sans-serif";
    const tw = ctx.measureText(info).width + 16;
    const bx = Math.min(Math.max(8, x - tw / 2), cssW - tw - 8);
    ctx.fillStyle = "rgba(31,41,55,0.92)";
    roundRect(ctx, bx, 0, tw, 22, 6);
    ctx.fill();
    ctx.fillStyle = "#f9fafb";
    ctx.fillText(info, bx + 8, 15);
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

window.addEventListener("resize", () => {
  if (!modal.hidden && chartState.candles.length) drawChart();
});
