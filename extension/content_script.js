// 콘텐츠 스크립트 - 뉴스 사이트에 주입됨
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractText') {
    const text = extractArticleText();
    sendResponse({ text });
  }
});

// 뉴스 사이트에서 기사 텍스트 추출
function extractArticleText() {
  const hostname = window.location.hostname;

  // 각 뉴스 사이트별 추출 로직
  if (hostname.includes('naver.com')) {
    return extractNaver();
  } else if (hostname.includes('hankyung.com')) {
    return extractHankyung();
  } else if (hostname.includes('mk.co.kr')) {
    return extractMk();
  } else if (hostname.includes('edaily.co.kr')) {
    return extractEdaily();
  } else if (hostname.includes('investor.co.kr')) {
    return extractInvestor();
  }

  // 기본 추출 (대부분의 뉴스 사이트)
  return extractGeneric();
}

// 네이버 뉴스
function extractNaver() {
  let text = '';

  // 제목
  const titleEl = document.querySelector('h2.media_end_head_headline, h1#title_area');
  if (titleEl) {
    text += titleEl.textContent.trim() + '\n\n';
  }

  // 본문
  const articleBody =
    document.querySelector('#dic_area') || document.querySelector('.newsct_article');
  if (articleBody) {
    text += articleBody.textContent
      .replace(/\n\s*\n/g, '\n')
      .trim();
  }

  return text;
}

// 한경닷컴
function extractHankyung() {
  let text = '';

  // 제목
  const titleEl = document.querySelector('h1.title');
  if (titleEl) {
    text += titleEl.textContent.trim() + '\n\n';
  }

  // 본문
  const articleBody = document.querySelector('.article-body');
  if (articleBody) {
    text += articleBody.textContent.trim();
  }

  return text;
}

// 매경
function extractMk() {
  let text = '';

  const titleEl = document.querySelector('h2.news_title, h1');
  if (titleEl) {
    text += titleEl.textContent.trim() + '\n\n';
  }

  const articleBody = document.querySelector('#content, .article_content');
  if (articleBody) {
    text += articleBody.textContent.trim();
  }

  return text;
}

// 이데일리
function extractEdaily() {
  let text = '';

  const titleEl = document.querySelector('h1.article_title');
  if (titleEl) {
    text += titleEl.textContent.trim() + '\n\n';
  }

  const articleBody = document.querySelector('#article_content');
  if (articleBody) {
    text += articleBody.textContent.trim();
  }

  return text;
}

// 인베스터
function extractInvestor() {
  let text = '';

  const titleEl = document.querySelector('h1.subject');
  if (titleEl) {
    text += titleEl.textContent.trim() + '\n\n';
  }

  const articleBody = document.querySelector('.article_content, #articleContent');
  if (articleBody) {
    text += articleBody.textContent.trim();
  }

  return text;
}

// 일반 추출 (CSS 선택자 기반)
function extractGeneric() {
  let text = '';

  // 제목 시도
  const titleSelectors = ['h1', 'h2.title', 'h1.headline', 'h1.article-title'];
  for (const sel of titleSelectors) {
    const el = document.querySelector(sel);
    if (el && el.textContent.length > 10) {
      text += el.textContent.trim() + '\n\n';
      break;
    }
  }

  // 본문 시도
  const bodySelectors = [
    'article',
    '.article-body',
    '.article_content',
    '#article-content',
    '.news-body',
    '[role="main"]',
  ];

  for (const sel of bodySelectors) {
    const el = document.querySelector(sel);
    if (el && el.textContent.length > 100) {
      const content = el.textContent
        .replace(/\n\s*\n/g, '\n')
        .replace(/\s+/g, ' ')
        .trim();
      text += content;
      break;
    }
  }

  // 아무것도 없으면 body 전체 사용
  if (text.length < 50) {
    text = document.body.innerText;
  }

  return text;
}
