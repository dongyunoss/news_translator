# 주린이 뉴스 번역기 - 브라우저 확장

경제 뉴스를 주식 초보자 눈높이의 쉬운 말로 자동 번역하는 Chrome/Edge 확장 프로그램입니다.

## 설치 방법

### 개발 모드 설치 (Chrome/Edge)

1. **확장 폴더 위치 확인**
   ```bash
   # 프로젝트 폴더에서
   cd extension
   ```

2. **Chrome 확장 페이지 열기**
   - Chrome: `chrome://extensions/`
   - Edge: `edge://extensions/`

3. **개발자 모드 활성화**
   - 우상단 "개발자 모드" 토글 ON

4. **확장 로드**
   - "압축되지 않은 확장 프로그램을 로드합니다" 클릭
   - 이 폴더의 `extension/` 디렉토리 선택

5. **설치 완료**
   - 브라우저 우상단에 📰 아이콘이 나타남

## 사용 방법

### 기본 사용

1. **뉴스 사이트 방문**
   - 네이버 뉴스, 한경닷컴, 매경, 이데일리 등 지원

2. **확장 아이콘 클릭**
   - 우상단 📰 아이콘 클릭

3. **기사 추출 (선택)**
   - "현재 페이지에서 기사 추출" 클릭
   - 또는 수동으로 기사 텍스트 붙여넣기

4. **번역 실행**
   - "번역하기" 버튼 클릭
   - 백엔드 API 서버와 통신하여 번역

5. **결과 확인**
   - 쉬운 말로 번역된 기사 표시
   - 용어 설명 (마우스 호버)
   - 관련 종목 정보 (클릭 가능)

### 설정

1. **API 주소 설정**
   - 우상단 ⚙️ 클릭
   - API 주소 입력 (예: `https://api.railway.app`)
   - API 키 입력 (선택사항)
   - "저장" 클릭

**기본값:**
- API 주소: `http://localhost:8000` (로컬 개발)
- 프로덕션: `https://news-translator-api.railway.app`

## 지원 뉴스 사이트

✅ **자동 추출 지원:**
- 네이버 뉴스 (news.naver.com)
- 한경닷컴 (hankyung.com)
- 매경 (mk.co.kr)
- 이데일리 (edaily.co.kr)
- 인베스터 (investor.co.kr)
- 헤럴드 경제 등 대부분의 뉴스 사이트

✏️ **수동 입력:**
- 모든 웹사이트에서 텍스트 복사-붙여넣기 가능

## 파일 구조

```
extension/
├── manifest.json          # 확장 설정 및 권한
├── popup.html            # 팝업 UI
├── popup.css             # 팝업 스타일
├── popup.js              # 팝업 로직
├── content_script.js     # 뉴스 사이트 기사 추출
└── README.md             # 이 파일
```

## 기술 사양

- **Manifest Version:** 3 (Chrome 최신 표준)
- **권한:** activeTab, scripting, storage
- **통신:** Fetch API (CORS 지원)
- **저장소:** Chrome Local Storage

## 트러블슈팅

### "기사를 추출하지 못했습니다"

1. **지원 사이트 확인**
   - 위의 지원 뉴스 사이트 목록 참고
   - 다른 사이트는 수동 입력 필요

2. **페이지 새로고침**
   - F5 또는 Ctrl+R로 새로고침 후 다시 시도

3. **콘솔 확인**
   - F12로 개발자 도구 열기
   - Console 탭에서 에러 메시지 확인

### "번역에 실패했습니다"

1. **API 주소 확인**
   - 설정에서 올바른 API URL 입력 확인
   - API 서버가 실행 중인지 확인

2. **로컬 개발:**
   ```bash
   # 백엔드 실행
   python run.py
   # http://localhost:8000 에서 실행 중 확인
   ```

3. **프로덕션:**
   ```bash
   # API 주소를 Railway 백엔드로 설정
   https://news-translator-api.railway.app
   ```

4. **네트워크 확인**
   - 인터넷 연결 상태 확인
   - 방화벽/프록시 설정 확인

## 개발 및 수정

### 코드 수정 후 새로고침

1. Chrome 확장 페이지에서 새로고침 (🔄 아이콘)
2. 또는 Ctrl+Shift+R로 강제 새로고침

### 디버깅

- **Popup 디버깅:** popup.html 우클릭 → "검사"
- **Content Script 디버깅:** 웹사이트에서 F12 → 콘솔 확인
- **Background Script:** 확장 관리 페이지에서 "서비스 워커 검사"

## 라이선스

MIT

## 문의

버그 리포트 또는 기능 요청: 프로젝트 GitHub Issues
