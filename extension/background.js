// 백그라운드 서비스 워커 — 콘텐츠 스크립트 대신 API를 호출한다.
// (확장 컨텍스트에서 fetch하면 뉴스 사이트의 CORS 제약을 받지 않는다)

// 사용자가 입력한 API 주소를 안전한 형태로 보정한다.
// - 앞뒤 공백 제거, 끝의 / 제거
// - "example.up.railway.app"처럼 스킴이 없으면 https:// 를 붙인다
//   (localhost/127.0.0.1 은 http:// 를 붙인다)
function normalizeBase(apiUrl) {
  let base = (apiUrl || '').trim().replace(/\/+$/, '');
  if (!base) return 'http://localhost:8000';
  if (!/^https?:\/\//i.test(base)) {
    const isLocal = /^(localhost|127\.0\.0\.1)(:|$)/i.test(base);
    base = (isLocal ? 'http://' : 'https://') + base;
  }
  return base;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type !== 'api') return;

  (async () => {
    let base = 'http://localhost:8000';
    try {
      const { apiUrl } = await chrome.storage.local.get(['apiUrl']);
      base = normalizeBase(apiUrl);
      const res = await fetch(base + msg.path, {
        method: msg.method || 'GET',
        headers: msg.body ? { 'Content-Type': 'application/json' } : undefined,
        body: msg.body ? JSON.stringify(msg.body) : undefined,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        sendResponse({ ok: false, error: data.detail || res.statusText || `HTTP ${res.status}` });
      } else {
        sendResponse({ ok: true, data });
      }
    } catch (e) {
      sendResponse({
        ok: false,
        error:
          `서버(${base})에 연결하지 못했어요. ` +
          (base.includes('localhost')
            ? '백엔드(python run.py)가 실행 중인지 확인해 주세요.'
            : '주소가 맞는지, 서버가 켜져 있는지 확인해 주세요.'),
      });
    }
  })();

  return true; // 비동기 응답
});
