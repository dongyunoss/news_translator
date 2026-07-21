// DOM 요소
const articleText = document.getElementById('article-text');
const extractBtn = document.getElementById('extract-btn');
const translateBtn = document.getElementById('translate-btn');
const errorMsg = document.getElementById('error-msg');
const statusMsg = document.getElementById('status-msg');
const inputSection = document.getElementById('input-section');
const resultSection = document.getElementById('result-section');
const summaryCard = document.getElementById('summary-card');
const summaryText = document.getElementById('summary-text');
const sentencesContainer = document.getElementById('sentences-container');
const settingsBtn = document.getElementById('settings-btn');
const settingsPanel = document.getElementById('settings-panel');
const saveSettingsBtn = document.getElementById('save-settings');
const cancelSettingsBtn = document.getElementById('cancel-settings');
const apiUrlInput = document.getElementById('api-url');
const apiKeyInput = document.getElementById('api-key');
const enableToggle = document.getElementById('enable-toggle');
const toggleStatus = document.getElementById('toggle-status');

// ---------------------------------------------------------------------------
// 기능 켜기/끄기 토글 — 기사 페이지의 번역 버튼(FAB)을 보이거나 숨긴다
// ---------------------------------------------------------------------------
function renderToggleStatus(enabled) {
  toggleStatus.textContent = enabled
    ? '기사 페이지에서 번역 버튼이 표시돼요'
    : '기능이 꺼져 있어요 — 기사 페이지에 버튼이 표시되지 않아요';
  toggleStatus.classList.toggle('off', !enabled);
}

chrome.storage.local.get(['enabled'], ({ enabled }) => {
  const on = enabled !== false; // 기본값: 켜짐
  enableToggle.checked = on;
  renderToggleStatus(on);
});

enableToggle.addEventListener('change', () => {
  const on = enableToggle.checked;
  chrome.storage.local.set({ enabled: on });
  renderToggleStatus(on);
});

// 설정 토글
settingsBtn.addEventListener('click', () => {
  settingsPanel.hidden = !settingsPanel.hidden;
  if (!settingsPanel.hidden) {
    loadSettings();
  }
});

// 설정 저장
saveSettingsBtn.addEventListener('click', () => {
  chrome.storage.local.set({
    apiUrl: apiUrlInput.value,
    apiKey: apiKeyInput.value,
  });
  settingsPanel.hidden = true;
  showStatus('설정이 저장되었습니다.');
});

cancelSettingsBtn.addEventListener('click', () => {
  settingsPanel.hidden = true;
});

// 설정 로드
function loadSettings() {
  chrome.storage.local.get(['apiUrl', 'apiKey'], (result) => {
    apiUrlInput.value = result.apiUrl || '';
    apiKeyInput.value = result.apiKey || '';
  });
}

// 현재 페이지에서 기사 추출
extractBtn.addEventListener('click', async () => {
  showStatus('기사를 추출 중입니다...');
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  chrome.tabs.sendMessage(tab.id, { action: 'extractText' }, (response) => {
    if (response && response.text) {
      articleText.value = response.text;
      showStatus('기사가 추출되었습니다.');
    } else {
      showError('기사를 추출하지 못했습니다.');
    }
  });
});

// 번역 실행
translateBtn.addEventListener('click', async () => {
  const text = articleText.value.trim();
  if (!text) {
    showError('번역할 기사 텍스트를 입력해주세요.');
    return;
  }

  showStatus('번역 중입니다...');
  translateBtn.disabled = true;

  try {
    const settings = await new Promise((resolve) => {
      chrome.storage.local.get(['apiUrl', 'apiKey'], resolve);
    });

    const apiUrl = settings.apiUrl || 'http://localhost:8000';
    const response = await fetch(`${apiUrl}/api/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || '번역에 실패했습니다.');
    }

    const data = await response.json();
    renderResult(data);
    statusMsg.hidden = true;
  } catch (err) {
    showError(`번역 오류: ${err.message}`);
  } finally {
    translateBtn.disabled = false;
  }
});

// 결과 렌더링
function renderResult(data) {
  resultSection.hidden = false;
  sentencesContainer.innerHTML = '';

  if (data.summary) {
    summaryText.innerHTML = escapeHtml(data.summary);
    summaryCard.hidden = false;
  }

  for (const s of data.sentences) {
    const block = document.createElement('div');
    block.className = 'sentence-block';

    const original = document.createElement('div');
    original.className = 'sentence-original';
    original.textContent = s.original;

    const easy = document.createElement('div');
    easy.className = 'sentence-easy';
    easy.innerHTML = decorateText(s.easy, s.mentions || [], s.terms || []);

    block.appendChild(original);
    block.appendChild(easy);
    sentencesContainer.appendChild(block);
  }
}

// 텍스트 장식 (티커, 용어 하이라이트)
function decorateText(text, mentions, terms) {
  let html = escapeHtml(text);

  const patterns = [];
  for (const m of mentions) {
    patterns.push({ text: m.text, type: 'ticker', data: m });
  }
  for (const t of terms) {
    patterns.push({ text: t.term, type: 'term', data: t });
  }

  patterns.sort((a, b) => b.text.length - a.text.length);

  for (const p of patterns) {
    const escaped = escapeHtml(p.text);
    const regex = new RegExp(`\\b${escaped}\\b`, 'g');

    if (p.type === 'ticker') {
      html = html.replace(
        regex,
        `<span class="ticker" title="${p.data.code}">${escaped}</span>`
      );
    } else if (p.type === 'term') {
      html = html.replace(
        regex,
        `<span class="term" title="${escapeHtml(p.data.desc)}">${escaped}</span>`
      );
    }
  }

  return html;
}

// HTML 이스케이프
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// 에러 표시
function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.hidden = false;
  statusMsg.hidden = true;
}

// 상태 메시지 표시
function showStatus(msg) {
  statusMsg.textContent = msg;
  statusMsg.hidden = false;
  errorMsg.hidden = true;
}

// 페이지 로드 시 설정 로드
chrome.storage.local.get(['apiUrl'], (result) => {
  if (result.apiUrl) {
    showStatus(`API: ${result.apiUrl}`);
  }
});
