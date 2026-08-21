"""과제 자료(12p)의 평가 질의 예시로 가드와 라우터를 검증한다.

답변 가능한 질의가 가드에 걸리는 오탐은 감점 이전에 정답 기회를 통째로 날리므로,
'걸리면 안 되는' 케이스를 함께 고정해 둔다.
"""

import pytest

from src.agent import guards, router
from src.agent.pipeline import answer_question

# 데이터로 확인할 수 없는 질의 — 답변을 생성하면 감점
UNANSWERABLE = [
    ("신용등급 AAAA인 채권 찾아줘", "G1"),
    ("Kimi 관련 투자 상품 있어?", "G2"),
    ("KODEX AI로봇 ETF 정보 알려줘", "G3"),
]

# 답변 가능한 질의 — 가드가 걸리면 안 된다
ANSWERABLE = [
    "현재 판매 가능한 원화채권 중 AA- 이상 종목 알려줘",
    "국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘",
    "캠브리콘이 편입된 중국 반도체 ETF를 알려줘",
    "최근 6개월 동안 우주항공 테마와 연결 이력이 있는 관련 ETF를 정리해줘",
    "에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품의 위험요인 알려줘",
    "미국 증시에 상장된 주식형 ETF 중에서 총보수가 낮고 운용 규모가 큰 상품 3개만 비교해 주세요.",
]


@pytest.mark.parametrize("question,expected", UNANSWERABLE)
def test_unanswerable_is_blocked(question, expected):
    result = guards.check(question)
    assert result is not None, f"가드가 걸리지 않음: {question}"
    assert result.guard == expected
    assert "확인할 수 없" in result.answer


@pytest.mark.parametrize("question", ANSWERABLE)
def test_answerable_passes_guards(question):
    result = guards.check(question)
    assert result is None, f"오탐 — {result.guard if result else ''}: {question}"


@pytest.mark.parametrize(
    "question",
    [
        # 브랜드는 나오지만 특정 상품을 지목하지 않은 목록형 질의
        "KODEX ETF 중에 뭐가 있어?",
        "KODEX 상품 목록 알려줘",
        # 실재하는 상품명
        "KODEX 200 알려줘",
        "TIGER 미국S&P500의 총보수는?",
        "KODEX 반도체와 TIGER 미국나스닥100 비교해줘",
    ],
)
def test_brand_queries_not_falsely_blocked(question):
    result = guards.check(question)
    assert result is None, f"오탐 — {result.guard if result else ''}: {question}"


def test_nonexistent_branded_product_blocked():
    result = guards.check("TIGER 우주여행테크 ETF 알려줘")
    assert result is not None and result.guard == "G3"
    # 상품명만 남고 "ETF 알려줘" 같은 꼬리말은 떨어져야 한다
    assert "TIGER 우주여행테크" in result.answer
    assert "알려줘" not in result.answer.split("는 확인할 수 없")[0]


def test_valid_rating_not_blocked():
    for grade in ("AAA", "AA+", "AA-", "BBB-", "A1", "A2+"):
        assert guards.check(f"신용등급 {grade} 이상 채권 알려줘") is None


def test_invalid_rating_blocked():
    for grade in ("AAAA", "AAB", "EEE", "AA++", "BBBB"):
        result = guards.check(f"신용등급 {grade}인 채권 찾아줘")
        assert result is not None and result.guard == "G1", grade


# --- 예시에 없는 질의로 일반화를 검증한다 -------------------------------------
# 과제 자료의 예시 3건에 맞춘 규칙은 못 본 27문항에 듣지 않는다. 아래는 예시에
# 등장하지 않는 유형으로, 판정이 온톨로지에서 나오는지를 확인한다.

GENERALIZED_UNANSWERABLE = [
    # 상품군에 그 컬럼 자체가 없는 경우 (공모펀드마스터는 보수 정보 미포함)
    ("공모펀드 중 총보수가 가장 낮은 상품 3개 알려줘", "G4"),
    ("펀드 선취수수료 낮은 순으로 정리해줘", "G4"),
    # 값 체계 밖의 값 — 등급 문자열과 숫자형 표기 양쪽
    ("위험등급 9등급인 ETF 찾아줘", "G1"),
    ("위험등급 0등급 펀드", "G1"),
    ("신용등급 EEE인 회사채 알려줘", "G1"),
]

GENERALIZED_ANSWERABLE = [
    "해외 ETF 중 총보수가 가장 낮은 상품 3개",
    "국내 ETF 중 순자산이 큰 상품",
    "위험등급 1등급인 ETF 찾아줘",
    "위험등급 6등급 채권형 펀드",
    "신용등급 BBB- 이상 회사채 알려줘",
    "신용등급 A1 단기물 알려줘",
    "공모펀드 중 순자산이 큰 상품 알려줘",
    "환헤지된 미국 주식형 펀드 알려줘",
    "듀레이션이 짧은 국채 알려줘",
    "NASDAQ에 상장된 ETF 중 AUM 큰 것",
]


@pytest.mark.parametrize("question,expected", GENERALIZED_UNANSWERABLE)
def test_generalized_unanswerable(question, expected):
    result = guards.check(question)
    assert result is not None, f"가드가 걸리지 않음: {question}"
    assert result.guard == expected
    assert "확인할 수 없" in result.answer


@pytest.mark.parametrize("question", GENERALIZED_ANSWERABLE)
def test_generalized_answerable(question):
    result = guards.check(question)
    assert result is None, f"오탐 — {result.guard if result else ''}: {question}"


def test_coverage_guard_names_an_alternative_product_group():
    """확인 불가로 끝내지 말고 조회 가능한 상품군을 역질문한다."""
    result = guards.check("공모펀드 중 총보수가 낮은 상품")
    assert result is not None and result.guard == "G4"
    assert "해외 ETF" in result.answer
    assert "PRFD01N001" in result.context


@pytest.mark.parametrize(
    "question,mode",
    [
        ("현재 판매 가능한 원화채권 중 AA- 이상 종목 알려줘", "SQL"),
        ("국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘", "VECTOR"),
        ("캠브리콘이 편입된 중국 반도체 ETF를 알려줘", "GRAPH"),
        ("최근 6개월 동안 우주항공 테마와 연결 이력이 있는 관련 ETF를 정리해줘", "GRAPH"),
        ("에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품의 위험요인 알려줘", "HYBRID"),
    ],
)
def test_router_modes(question, mode):
    assert router.classify(question).mode == mode


def test_response_schema_is_fixed():
    """확인 불가든 아니든 필드 5개가 항상 있어야 한다."""
    fields = {"question_id", "question", "retrieved_context", "think_trace", "answer"}
    for question in [q for q, _ in UNANSWERABLE] + ANSWERABLE + ["", "?!@#"]:
        body = answer_question("Q-001", question)
        assert set(body) == fields
        assert all(isinstance(v, str) for v in body.values())
        assert body["question_id"] == "Q-001"
