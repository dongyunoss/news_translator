"""Intent 라우터 — 질의를 검색 모드로 분류한다.

과제 평가 예시를 보면 필요한 검색 방식이 뚜렷하게 갈린다.

    SQL     수치 조건·정렬·집계          "AA- 이상 원화채권", "총보수 낮고 AUM 큰 3개"
    VECTOR  서술·전략·구조               "국민성장펀드의 구조와 투자전략 동향"
    GRAPH   편입·자회사·테마 연결 이력    "에코프로의 자회사를 편입한 ETF"
    HYBRID  관계 + 수치 조건이 함께

지금은 키워드 신호 기반이다. LLM 분류로 바꿀 수 있게 `classify()` 한 함수로 막아뒀지만,
라우팅에까지 LLM 호출을 넣으면 문항당 응답 시간이 두 배가 되므로 규칙으로 처리되는
질의는 규칙에서 끝내는 편이 낫다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 관계 탐색이 필요하다는 신호 — 마스터 컬럼만으로는 못 푸는 축이다.
GRAPH_SIGNALS = (
    "편입", "포함", "구성종목", "보유종목", "담은", "담긴",
    "자회사", "계열사", "모회사", "지분", "관계사",
    "테마", "연결", "이력", "관련", "엮인", "연관",
)

# 서술형 문서를 봐야 한다는 신호.
VECTOR_SIGNALS = (
    "구조", "전략", "동향", "특징", "설명", "개요", "방식", "성격",
    "위험요인", "리스크", "투자전략", "운용전략", "어떤", "무엇",
)

# 정형 연산이 필요하다는 신호.
SQL_SIGNALS = (
    "이상", "이하", "초과", "미만", "큰", "작은", "높은", "낮은",
    "상위", "하위", "가장", "최대", "최소", "평균", "합계",
    "비교", "순서", "정렬", "개만", "개를", "순위",
    "총보수", "순자산", "수익률", "규모", "듀레이션", "표면금리", "만기",
)


@dataclass
class Route:
    """분류 결과."""

    mode: str  # "SQL" | "VECTOR" | "GRAPH" | "HYBRID"
    signals: dict[str, list[str]] = field(default_factory=dict)

    def describe(self) -> str:
        """think_trace에 넣을 한 줄 설명."""
        hits = ", ".join(
            f"{kind}({'·'.join(words)})" for kind, words in self.signals.items() if words
        )
        return f"검색 모드 {self.mode}" + (f" ← {hits}" if hits else "")


def _hits(question: str, signals: tuple[str, ...]) -> list[str]:
    return [word for word in signals if word in question]


def classify(question: str) -> Route:
    question = question or ""
    graph = _hits(question, GRAPH_SIGNALS)
    vector = _hits(question, VECTOR_SIGNALS)
    sql = _hits(question, SQL_SIGNALS)

    signals = {"GRAPH": graph, "VECTOR": vector, "SQL": sql}
    active = [kind for kind, words in signals.items() if words]

    if len(active) > 1:
        mode = "HYBRID"
    elif active:
        mode = active[0]
    else:
        # 신호가 없으면 단순 조회로 보고 정형 검색에 맡긴다.
        mode = "SQL"

    return Route(mode=mode, signals=signals)
