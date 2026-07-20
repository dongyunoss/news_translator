// 주린이 뉴스 번역기 — 기사 페이지 위에서 바로 동작하는 콘텐츠 스크립트.
// 우하단 플로팅 버튼 → 페이지 안 패널에 쉬운 번역을 띄우고,
// 문장 호버 → 관련 종목 시세, 종목 클릭 → 캔들 차트까지 페이지 위에서 처리한다.
"use strict";

// ---------------------------------------------------------------------------
// 팝업(popup.js)과의 메시지: 기사 추출 요청
// ---------------------------------------------------------------------------
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractText') {
    sendResponse({ text: extractArticleText() });
  }
});

// ---------------------------------------------------------------------------
// 기사 텍스트 추출 (사이트별)
// ---------------------------------------------------------------------------
function extractArticleText() {
  const hostname = window.location.hostname;
  if (hostname.includes('naver.com')) return extractBySelectors(
    ['h2.media_end_head_headline', 'h1#title_area'], ['#dic_area', '.newsct_article']);
  if (hostname.includes('hankyung.com')) return extractBySelectors(
    ['h1.title', 'h1.headline'], ['.article-body', '#articletxt']);
  if (hostname.includes('mk.co.kr')) return extractBySelectors(
    ['h2.news_ttl', 'h2.news_title', 'h1'], ['.news_cnt_detail_wrap', '#content', '.article_content']);
  if (hostname.includes('edaily.co.kr')) return extractBySelectors(
    ['h1.article_title', 'h2.news_titles'], ['.news_body', '#article_content']);
  if (hostname.includes('fnnews.com')) return extractBySelectors(
    ['h1.tit_thumb', 'h1'], ['#article_content', '.cont_art']);
  return extractGeneric();
}

function extractBySelectors(titleSels, bodySels) {
  let title = '';
  for (const sel of titleSels) {
    const el = document.querySelector(sel);
    if (el && el.textContent.trim().length > 5) {
      title = el.textContent.trim();
      break;
    }
  }
  let body = '';
  for (const sel of bodySels) {
    const el = document.querySelector(sel);
    if (el && el.textContent.trim().length > 100) {
      body = cleanText(el.textContent);
      break;
    }
  }
  // 본문을 못 찾으면 사이트 공통 추출로 폴백 (제목만 갖고 끝내지 않는다)
  if (!body) return extractGeneric();
  return (title ? title + '\n\n' : '') + body;
}

function extractGeneric() {
  let text = '';
  for (const sel of ['h1', 'h2.title', 'h1.headline', 'h1.article-title']) {
    const el = document.querySelector(sel);
    if (el && el.textContent.trim().length > 10) {
      text += el.textContent.trim() + '\n\n';
      break;
    }
  }
  for (const sel of ['article', '.article-body', '.article_content', '#article-content', '.news-body', '[role="main"]']) {
    const el = document.querySelector(sel);
    if (el && el.textContent.trim().length > 200) {
      text += cleanText(el.textContent);
      break;
    }
  }
  if (text.trim().length < 50) text = cleanText(document.body.innerText);
  return text.trim();
}

function cleanText(raw) {
  return raw
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.length > 0)
    .join('\n')
    .replace(/\n{2,}/g, '\n');
}

// ---------------------------------------------------------------------------
// 백그라운드 경유 API 호출 (뉴스 사이트 CORS 우회)
// ---------------------------------------------------------------------------
function api(path, method, body) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: 'api', path, method, body }, (res) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (!res || !res.ok) return reject(new Error((res && res.error) || '요청에 실패했어요.'));
      resolve(res.data);
    });
  });
}

// ---------------------------------------------------------------------------
// 공통 유틸
// ---------------------------------------------------------------------------
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
function fmtPrice(n) { return Number(n).toLocaleString('ko-KR'); }
function changeClass(v) { return v > 0 ? 'up' : v < 0 ? 'down' : 'flat'; }
function changeSign(v) { return v > 0 ? '▲' : v < 0 ? '▼' : '―'; }

// ---------------------------------------------------------------------------
// UI 뼈대 — Shadow DOM으로 사이트 스타일과 완전히 격리
// ---------------------------------------------------------------------------
const CSS = `
:host { all: initial; }
* { box-sizing: border-box; font-family: "Pretendard","Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif; }
[hidden] { display: none !important; }

.fab {
  position: fixed; right: 22px; bottom: 26px; z-index: 2147483600;
  display: flex; align-items: center; gap: 7px;
  background: #2563eb; color: #fff; border: none; border-radius: 999px;
  padding: 12px 18px; font-size: 14px; font-weight: 700; cursor: pointer;
  box-shadow: 0 8px 24px rgba(37,99,235,.4); line-height: 1;
}
.fab:hover { background: #1d4ed8; }
.fab .spin {
  width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.4);
  border-top-color: #fff; border-radius: 50%; animation: jnspin .8s linear infinite;
}
@keyframes jnspin { to { transform: rotate(360deg); } }

.panel {
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 2147483610;
  width: min(430px, 96vw); background: #f5f6f8; color: #1c1e21;
  box-shadow: -12px 0 32px rgba(0,0,0,.18);
  display: flex; flex-direction: column; font-size: 14px; line-height: 1.6;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 13px 16px; background: #fff; border-bottom: 1px solid #e5e7eb;
}
.panel-header .title { font-size: 15px; font-weight: 700; }
.panel-header .close {
  background: none; border: none; font-size: 16px; color: #6b7280; cursor: pointer; padding: 4px 8px;
}
.panel-header .close:hover { color: #1c1e21; }
.panel-body { overflow-y: auto; padding: 14px; flex: 1; }

.notice {
  background: #fffbeb; border: 1px solid #fde68a; color: #92400e;
  border-radius: 10px; padding: 10px 12px; font-size: 12.5px; margin-bottom: 10px;
}
.summary {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
  padding: 12px 14px; margin-bottom: 10px;
}
.summary h3 { margin: 0 0 6px; font-size: 13.5px; }
.summary p { margin: 0; font-size: 13.5px; }
.hint { color: #6b7280; font-size: 12px; margin: 0 2px 10px; }

.sentence-block {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
  padding: 11px 13px; margin-bottom: 9px; transition: border-color .15s, box-shadow .15s;
}
.sentence-block:hover { border-color: #2563eb; box-shadow: 0 4px 14px rgba(37,99,235,.12); }
.sentence-original { color: #6b7280; font-size: 12px; margin-bottom: 7px; }
.sentence-easy {
  background: #eff6ff; border-radius: 9px; padding: 8px 11px; font-size: 13.5px;
}
.sentence-easy::before { content: "🐣 "; }
.related-badge {
  display: inline-block; margin-top: 8px; font-size: 11px; color: #6b7280;
  background: #f3f4f6; border-radius: 999px; padding: 2px 9px;
}

.ticker { color: #2563eb; font-weight: 600; cursor: pointer; border-bottom: 1.5px solid rgba(37,99,235,.35); }
.ticker:hover { background: #dbeafe; }
.term { border-bottom: 1.5px dotted #b45309; color: #b45309; cursor: help; }

.error-card {
  background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c;
  border-radius: 10px; padding: 11px 13px; font-size: 13px;
}

.popover {
  position: fixed; z-index: 2147483630; width: 300px;
  background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0,0,0,.15); padding: 8px;
}
.popover-title { font-size: 11.5px; font-weight: 700; color: #6b7280; padding: 2px 6px 7px; }
.popover-loading, .popover-empty { padding: 8px; color: #6b7280; font-size: 12.5px; }
.stock-row {
  display: grid; grid-template-columns: 1fr auto auto; align-items: center;
  gap: 9px; padding: 6px 7px; border-radius: 8px; cursor: pointer;
}
.stock-row:hover { background: #eff6ff; }
.stock-row .name { font-weight: 600; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stock-row .reason { font-size: 10.5px; color: #6b7280; }
.stock-row .quote { text-align: right; font-size: 12.5px; white-space: nowrap; }
.stock-row .quote .pct { display: block; font-size: 11.5px; }
.up { color: #d93025; } .down { color: #1a73e8; } .flat { color: #6b7280; }

.tooltip {
  position: fixed; z-index: 2147483640; max-width: 290px;
  background: #1f2937; color: #f9fafb; border-radius: 10px;
  padding: 9px 13px; font-size: 12.5px; box-shadow: 0 8px 24px rgba(0,0,0,.25);
  pointer-events: none; line-height: 1.5;
}
.tooltip .tt-term { font-weight: 700; color: #fbbf24; }
.tooltip .tt-easy { display: block; margin-top: 1px; }
.tooltip .tt-desc { display: block; margin-top: 5px; color: #d1d5db; font-size: 11.5px; }

.modal-backdrop {
  position: fixed; inset: 0; z-index: 2147483650;
  background: rgba(15,23,42,.55); display: flex; align-items: center; justify-content: center; padding: 16px;
}
.modal {
  background: #fff; color: #1c1e21; border-radius: 16px;
  width: min(760px, 100%); padding: 18px 20px; box-shadow: 0 8px 24px rgba(0,0,0,.3);
}
.modal-header { display: flex; justify-content: space-between; align-items: flex-start; }
.modal-title { display: flex; align-items: center; gap: 8px; font-size: 18px; font-weight: 700; flex-wrap: wrap; }
.code-chip, .sector-chip { font-size: 11.5px; font-weight: 500; border-radius: 999px; padding: 2px 9px; }
.code-chip { background: #f3f4f6; color: #6b7280; }
.sector-chip { background: #eff6ff; color: #2563eb; }
.modal-quote { margin-top: 3px; font-size: 14px; display: flex; gap: 9px; align-items: baseline; }
.modal-quote .price { font-size: 21px; font-weight: 700; }
.close-btn { background: none; border: none; font-size: 17px; cursor: pointer; color: #6b7280; padding: 4px 8px; }
.close-btn:hover { color: #1c1e21; }
.range-buttons { display: flex; gap: 6px; margin: 12px 0 9px; }
.range-buttons button {
  border: 1px solid #e5e7eb; background: #fff; border-radius: 8px;
  padding: 4px 13px; font-size: 12.5px; cursor: pointer; color: #1c1e21;
}
.range-buttons button.active { background: #2563eb; color: #fff; border-color: #2563eb; }
.chart-wrap { position: relative; }
canvas.chart { width: 100%; height: 330px; display: block; }
.chart-loading {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: #6b7280; background: rgba(255,255,255,.7); font-size: 13px;
}
.chart-source { margin: 7px 0 0; font-size: 11.5px; color: #6b7280; text-align: right; }
`;

const host = document.createElement('div');
host.style.all = 'initial';
document.documentElement.appendChild(host);
const root = host.attachShadow({ mode: 'open' });

root.innerHTML = `
  <style>${CSS}</style>
  <button class="fab" id="fab"><span>📰</span><span id="fab-label">쉬운말 번역</span></button>
  <div class="panel" id="panel" hidden>
    <div class="panel-header">
      <span class="title">📰 주린이 번역</span>
      <button class="close" id="panel-close" aria-label="닫기">✕</button>
    </div>
    <div class="panel-body" id="panel-body"></div>
  </div>
  <div class="popover" id="popover" hidden></div>
  <div class="tooltip" id="tooltip" hidden></div>
  <div class="modal-backdrop" id="modal" hidden>
    <div class="modal">
      <div class="modal-header">
        <div>
          <div class="modal-title">
            <span id="chart-name"></span>
            <span id="chart-code" class="code-chip"></span>
            <span id="chart-sector" class="sector-chip"></span>
          </div>
          <div class="modal-quote">
            <span id="chart-price" class="price"></span>
            <span id="chart-change"></span>
          </div>
        </div>
        <button id="chart-close" class="close-btn" aria-label="닫기">✕</button>
      </div>
      <div class="range-buttons" id="range-buttons">
        <button data-range="1m">1개월</button>
        <button data-range="3m" class="active">3개월</button>
        <button data-range="6m">6개월</button>
        <button data-range="1y">1년</button>
      </div>
      <div class="chart-wrap">
        <canvas class="chart" id="chart-canvas"></canvas>
        <div id="chart-loading" class="chart-loading" hidden>불러오는 중…</div>
      </div>
      <p class="chart-source" id="chart-source"></p>
    </div>
  </div>
`;

const $ = (sel) => root.querySelector(sel);
const fab = $('#fab');
const fabLabel = $('#fab-label');
const panel = $('#panel');
const panelBody = $('#panel-body');
const popover = $('#popover');
const tooltip = $('#tooltip');
const modal = $('#modal');
const chartCanvas = $('#chart-canvas');

// ---------------------------------------------------------------------------
// 플로팅 버튼 → 번역 실행/패널 토글
// ---------------------------------------------------------------------------
let translated = false;
let translating = false;

fab.addEventListener('click', async () => {
  if (translating) return;
  if (translated) {
    panel.hidden = !panel.hidden;
    return;
  }
  const text = extractArticleText();
  if (!text || text.length < 30) {
    panel.hidden = false;
    panelBody.innerHTML = `<div class="error-card">이 페이지에서 기사를 찾지 못했어요. 기사 본문 페이지에서 다시 시도해 주세요.</div>`;
    return;
  }

  translating = true;
  fabLabel.innerHTML = `<span class="spin"></span>`;
  fab.querySelector('span').textContent = '번역 중…';
  panel.hidden = false;
  panelBody.innerHTML = `<div class="hint">기사를 쉬운 말로 바꾸는 중이에요… (문장 수에 따라 몇 초 걸려요)</div>`;

  try {
    const data = await api('/api/translate', 'POST', { text });
    renderResult(data);
    translated = true;
    fab.querySelector('span').textContent = '📰';
    fabLabel.textContent = '번역 결과 보기';
  } catch (err) {
    panelBody.innerHTML =
      `<div class="error-card">번역에 실패했어요: ${escapeHtml(err.message)}<br><br>` +
      `확장 아이콘(📰) 팝업의 ⚙️ 설정에서 API 주소를 확인해 주세요.</div>`;
    fab.querySelector('span').textContent = '📰';
    fabLabel.textContent = '다시 시도';
  } finally {
    translating = false;
  }
});

$('#panel-close').addEventListener('click', () => { panel.hidden = true; hidePopoverNow(); });

// ---------------------------------------------------------------------------
// 결과 렌더링
// ---------------------------------------------------------------------------
function decorateText(text, mentions, terms) {
  const pats = [];
  for (const m of mentions) pats.push({ t: m.text, type: 'ticker', data: m });
  for (const t of terms) pats.push({ t: t.term, type: 'term', data: t });
  pats.sort((a, b) => b.t.length - a.t.length);
  if (!pats.length) return escapeHtml(text);

  const re = new RegExp(pats.map((p) => escapeRegex(p.t)).join('|'), 'g');
  let out = '', last = 0;
  for (const m of text.matchAll(re)) {
    out += escapeHtml(text.slice(last, m.index));
    const p = pats.find((p) => p.t === m[0]);
    if (p.type === 'ticker') {
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
  let html = '';
  if (data.notice) html += `<div class="notice">${escapeHtml(data.notice)}</div>`;
  if (data.summary) html += `<div class="summary"><h3>📌 세 줄 요약</h3><p>${escapeHtml(data.summary)}</p></div>`;
  html += `<div class="hint">💡 문장에 마우스를 올리면 관련 종목이, <span class="ticker">파란 종목명</span>을 클릭하면 차트가 떠요.</div>`;
  panelBody.innerHTML = html;

  for (const s of data.sentences) {
    const block = document.createElement('div');
    block.className = 'sentence-block';
    block._related = s.related || [];
    let inner = `<div class="sentence-original">${decorateText(s.original, s.mentions, s.terms)}</div>`;
    inner += `<div class="sentence-easy">${decorateText(s.easy, s.mentions, [])}</div>`;
    if (block._related.length) {
      inner += `<span class="related-badge">📈 관련 종목 ${block._related.length}개 — 마우스를 올려보세요</span>`;
    }
    block.innerHTML = inner;
    block.addEventListener('mouseenter', () => schedulePopover(block));
    block.addEventListener('mouseleave', scheduleHidePopover);
    panelBody.appendChild(block);
  }
}

// ---------------------------------------------------------------------------
// 관련 종목 팝오버
// ---------------------------------------------------------------------------
let popShowTimer = null, popHideTimer = null, popToken = 0;
const quoteCache = new Map();

function getQuote(code) {
  if (!quoteCache.has(code)) {
    quoteCache.set(code, api(`/api/stocks/${code}`).catch((e) => {
      quoteCache.delete(code);
      throw e;
    }));
  }
  return quoteCache.get(code);
}

popover.addEventListener('mouseenter', () => clearTimeout(popHideTimer));
popover.addEventListener('mouseleave', scheduleHidePopover);

function schedulePopover(block) {
  clearTimeout(popShowTimer);
  clearTimeout(popHideTimer);
  if (!block._related.length) return;
  popShowTimer = setTimeout(() => showPopover(block), 200);
}
function scheduleHidePopover() {
  clearTimeout(popShowTimer);
  clearTimeout(popHideTimer);
  popHideTimer = setTimeout(hidePopoverNow, 250);
}
function hidePopoverNow() { popover.hidden = true; }

async function showPopover(block) {
  const token = ++popToken;
  popover.innerHTML =
    `<div class="popover-title">📈 이 문장과 관련된 종목</div>` +
    `<div class="popover-loading">시세를 불러오는 중…</div>`;
  popover.hidden = false;
  positionPopover(block);

  const quotes = await Promise.all(block._related.map((r) =>
    getQuote(r.code).then((q) => ({ ...q, reason: r.reason })).catch(() => null)
  ));
  if (token !== popToken || popover.hidden) return;

  const rows = quotes.filter(Boolean);
  if (!rows.length) {
    popover.innerHTML = `<div class="popover-empty">시세를 불러오지 못했어요.</div>`;
    return;
  }

  popover.innerHTML =
    `<div class="popover-title">📈 관련 종목 — 누르면 차트가 열려요</div>` +
    rows.map((q) => `
      <div class="stock-row" data-code="${q.code}">
        <div>
          <div class="name">${escapeHtml(q.name)}</div>
          <div class="reason">${escapeHtml(q.reason)} · ${q.code}</div>
        </div>
        <canvas class="spark" width="60" height="24" data-spark="${q.spark.join(',')}" data-dir="${changeClass(q.change)}"></canvas>
        <div class="quote ${changeClass(q.change)}">
          ${fmtPrice(q.price)}
          <span class="pct">${changeSign(q.change)} ${Math.abs(q.change_pct)}%</span>
        </div>
      </div>`).join('');

  popover.querySelectorAll('canvas.spark').forEach(drawSparkline);
  popover.querySelectorAll('.stock-row').forEach((row) => {
    row.addEventListener('click', () => {
      hidePopoverNow();
      openChart(row.dataset.code);
    });
  });
  positionPopover(block);
}

function positionPopover(block) {
  const rect = block.getBoundingClientRect();
  const popW = popover.offsetWidth || 300;
  const popH = popover.offsetHeight || 180;
  let left = Math.min(rect.left, window.innerWidth - popW - 10);
  left = Math.max(8, left - popW * 0.2);
  let top = rect.bottom + 6;
  if (top + popH + 10 > window.innerHeight) top = rect.top - popH - 6;
  popover.style.left = `${left}px`;
  popover.style.top = `${Math.max(8, top)}px`;
}

function drawSparkline(canvas) {
  const values = canvas.dataset.spark.split(',').map(Number);
  const dir = canvas.dataset.dir;
  const dpr = window.devicePixelRatio || 1;
  const w = 60, h = 24;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  ctx.beginPath();
  values.forEach((v, i) => {
    const x = (i / (values.length - 1)) * (w - 2) + 1;
    const y = h - 3 - ((v - min) / span) * (h - 6);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = dir === 'up' ? '#d93025' : dir === 'down' ? '#1a73e8' : '#9ca3af';
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

// ---------------------------------------------------------------------------
// 용어 툴팁 / 티커 클릭 (패널 내부 이벤트 위임)
// ---------------------------------------------------------------------------
panelBody.addEventListener('mouseover', (e) => {
  const term = e.target.closest && e.target.closest('.term');
  if (!term) return;
  tooltip.innerHTML =
    `<span class="tt-term">${escapeHtml(term.dataset.term)}</span>` +
    `<span class="tt-easy">= ${escapeHtml(term.dataset.easy)}</span>` +
    `<span class="tt-desc">${escapeHtml(term.dataset.desc)}</span>`;
  tooltip.hidden = false;
  const rect = term.getBoundingClientRect();
  const ttW = tooltip.offsetWidth;
  let left = Math.min(rect.left, window.innerWidth - ttW - 8);
  tooltip.style.left = `${Math.max(8, left)}px`;
  tooltip.style.top = `${rect.bottom + 6}px`;
});
panelBody.addEventListener('mouseout', (e) => {
  if (e.target.closest && e.target.closest('.term')) tooltip.hidden = true;
});
panelBody.addEventListener('click', (e) => {
  const ticker = e.target.closest && e.target.closest('.ticker');
  if (ticker && ticker.dataset.code) openChart(ticker.dataset.code);
});

// ---------------------------------------------------------------------------
// 차트 모달
// ---------------------------------------------------------------------------
const chartState = { code: null, range: '3m', candles: [], hoverIndex: -1 };

$('#chart-close').addEventListener('click', closeChart);
modal.addEventListener('click', (e) => { if (e.target === modal) closeChart(); });
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !modal.hidden) closeChart();
});

$('#range-buttons').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-range]');
  if (!btn || !chartState.code) return;
  root.querySelectorAll('#range-buttons button').forEach((b) => b.classList.remove('active'));
  btn.classList.add('active');
  chartState.range = btn.dataset.range;
  loadChart(chartState.code, chartState.range);
});

async function openChart(code) {
  modal.hidden = false;
  chartState.code = code;
  root.querySelectorAll('#range-buttons button').forEach((b) => {
    b.classList.toggle('active', b.dataset.range === chartState.range);
  });
  try {
    const q = await getQuote(code);
    $('#chart-name').textContent = q.name;
    $('#chart-code').textContent = `${q.code} · ${q.market}`;
    $('#chart-sector').textContent = q.sector;
    $('#chart-price').textContent = fmtPrice(q.price);
    $('#chart-price').className = `price ${changeClass(q.change)}`;
    $('#chart-change').textContent =
      `${changeSign(q.change)} ${fmtPrice(Math.abs(q.change))} (${Math.abs(q.change_pct)}%)`;
    $('#chart-change').className = changeClass(q.change);
  } catch (_) { /* 헤더 없이도 차트는 시도 */ }
  loadChart(code, chartState.range);
}

function closeChart() {
  modal.hidden = true;
  chartState.code = null;
}

async function loadChart(code, range) {
  $('#chart-loading').hidden = false;
  try {
    const data = await api(`/api/stocks/${code}/chart?range=${range}`);
    if (chartState.code !== code) return;
    chartState.candles = data.candles;
    chartState.hoverIndex = -1;
    $('#chart-source').textContent =
      data.source === 'live' ? '데이터: Yahoo Finance (지연 시세)' : '데이터: 데모용 모의 시세';
    drawChart();
  } catch (err) {
    $('#chart-source').textContent = `차트를 불러오지 못했어요: ${err.message}`;
  } finally {
    $('#chart-loading').hidden = true;
  }
}

chartCanvas.addEventListener('mousemove', (e) => {
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
chartCanvas.addEventListener('mouseleave', () => {
  chartState.hoverIndex = -1;
  drawChart();
});

function chartLayout(w, h) {
  const left = 10, right = 62, top = 16, volH = h * 0.18, gap = 22;
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
  const ctx = chartCanvas.getContext('2d');
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

  ctx.font = '11px sans-serif';
  ctx.fillStyle = '#9ca3af';
  ctx.strokeStyle = '#f3f4f6';
  ctx.lineWidth = 1;
  for (let g = 0; g <= 4; g++) {
    const v = min + ((max - min) * g) / 4;
    const y = py(v);
    ctx.beginPath();
    ctx.moveTo(L.left, y);
    ctx.lineTo(cssW - L.right + 8, y);
    ctx.stroke();
    ctx.fillText(fmtPrice(Math.round(v)), cssW - L.right + 12, y + 4);
  }

  const candleW = Math.max(1, Math.min(12, L.step * 0.62));
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const x = px(i);
    const color = c.close >= c.open ? '#d93025' : '#1a73e8';
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x, py(c.high));
    ctx.lineTo(x, py(c.low));
    ctx.stroke();
    const yO = py(c.open), yC = py(c.close);
    ctx.fillRect(x - candleW / 2, Math.min(yO, yC), candleW, Math.max(1, Math.abs(yO - yC)));
  }

  const volTop = L.top + L.priceH + L.gap;
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    ctx.fillStyle = c.close >= c.open ? 'rgba(217,48,37,.35)' : 'rgba(26,115,232,.35)';
    const vh = (c.volume / maxVol) * L.volH;
    ctx.fillRect(px(i) - candleW / 2, volTop + L.volH - vh, candleW, vh);
  }

  ctx.fillStyle = '#9ca3af';
  const labelEvery = Math.ceil(candles.length / 6);
  for (let i = 0; i < candles.length; i += labelEvery) {
    ctx.fillText(candles[i].date.slice(5), px(i) - 14, cssH - 2);
  }

  const hi = chartState.hoverIndex;
  if (hi >= 0 && hi < candles.length) {
    const c = candles[hi];
    const x = px(hi);
    ctx.strokeStyle = '#9ca3af';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(x, L.top);
    ctx.lineTo(x, volTop + L.volH);
    ctx.stroke();
    ctx.setLineDash([]);

    const info = `${c.date}  시 ${fmtPrice(c.open)}  고 ${fmtPrice(c.high)}  저 ${fmtPrice(c.low)}  종 ${fmtPrice(c.close)}  량 ${fmtPrice(c.volume)}`;
    ctx.font = '12px sans-serif';
    const tw = ctx.measureText(info).width + 16;
    const bx = Math.min(Math.max(8, x - tw / 2), cssW - tw - 8);
    ctx.fillStyle = 'rgba(31,41,55,.92)';
    roundRect(ctx, bx, 0, tw, 22, 6);
    ctx.fill();
    ctx.fillStyle = '#f9fafb';
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

window.addEventListener('resize', () => {
  if (!modal.hidden && chartState.candles.length) drawChart();
});
