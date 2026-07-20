// 백그라운드 서비스 워커 — 콘텐츠 스크립트 대신 API를 호출한다.
// (확장 컨텍스트에서 fetch하면 뉴스 사이트의 CORS 제약을 받지 않는다)
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type !== 'api') return;

  (async () => {
    try {
      const { apiUrl } = await chrome.storage.local.get(['apiUrl']);
      const base = (apiUrl || 'http://localhost:8000').replace(/\/+$/, '');
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
      const { apiUrl } = await chrome.storage.local.get(['apiUrl']).catch(() => ({}));
      const base = (apiUrl || 'http://localhost:8000').replace(/\/+$/, '');
      sendResponse({
        ok: false,
        error: `서버(${base})에 연결하지 못했어요. 백엔드(python run.py)가 실행 중인지, 팝업 ⚙️ 설정의 API 주소가 맞는지 확인해 주세요.`,
      });
    }
  })();

  return true; // 비동기 응답
});
