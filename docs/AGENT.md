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
  --data-urlencode "question=공모펀드 중 총보수가 가장 낮은 상품 알려줘"
```

```bash
python -m pytest tests/ -q
```

## 설계 원칙 — 예시가 아니라 스키마에서 판정한다

과제 자료의 질의 예시는 예시일 뿐이고, 실제 평가는 못 본 30문항이다. 예시 문자열에
맞춘 규칙은 그 3~5건에만 듣는다. 그래서 판정 근거를 전부 `ontology/*.ttl`로 옮겼다.

| 온톨로지 선언 | 코드가 읽어 쓰는 곳 |
|---|---|
| `skos:ConceptScheme` + `fp:ordinal` | 값 체계 검증(G1), "AA- 이상" 서열 비교 |
| `fp:coverage` | 미수록 속성 판정(G4) |
| `fp:sourceTable` / `fp:sourceColumn` | `retrieved_context` 자동 생성 |
| `rdfs:domain` + 하위 클래스 폐포 | 상품군별 속성 적용 범위 |
| `skos:altLabel` | 질의 표현 ↔ 컬럼 라벨 매칭 |

컬럼이 늘거나 등급 체계가 바뀌면 `.ttl`만 고치면 되고, 가드·라우팅·근거 표시가
함께 따라온다.

## 현재 구현 범위

| 단계 | 상태 | 위치 |
|---|---|---|
| Ontology `.ttl` 5종 (필수 제출물) | 완료 · 932 triples | `ontology/` |
| 온톨로지 런타임 로더 | 완료 | `src/kb/ontology.py` |
| `GET /answer` 규격 준수 | 완료 | `src/api.py` |
| 답변불가 가드 G1~G4 | 완료 | `src/agent/guards.py` |
| 근거(`retrieved_context`) 자동 생성 | 완료 | `src/agent/pipeline.py` |
| Intent 라우팅 (SQL/VECTOR/GRAPH/HYBRID) | 완료 | `src/agent/router.py` |
| 조사 처리 | 완료 | `src/korean.py` |
| HyperCLOVA X 클라이언트 | 완료 (실호출 미검증) | `src/llm.py` |
| 마스터 4종 적재 (DuckDB) | 미착수 — **데이터 대기** | `src/ingest/` |
| Vector · Graph 인덱스 | 미착수 | `src/kb/` |
| NL2SQL · Retrieval · 생성 | 미착수 | `src/agent/pipeline.py` |

`_KB_READY = False`인 동안 답변 가능한 질의는 "확인할 수 없습니다"로 응답한다.
검색할 데이터가 없는 상태에서 답을 만들면 과제 규칙("데이터에 근거 없는 내용 생성
금지")을 위반하므로, 적재 전까지는 의도적으로 답하지 않는다.

## 온톨로지

```
ontology/
├─ common.ttl     fp:Product 계층, 공통 속성, 위험등급·투자자산군·투자지역 체계
├─ bond_kr.ttl    국내채권(PRBD01N001) — 신용등급 장기/단기 체계, 채권종류
├─ etf_kr.ttl     국내 ETF(PREF01N001) — 기간수익률, 외부 수집 관계(편입·테마·자회사)
├─ etf_gl.ttl     해외 ETF(PREF02N001) — 티커·ISIN·상장시장·거래통화, 운용전략 서술
└─ fund_pub.ttl   공모펀드(PRFD01N001) — 운용속성, 환헤지, 미수록 속성 선언
```

설계에서 신경 쓴 두 지점:

**등급은 서열(`fp:ordinal`)로 사상한다.** "AA- 이상"을 문자열 비교로 풀면 사전순으로
`AA- < AAA < AA+`가 되어 조건이 깨진다. 등급마다 정수를 부여해 부등호가 성립하게 했다.
위험등급은 방향이 반대라(1등급이 가장 위험) 숫자를 그대로 쓰면 정반대 결과가 나오므로,
`ordinal`은 위험의 크기를 따르게 두고 숫자는 코드로만 남겼다.

**마스터에 없는 축을 명시한다.** 편입종목·자회사관계·테마연결은 컬럼으로 존재하지
않으므로 `fp:coverage "external"`로 선언했다. 이 관계가 없으면 "에코프로의 자회사를
편입한 ETF" 같은 질의는 구조적으로 답할 수 없다는 사실이 스키마에 드러난다.

## 답변불가 가드

30문항 중 5문항이 답변 불가 질의이고 답변을 생성하면 감점된다. 가드는 검색·생성
**이전**에 동작해 환각을 원천 차단하고 응답 시간도 아낀다.

| 가드 | 판정 | 걸리는 예 |
|---|---|---|
| G1 | 값이 그 속성의 값 체계에 없음 | `신용등급 AAAA`, `AA++`, `EEE`, `위험등급 9등급` |
| G2 | 라틴 고유명사가 어떤 인덱스에도 미해결 | `Kimi 관련 투자 상품 있어?` |
| G3 | 브랜드 지목 상품명의 최고 유사도 < 0.72 | `KODEX AI로봇 ETF` |
| G4 | 그 상품군에 해당 속성이 미수록 | `공모펀드 총보수`, `펀드 선취수수료` |

G1의 숫자형 패턴은 허용값에서 자동으로 유도한다. `1등급`에서 `\d+등급`을 만들어
`9등급`을 걸러내는 식이라, 값 체계가 바뀌어도 규칙을 다시 쓰지 않는다.

G4는 상품군을 좁히지 못한 질의에는 동작하지 않는다. "총보수 낮은 상품"은 해외
ETF로는 답할 수 있으므로 막으면 오탐이다. 언급된 상품군 **전부**에서 미수록일 때만
차단하고, 조회 가능한 다른 상품군을 역질문으로 안내한다.

### 오탐 방지

답변 불가 5문항을 놓치는 것보다 답변 가능한 25문항을 잘못 막는 쪽이 비싸다.

- G2는 **라틴 문자 토큰만** 검사한다. 한글까지 검사하면 `캠브리콘이 편입된 중국
  반도체 ETF`처럼 외부 데이터로 답할 수 있는 질의가 막힌다.
- G3는 **브랜드 접두어가 있을 때만** 동작한다. `중국 반도체 ETF`, `국민성장펀드`
  같은 범주 서술을 상품명 지목으로 오인하지 않기 위함이다.
- G1의 한글 값 검사는 허용값에서 유도한 숫자형 패턴으로 제한한다.

`tests/test_agent.py`가 과제 예시 9건과 **예시에 없는 일반화 케이스 15건**을
양방향으로 고정한다. 답변 가능한 질의가 가드에 걸리면 빌드가 깨진다.

## LLM — HyperCLOVA X

CLOVA Studio를 사용한다. 모델 후보는 `HCX-007 → HCX-005 → HCX-003 → HCX-DASH-002
→ HCX-DASH-001` 순이며, 신규 키(Bearer) 방식과 구 APIGW 키 방식을 모두 시도한다.

**첫 성공 조합은 프로세스 수명 동안 고정된다.** 응답 소요 시간이 평가 항목이라
요청마다 후보를 재탐색하면 안 되기 때문이다. `CLOVASTUDIO_MODEL`로 고정할 수도 있다.

호출부는 `chat()` / `chat_json()` 두 함수만 노출한다. 과제 자료에 "필수 LLM 활용
기준 추후 공지 예정"이라고 되어 있어 모델 교체 가능성을 열어둔 구조다.

## 데이터 확보 후 해야 할 일

1. `.ttl`의 `fp:sourceColumn`을 실제 schema 엑셀의 컬럼명과 대조해 보정
2. `src/ingest/`에 xlsx → DuckDB 적재기 작성
3. `src/kb/registry.py`의 `_load_products()`를 DuckDB 조회로 교체 — 가드는 무수정
4. `src/agent/pipeline.py`의 `_KB_READY`를 True로 전환하고 Retrieval 연결
