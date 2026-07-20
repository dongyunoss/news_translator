# 배포 가이드

## 자동 배포 (권장)

### 1. Railway에서 백엔드 배포

1. [railway.app](https://railway.app)에서 계정 생성
2. GitHub와 연결
3. New Project → Deploy from GitHub repo 선택
4. `dongyunoss/news_translator` 선택
5. 환경 변수 설정:
   - `ANTHROPIC_API_KEY`: Claude API 키

Railway가 자동으로 `Procfile`을 인식하고 FastAPI 앱을 실행합니다.

**배포 후 백엔드 URL 확인**: 예) `https://news-translator-api.railway.app`

### 2. Vercel에서 프론트엔드 배포

1. [vercel.com](https://vercel.com)에서 계정 생성
2. GitHub와 연결
3. Import Project → GitHub repo 선택
4. `dongyunoss/news_translator` 선택
5. 환경 변수 설정:
   - `API_BASE_URL`: Railway 백엔드 URL (예: `https://news-translator-api.railway.app`)

Vercel이 자동으로 `vercel.json`을 읽고 `static/` 폴더를 배포합니다.

---

## 로컬 실행

```bash
pip install -r requirements.txt
python run.py
```

http://localhost:8000 접속

---

## 환경 변수 설정

### 로컬 개발
`.env` 파일 생성:
```
ANTHROPIC_API_KEY=sk-...
```

### Railway
Project Settings → Variables에서 추가

### Vercel  
Project Settings → Environment Variables에서 추가

---

## 구조

```
news_translator/
├── static/           # 프론트엔드 (Vercel 배포)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── app/              # 백엔드 (Railway 배포)
│   ├── main.py       # FastAPI 앱
│   ├── translator.py # Claude 번역
│   ├── stocks.py     # 주식 데이터
│   └── data/         # glossary.json, stocks.json
├── requirements.txt  # Python 의존성
├── Procfile          # Railway 배포 설정
├── vercel.json       # Vercel 배포 설정
└── run.py            # 로컬 실행 스크립트
```

---

## 크로스 도메인 설정

프론트엔드(Vercel)와 백엔드(Railway)가 다른 도메인에 배포되므로:
- 백엔드에서 CORS 허용 필요 (이미 설정됨)
- 프론트엔드의 `app.js`가 자동으로 API URL 감지

### 커스텀 API 주소

프로덕션에서 다른 백엔드를 사용하려면:
1. Vercel 프로젝트 Settings
2. Environment Variables
3. `API_BASE_URL` 추가 (예: `https://your-backend.com`)
4. Redeploy
