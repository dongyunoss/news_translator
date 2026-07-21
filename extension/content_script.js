// 주린이 뉴스 번역기 — 기사 페이지 위에서 바로 동작하는 콘텐츠 스크립트.
// 번역하면 기사 원문 문장에 하이라이트가 생기고,
//   문장 호버  → 쉬운 번역 + 관련 종목 카드 (문장 바로 옆)
//   종목명 클릭 → 캔들 차트 모달
//   용어 호버  → 뜻 툴팁
// 화면 우측에는 요약·관련 종목 시세·용어 사전이 담긴 사이드바가 뜬다.
"use strict";

// ---------------------------------------------------------------------------
// 팝업(popup.js)과의 메시지: 기사 추출 요청
// ---------------------------------------------------------------------------
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractText') {
    sendResponse({ text: extractArticle().text });
  }
});

// ---------------------------------------------------------------------------
// 기사 텍스트 추출 (사이트별 → 공통 폴백)
// 하이라이트를 달 본문 컨테이너도 함께 돌려준다.
// ---------------------------------------------------------------------------
const SITE_RULES = [
  { host: 'naver.com',    title: ['h2.media_end_head_headline', 'h1#title_area'], body: ['#dic_area', '.newsct_article'] },
  { host: 'hankyung.com', title: ['h1.title', 'h1.headline'],                     body: ['.article-body', '#articletxt'] },
  { host: 'mk.co.kr',     title: ['h2.news_ttl', 'h2.news_title', 'h1'],          body: ['.news_cnt_detail_wrap', '#content', '.article_content'] },
  { host: 'edaily.co.kr', title: ['h1.article_title', 'h2.news_titles'],          body: ['.news_body', '#article_content'] },
  { host: 'fnnews.com',   title: ['h1.tit_thumb', 'h1'],                          body: ['#article_content', '.cont_art'] },
];
const GENERIC_BODY_SELECTORS = [
  'article', '.article-body', '.article_content', '#article-content',
  '.news-body', '.news_body', '#newsct_article', '[itemprop="articleBody"]', '[role="main"]',
];

function extractArticle() {
  const hostname = window.location.hostname;
  const rule = SITE_RULES.find((r) => hostname.includes(r.host));

  let title = '';
  let container = null;
  const titleSels = rule ? rule.title : ['h1', 'h2.title', 'h1.headline', 'h1.article-title'];
  for (const sel of titleSels) {
    const el = document.querySelector(sel);
    if (el && el.textContent.trim().length > 5) { title = el.textContent.trim(); break; }
  }
  const bodySels = (rule ? rule.body : []).concat(GENERIC_BODY_SELECTORS);
  for (const sel of bodySels) {
    const el = document.querySelector(sel);
    if (el && el.textContent.trim().length > 100) { container = el; break; }
  }

  let body = container ? cleanText(container.textContent) : '';
  if (body.length < 50) {
    container = document.body;
    body = cleanText(document.body.innerText);
  }
  const text = ((title ? title + '\n\n' : '') + body).trim();
  return { text, container: container || document.body };
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
// 페이지에 심는 스타일 (하이라이트는 기사 DOM에 직접 달리므로 일반 CSS 필요)
// ---------------------------------------------------------------------------
const pageStyle = document.createElement('style');
pageStyle.id = 'jn-page-style';
pageStyle.textContent = `
.jn-hl {
  background: rgba(37,99,235,.09) !important;
  border-bottom: 2px solid rgba(37,99,235,.45) !important;
  cursor: pointer !important;
  border-radius: 2px;
  transition: background .15s;
}
.jn-hl:hover, .jn-hl.jn-active { background: rgba(37,99,235,.20) !important; }
/* 특히 어려운 문장은 주황색으로 구분 */
.jn-hl.jn-hard {
  background: rgba(234,88,12,.12) !important;
  border-bottom-color: rgba(234,88,12,.55) !important;
}
.jn-hl.jn-hard:hover, .jn-hl.jn-hard.jn-active { background: rgba(234,88,12,.24) !important; }
.jn-ticker {
  color: #2563eb !important; font-weight: 700 !important; cursor: pointer !important;
  border-bottom: 2px solid rgba(37,99,235,.6) !important;
}
.jn-ticker:hover { background: rgba(37,99,235,.15) !important; }
.jn-term {
  border-bottom: 2px dotted #b45309 !important; cursor: help !important;
}
.jn-flash { animation: jnflash 1.2s ease; }
@keyframes jnflash {
  0%, 60% { background: rgba(250,204,21,.55); }
  100% { background: rgba(37,99,235,.09); }
}
`;
document.documentElement.appendChild(pageStyle);

// ---------------------------------------------------------------------------
// 확장 UI (Shadow DOM으로 사이트 스타일과 격리)
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

/* ------- 우측 사이드바 ------- */
.sidebar {
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 2147483610;
  width: min(360px, 94vw); background: #f5f6f8; color: #1c1e21;
  box-shadow: -12px 0 32px rgba(0,0,0,.18);
  display: flex; flex-direction: column; font-size: 14px; line-height: 1.6;
}
.sidebar-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 13px 16px; background: #fff; border-bottom: 1px solid #e5e7eb;
}
.sidebar-header .title { font-size: 15px; font-weight: 700; }
.sidebar-header .close {
  background: none; border: none; font-size: 16px; color: #6b7280; cursor: pointer; padding: 4px 8px;
}
.sidebar-header .close:hover { color: #1c1e21; }
.sidebar-body { overflow-y: auto; padding: 13px; flex: 1; }

.notice {
  background: #fffbeb; border: 1px solid #fde68a; color: #92400e;
  border-radius: 10px; padding: 10px 12px; font-size: 12.5px; margin-bottom: 10px;
}
.section {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
  padding: 12px 14px; margin-bottom: 10px;
}
.section h3 { margin: 0 0 8px; font-size: 13.5px; }
.section p { margin: 0; font-size: 13.5px; }
.hint { color: #6b7280; font-size: 12px; margin: 0 2px 10px; }

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
.loading-line { color: #6b7280; font-size: 12.5px; padding: 4px 2px; }

.sent-item {
  padding: 8px 10px; border-radius: 9px; margin-bottom: 6px;
  background: #eff6ff; font-size: 13px; cursor: pointer; line-height: 1.55;
}
.sent-item:hover { background: #dbeafe; }
.sent-item.unmatched { background: #f3f4f6; cursor: default; }
.sent-item .orig { display: block; color: #6b7280; font-size: 11.5px; margin-bottom: 3px; }
.sent-item .badge {
  display: inline-block; margin-top: 5px; font-size: 10.5px; color: #2563eb;
  background: #fff; border-radius: 999px; padding: 1px 8px; margin-right: 4px;
}
.sent-item .badge.hard { color: #c2410c; }

.term-item { padding: 6px 2px; border-bottom: 1px dashed #e5e7eb; font-size: 12.5px; }
.term-item:last-child { border-bottom: none; }
.term-item .t { font-weight: 700; color: #b45309; }
.term-item .d { color: #6b7280; font-size: 11.5px; display: block; margin-top: 1px; }

.error-card {
  background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c;
  border-radius: 10px; padding: 11px 13px; font-size: 13px;
}

/* ------- 문장 호버 카드 (기사 본문 옆에 뜸) ------- */
.card {
  position: fixed; z-index: 2147483630; width: 340px; max-width: 94vw;
  background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
  box-shadow: 0 10px 28px rgba(0,0,0,.18); padding: 11px 13px;
  font-size: 13px; line-height: 1.6; color: #1c1e21;
}
.card .easy {
  background: #eff6ff; border-radius: 9px; padding: 8px 11px; font-size: 13.5px; margin-bottom: 8px;
}
.card .easy::before { content: "🐣 "; }
.card .hard-chip {
  display: inline-block; background: #fff7ed; color: #c2410c;
  border: 1px solid #fed7aa; border-radius: 999px;
  font-size: 11px; font-weight: 700; padding: 2px 10px; margin-bottom: 7px;
}
.card .card-sub { font-size: 11px; font-weight: 700; color: #6b7280; margin: 2px 2px 4px; }
.card .ticker { color: #2563eb; font-weight: 600; cursor: pointer; border-bottom: 1.5px solid rgba(37,99,235,.35); }
.card .ticker:hover { background: #dbeafe; }
.card .term { border-bottom: 1.5px dotted #b45309; color: #b45309; cursor: help; }

.tooltip {
  position: fixed; z-index: 2147483640; max-width: 290px;
  background: #1f2937; color: #f9fafb; border-radius: 10px;
  padding: 9px 13px; font-size: 12.5px; box-shadow: 0 8px 24px rgba(0,0,0,.25);
  pointer-events: none; line-height: 1.5;
}
.tooltip .tt-term { font-weight: 700; color: #fbbf24; }
.tooltip .tt-easy { display: block; margin-top: 1px; }
.tooltip .tt-desc { display: block; margin-top: 5px; color: #d1d5db; font-size: 11.5px; }

/* ------- 차트 모달 ------- */
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
  <div class="sidebar" id="sidebar" hidden>
    <div class="sidebar-header">
      <span class="title">📰 주린이 번역 — 관련 정보</span>
      <button class="close" id="sidebar-close" aria-label="닫기">✕</button>
    </div>
    <div class="sidebar-body" id="sidebar-body"></div>
  </div>
  <div class="card" id="card" hidden></div>
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
const sidebar = $('#sidebar');
const sidebarBody = $('#sidebar-body');
const card = $('#card');
const tooltip = $('#tooltip');
const modal = $('#modal');
const chartCanvas = $('#chart-canvas');

// ---------------------------------------------------------------------------
// 상태
// ---------------------------------------------------------------------------
let translated = false;
let translating = false;
// sentIdx → { data: 문장 데이터, spans: 기사 본문에 달린 하이라이트 span 목록 }
const sentMap = new Map();

// ---------------------------------------------------------------------------
// 기능 켜기/끄기 (팝업의 토글 스위치와 연동)
// ---------------------------------------------------------------------------
fab.hidden = true; // 설정을 읽기 전엔 숨겨서 꺼짐 상태에서 깜빡이지 않게 함
chrome.storage.local.get(['enabled'], ({ enabled }) => {
  fab.hidden = enabled === false; // 기본값: 켜짐
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local' || !('enabled' in changes)) return;
  const on = changes.enabled.newValue !== false;
  fab.hidden = !on;
  if (!on) {
    // 끄면 열려 있던 UI를 모두 닫는다 (하이라이트는 무해하므로 유지)
    sidebar.hidden = true;
    hideCardNow();
    tooltip.hidden = true;
    modal.hidden = true;
  }
});

// ---------------------------------------------------------------------------
// 플로팅 버튼 → 번역 실행 / 사이드바 토글
// ---------------------------------------------------------------------------
fab.addEventListener('click', async () => {
  if (translating) return;
  if (translated) {
    sidebar.hidden = !sidebar.hidden;
    return;
  }
  const { text, container } = extractArticle();
  if (!text || text.length < 30) {
    sidebar.hidden = false;
    sidebarBody.innerHTML = `<div class="error-card">이 페이지에서 기사를 찾지 못했어요. 기사 본문 페이지에서 다시 시도해 주세요.</div>`;
    return;
  }

  translating = true;
  fabLabel.innerHTML = `<span class="spin"></span>`;
  fab.querySelector('span').textContent = '번역 중…';
  sidebar.hidden = false;
  sidebarBody.innerHTML = `<div class="hint">기사를 쉬운 말로 바꾸는 중이에요… (문장 수에 따라 몇 초 걸려요)</div>`;

  try {
    const data = await api('/api/translate', 'POST', { text });
    annotateArticle(container, data);
    renderSidebar(data);
    translated = true;
    fab.querySelector('span').textContent = '📰';
    fabLabel.textContent = '관련 정보 열기/닫기';
  } catch (err) {
    sidebarBody.innerHTML =
      `<div class="error-card">번역에 실패했어요: ${escapeHtml(err.message)}<br><br>` +
      `확장 아이콘(📰) 팝업의 ⚙️ 설정에서 API 주소를 확인해 주세요.</div>`;
    fab.querySelector('span').textContent = '📰';
    fabLabel.textContent = '다시 시도';
  } finally {
    translating = false;
  }
});

$('#sidebar-close').addEventListener('click', () => { sidebar.hidden = true; });

// ---------------------------------------------------------------------------
// 기사 본문에 하이라이트 달기
// ---------------------------------------------------------------------------
function collectTextNodes(container) {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      const p = n.parentElement;
      if (!p) return NodeFilter.FILTER_REJECT;
      const tag = p.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'TEXTAREA') {
        return NodeFilter.FILTER_REJECT;
      }
      if (!n.textContent.trim()) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes = [];
  let node;
  while ((node = walker.nextNode())) nodes.push(node);
  return nodes;
}

// 문장을 컨테이너의 텍스트 노드들에서 찾아 <span class="jn-hl">로 감싼다.
// 공백/줄바꿈 차이는 무시하도록 토큰 사이를 \s+로 잇는다.
function wrapSentence(container, sentence, idx) {
  const nodes = collectTextNodes(container);
  let full = '';
  const offsets = [];
  for (const n of nodes) { offsets.push(full.length); full += n.textContent; }

  const tokens = sentence.trim().split(/\s+/).filter(Boolean);
  if (!tokens.length) return [];
  const re = new RegExp(tokens.map(escapeRegex).join('[\\s\\u00a0]+'));
  const m = re.exec(full);
  if (!m) return [];

  const start = m.index;
  const end = m.index + m[0].length;
  const spans = [];
  for (let i = 0; i < nodes.length; i++) {
    const nStart = offsets[i];
    const nEnd = nStart + nodes[i].textContent.length;
    if (nEnd <= start || nStart >= end) continue;
    if (nodes[i].parentElement.closest('.jn-hl')) continue; // 이미 감싼 곳은 건너뜀

    const localStart = Math.max(0, start - nStart);
    const localEnd = Math.min(nodes[i].textContent.length, end - nStart);
    let target = nodes[i];
    if (localStart > 0) target = target.splitText(localStart);
    if (localEnd - localStart < target.textContent.length) target.splitText(localEnd - localStart);

    const span = document.createElement('span');
    span.className = 'jn-hl';
    span.dataset.jnIdx = idx;
    target.parentNode.insertBefore(span, target);
    span.appendChild(target);
    spans.push(span);
  }
  return spans;
}

// 하이라이트 span 내부에서 특정 문구를 찾아 종목/용어 span으로 한 번 더 감싼다.
function wrapInline(spanEl, matchText, className, dataset) {
  for (const tn of [...spanEl.childNodes]) {
    if (tn.nodeType !== Node.TEXT_NODE) continue;
    const i = tn.textContent.indexOf(matchText);
    if (i === -1) continue;
    let target = tn;
    if (i > 0) target = target.splitText(i);
    if (matchText.length < target.textContent.length) target.splitText(matchText.length);
    const el = document.createElement('span');
    el.className = className;
    for (const [k, v] of Object.entries(dataset)) el.dataset[k] = v;
    target.parentNode.insertBefore(el, target);
    el.appendChild(target);
    return true;
  }
  return false;
}

function annotateArticle(container, data) {
  data.sentences.forEach((s, idx) => {
    // 컨테이너에서 먼저 찾고, 못 찾으면(예: 제목) 문서 전체에서 한 번 더 찾는다.
    let spans = wrapSentence(container, s.original, idx);
    if (!spans.length && container !== document.body) {
      spans = wrapSentence(document.body, s.original, idx);
    }
    sentMap.set(idx, { data: s, spans });

    // 특히 어려운 문장은 주황색으로 표시
    if (s.hard) {
      for (const span of spans) span.classList.add('jn-hard');
    }

    // 문장 안의 종목명·용어에도 표시를 단다.
    for (const span of spans) {
      for (const m of s.mentions || []) {
        wrapInline(span, m.text, 'jn-ticker', { jnCode: m.code });
      }
      for (const t of s.terms || []) {
        wrapInline(span, t.term, 'jn-term', {
          jnTerm: t.term, jnEasy: t.easy, jnDesc: t.desc,
        });
      }
    }
  });
}

// ---------------------------------------------------------------------------
// 기사 위 상호작용 (페이지 DOM 이벤트 위임)
// ---------------------------------------------------------------------------
document.addEventListener('mouseover', (e) => {
  const t = e.target;
  if (!(t instanceof Element)) return;
  const term = t.closest('.jn-term');
  if (term) {
    showTooltip(term, term.dataset.jnTerm, term.dataset.jnEasy, term.dataset.jnDesc);
    return;
  }
  const hl = t.closest('.jn-hl');
  if (hl) scheduleCard(hl);
});

document.addEventListener('mouseout', (e) => {
  const t = e.target;
  if (!(t instanceof Element)) return;
  if (t.closest('.jn-term')) tooltip.hidden = true;
  if (t.closest('.jn-hl')) scheduleHideCard();
});

// 종목명 클릭 → 차트 (사이트 자체 링크보다 먼저 잡도록 캡처 단계 사용)
document.addEventListener('click', (e) => {
  const t = e.target;
  if (!(t instanceof Element)) return;
  const tk = t.closest('.jn-ticker');
  if (tk && tk.dataset.jnCode) {
    e.preventDefault();
    e.stopPropagation();
    hideCardNow();
    openChart(tk.dataset.jnCode);
  }
}, true);

// ---------------------------------------------------------------------------
// 문장 호버 카드 — 쉬운 번역 + 관련 종목
// ---------------------------------------------------------------------------
let cardShowTimer = null, cardHideTimer = null, cardToken = 0, activeIdx = -1;
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

card.addEventListener('mouseenter', () => clearTimeout(cardHideTimer));
card.addEventListener('mouseleave', scheduleHideCard);

function scheduleCard(hl) {
  clearTimeout(cardHideTimer);
  const idx = Number(hl.dataset.jnIdx);
  if (idx === activeIdx && !card.hidden) return;
  clearTimeout(cardShowTimer);
  cardShowTimer = setTimeout(() => showCard(idx, hl), 180);
}
function scheduleHideCard() {
  clearTimeout(cardShowTimer);
  clearTimeout(cardHideTimer);
  cardHideTimer = setTimeout(hideCardNow, 260);
}
function hideCardNow() {
  card.hidden = true;
  setActiveSentence(-1);
}
function setActiveSentence(idx) {
  if (activeIdx >= 0 && sentMap.has(activeIdx)) {
    for (const s of sentMap.get(activeIdx).spans) s.classList.remove('jn-active');
  }
  activeIdx = idx;
  if (idx >= 0 && sentMap.has(idx)) {
    for (const s of sentMap.get(idx).spans) s.classList.add('jn-active');
  }
}

function decorateText(text, mentions, terms) {
  const pats = [];
  for (const m of mentions || []) pats.push({ t: m.text, type: 'ticker', data: m });
  for (const t of terms || []) pats.push({ t: t.term, type: 'term', data: t });
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

async function showCard(idx, anchorEl) {
  const entry = sentMap.get(idx);
  if (!entry) return;
  const token = ++cardToken;
  setActiveSentence(idx);

  const s = entry.data;
  let html = '';
  if (s.hard) html += `<div class="hard-chip">🔥 특히 어려운 문장이에요</div>`;
  html += `<div class="easy">${decorateText(s.easy, s.mentions, s.terms)}</div>`;
  const related = s.related || [];
  if (related.length) {
    html += `<div class="card-sub">📈 관련 종목 — 누르면 차트가 열려요</div>`;
    html += `<div class="card-stocks"><div class="loading-line">시세를 불러오는 중…</div></div>`;
  }
  card.innerHTML = html;
  card.hidden = false;
  positionCard(anchorEl);

  if (!related.length) return;
  const quotes = await Promise.all(related.map((r) =>
    getQuote(r.code).then((q) => ({ ...q, reason: r.reason })).catch(() => null)
  ));
  if (token !== cardToken || card.hidden) return;

  const rows = quotes.filter(Boolean);
  const wrap = card.querySelector('.card-stocks');
  if (!wrap) return;
  if (!rows.length) {
    wrap.innerHTML = `<div class="loading-line">시세를 불러오지 못했어요.</div>`;
    return;
  }
  wrap.innerHTML = rows.map((q) => `
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
  wrap.querySelectorAll('canvas.spark').forEach(drawSparkline);
  positionCard(anchorEl);
}

function positionCard(anchorEl) {
  const rect = anchorEl.getBoundingClientRect();
  const cardW = card.offsetWidth || 340;
  const cardH = card.offsetHeight || 160;
  let left = Math.min(rect.left, window.innerWidth - cardW - 12);
  left = Math.max(8, left);
  let top = rect.bottom + 8;
  if (top + cardH + 10 > window.innerHeight) top = rect.top - cardH - 8;
  card.style.left = `${left}px`;
  card.style.top = `${Math.max(8, top)}px`;
}

// 카드 내부의 종목/용어 (Shadow DOM 이벤트 위임)
card.addEventListener('click', (e) => {
  const row = e.target.closest && e.target.closest('.stock-row');
  if (row && row.dataset.code) { hideCardNow(); openChart(row.dataset.code); return; }
  const ticker = e.target.closest && e.target.closest('.ticker');
  if (ticker && ticker.dataset.code) { hideCardNow(); openChart(ticker.dataset.code); }
});
card.addEventListener('mouseover', (e) => {
  const term = e.target.closest && e.target.closest('.term');
  if (term) showTooltip(term, term.dataset.term, term.dataset.easy, term.dataset.desc);
});
card.addEventListener('mouseout', (e) => {
  if (e.target.closest && e.target.closest('.term')) tooltip.hidden = true;
});

// ---------------------------------------------------------------------------
// 용어 툴팁 (기사·카드·사이드바 공용)
// ---------------------------------------------------------------------------
function showTooltip(anchorEl, term, easy, desc) {
  tooltip.innerHTML =
    `<span class="tt-term">${escapeHtml(term)}</span>` +
    `<span class="tt-easy">= ${escapeHtml(easy)}</span>` +
    `<span class="tt-desc">${escapeHtml(desc)}</span>`;
  tooltip.hidden = false;
  const rect = anchorEl.getBoundingClientRect();
  const ttW = tooltip.offsetWidth;
  const left = Math.min(rect.left, window.innerWidth - ttW - 8);
  tooltip.style.left = `${Math.max(8, left)}px`;
  tooltip.style.top = `${rect.bottom + 6}px`;
}

// ---------------------------------------------------------------------------
// 우측 사이드바 — 요약 · 관련 종목 전체 · 문장 목록 · 용어 사전
// ---------------------------------------------------------------------------
async function renderSidebar(data) {
  let html = '';
  if (data.notice) html += `<div class="notice">${escapeHtml(data.notice)}</div>`;
  if (data.summary) html += `<div class="section"><h3>📌 세 줄 요약</h3><p>${escapeHtml(data.summary)}</p></div>`;
  html += `<div class="hint">💡 기사 본문의 <u>파란 밑줄 문장</u>에 마우스를 올려보세요. 쉬운 번역과 관련 종목이 바로 옆에 떠요. <span style="color:#c2410c">주황 문장</span>은 특히 어려운 문장, 점선 용어는 호버하면 뜻이 나와요.</div>`;

  // 기사 전체에서 언급된 관련 종목 (중복 제거)
  const agg = new Map();
  for (const s of data.sentences) {
    for (const r of s.related || []) {
      if (!agg.has(r.code)) agg.set(r.code, r);
    }
  }
  if (agg.size) {
    html += `<div class="section"><h3>📈 이 기사의 관련 종목</h3><div id="sb-stocks"><div class="loading-line">시세를 불러오는 중…</div></div></div>`;
  }

  // 문장별 쉬운 번역 목록 (클릭하면 해당 문장으로 스크롤)
  html += `<div class="section"><h3>🐣 문장별 쉬운 말</h3><div id="sb-sents">`;
  data.sentences.forEach((s, idx) => {
    const entry = sentMap.get(idx);
    const matched = entry && entry.spans.length > 0;
    let badge = '';
    if (s.hard) badge += `<span class="badge hard">🔥 어려운 문장</span>`;
    if ((s.related || []).length) badge += `<span class="badge">📈 관련 종목 ${s.related.length}개</span>`;
    if (matched) {
      html += `<div class="sent-item" data-idx="${idx}" title="누르면 기사에서 이 문장을 찾아가요">${escapeHtml(s.easy)}${badge}</div>`;
    } else {
      html += `<div class="sent-item unmatched"><span class="orig">${escapeHtml(s.original)}</span>${escapeHtml(s.easy)}${badge}</div>`;
    }
  });
  html += `</div></div>`;

  // 용어 사전 (중복 제거)
  const terms = new Map();
  for (const s of data.sentences) {
    for (const t of s.terms || []) if (!terms.has(t.term)) terms.set(t.term, t);
  }
  if (terms.size) {
    html += `<div class="section"><h3>📖 어려운 용어 풀이</h3>`;
    for (const t of terms.values()) {
      html += `<div class="term-item"><span class="t">${escapeHtml(t.term)}</span> = ${escapeHtml(t.easy)}<span class="d">${escapeHtml(t.desc)}</span></div>`;
    }
    html += `</div>`;
  }
  sidebarBody.innerHTML = html;

  // 관련 종목 시세 채우기
  if (agg.size) {
    const quotes = await Promise.all([...agg.values()].map((r) =>
      getQuote(r.code).then((q) => ({ ...q, reason: r.reason })).catch(() => null)
    ));
    const wrap = sidebarBody.querySelector('#sb-stocks');
    if (!wrap) return;
    const rows = quotes.filter(Boolean);
    if (!rows.length) {
      wrap.innerHTML = `<div class="loading-line">시세를 불러오지 못했어요.</div>`;
    } else {
      wrap.innerHTML = rows.map((q) => `
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
      wrap.querySelectorAll('canvas.spark').forEach(drawSparkline);
    }
  }
}

sidebarBody.addEventListener('click', (e) => {
  const row = e.target.closest && e.target.closest('.stock-row');
  if (row && row.dataset.code) { openChart(row.dataset.code); return; }
  const item = e.target.closest && e.target.closest('.sent-item[data-idx]');
  if (item) {
    const entry = sentMap.get(Number(item.dataset.idx));
    if (entry && entry.spans.length) {
      const span = entry.spans[0];
      span.scrollIntoView({ behavior: 'smooth', block: 'center' });
      for (const s of entry.spans) {
        s.classList.remove('jn-flash');
        void s.offsetWidth; // 애니메이션 재시작
        s.classList.add('jn-flash');
      }
    }
  }
});

// ---------------------------------------------------------------------------
// 스파크라인
// ---------------------------------------------------------------------------
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
