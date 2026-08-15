# 금융상품 Agent — 구현 현황

미래에셋증권 AI Festival 과제 구현체. 전략과 일정은 [AI_FESTIVAL_PLAN.md](./AI_FESTIVAL_PLAN.md) 참고.

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env      # CLOVASTUDIO_API_KEY 입력
uvicorn src.api:app --host 0.0.0.0 --port 8000
```

```bash
curl -G "http://localhost:8000/answer" \
  --data-urlencode "question_id=Q-001" \
  --data-urlencode "question=신용등급 AAAA인 채권 찾아줘"
```

```bash
python -m pytest tests/ -q
```

## 현재 구현 범위

| 단계 | 상태 | 위치 |
|---|---|---|
| `GET /answer` 규격 준수 | 완료 | `src/api.py` |
| 답변불가 가드 G1·G2·G3 | 완료 | `src/agent/guards.py` |
| Intent 라우팅 (SQL/VECTOR/GRAPH/HYBRID) | 완료 | `src/agent/router.py` |
| HyperCLOVA X 클라이언트 | 완료 (실호출 미검증) | `src/llm.py` |
| 엔티티 레지스트리 | 시드 데이터로 동작 | `src/kb/registry.py` |
| 마스터 4종 적재 (DuckDB) | 미착수 — **데이터 대기** | `src/ingest/` |
| Ontology `.ttl` 5종 | 미착수 — 데이터 대기 | `ontology/` |
| Vector · Graph 인덱스 | 미착수 | `src/kb/` |
| NL2SQL · Retrieval · 생성 | 미착수 | `src/agent/pipeline.py` |

`_KB_READY = False`인 동안 답변 가능한 질의는 "확인할 수 없습니다"로 응답한다.
검색할 데이터가 없는 상태에서 답을 만들면 과제 규칙("데이터에 근거 없는 내용 생성
금지")을 위반하므로, 적재 전까지는 의도적으로 답하지 않는다.

## LLM — HyperCLOVA X

CLOVA Studio를 사용한다. 모델 후보는 `HCX-007 → HCX-005 → HCX-003 → HCX-DASH-002
→ HCX-DASH-001` 순이며, 신규 키(Bearer) 방식과 구 APIGW 키 방식을 모두 시도한다.

**첫 성공 조합은 프로세스 수명 동안 고정된다.** 응답 소요 시간이 평가 항목이라
요청마다 후보를 재탐색하면 안 되기 때문이다. `CLOVASTUDIO_MODEL`로 고정할 수도 있다.

호출부는 `chat()` / `chat_json()` 두 함수만 노출한다. 과제 자료에 "필수 LLM 활용
기준 추후 공지 예정"이라고 되어 있어 모델 교체 가능성을 열어둔 구조다.

## 답변불가 가드

30문항 중 5문항이 답변 불가 질의이고 답변을 생성하면 감점된다. 가드는 검색·생성
**이전**에 동작해 환각을 원천 차단하고 응답 시간도 아낀다.

| 가드 | 판정 | 예시 |
|---|---|---|
| G1 | 등급 값이 국내 신용등급 체계 밖 | `신용등급 AAAA인 채권 찾아줘` |
| G2 | 라틴 고유명사가 어떤 인덱스에도 미해결 | `Kimi 관련 투자 상품 있어?` |
| G3 | 브랜드 지목 상품명의 최고 유사도 < 0.72 | `KODEX AI로봇 ETF 정보 알려줘` |

오탐(답변 가능한 질의 차단)이 미탐보다 비싸므로 보수적으로 잡았다.

- G2는 **라틴 문자 토큰만** 검사한다. 한글 고유명사까지 검사하면 `캠브리콘이 편입된
  중국 반도체 ETF`처럼 외부 데이터로 답할 수 있는 질의를 막게 된다. 실제 마스터와
  기업 인덱스가 붙은 뒤에 확장한다.
- G3는 **브랜드 접두어가 있을 때만** 동작한다. `중국 반도체 ETF`, `국민성장펀드`
  같은 범주 서술을 상품명 지목으로 오인하지 않기 위함이다.

`tests/test_agent.py`가 과제 자료의 답변 불가 예시 3건과 답변 가능 예시 6건을
양방향으로 고정한다.

## 데이터 확보 후 해야 할 일

1. `src/kb/registry.py`의 `_load_products()`를 DuckDB 조회로 교체 — 가드·라우터는 무수정
2. `src/ingest/`에 xlsx → DuckDB 적재기 작성
3. `ontology/*.ttl` 5종 생성 (필수 제출물)
4. `src/agent/pipeline.py`의 `_KB_READY`를 True로 전환하고 Retrieval 연결
