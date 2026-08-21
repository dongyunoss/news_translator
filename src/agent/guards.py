"""답변 불가 가드 — Retrieval 이전에 '확인할 수 없음'을 판정한다.

평가 30문항 중 5문항이 데이터로 확인할 수 없는 질의이고, 여기에 답변을 생성하면
감점된다. '확인할 수 없음' 명시 또는 필요한 조건 역질문이 정답 처리다.

가드를 검색·생성보다 **앞에** 두는 이유는 두 가지다. 환각이 LLM에 도달하기 전에
차단되고, 불필요한 검색·생성을 건너뛰어 응답 시간(평가 항목)도 아낀다.

판정 근거는 모두 `ontology/*.ttl`에서 나온다. 과제 자료의 답변 불가 예시 3건에
맞춘 규칙을 쓰면 못 본 질의에는 듣지 않으므로, 예시가 아니라 데이터 정의에서
판정을 끌어낸다.

    G1  값 도메인 위반    열거형 속성의 값이 그 속성의 값 체계에 없음
    G2  엔티티 미해결      고유명사가 어떤 인덱스에도 매핑되지 않음
    G3  상품명 미존재      브랜드까지 지목한 이름이 마스터에 없음
    G4  속성 미수록        질의가 요구하는 속성이 그 상품군에 수록되지 않음

오탐(답변 가능한 질의를 막는 것)이 미탐보다 비싸므로 판정은 보수적으로 잡았다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..kb import ontology, registry
from ..korean import josa, quoted

# 라틴 문자로 된 고유명사·코드 후보.
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&.]{1,}")

# 등급 표기 덩어리. 부호가 몇 개 붙든 통째로 잡아야 "AA++"처럼 한 글자만 더 붙은
# 값이 유효한 "AA+"로 잘려 통과하는 일이 없다.
_CODE_RUN_RE = re.compile(r"(?<![A-Za-z0-9+\-])([A-Z][A-Z0-9+\-]{1,7})(?![A-Za-z0-9+\-])")

# 브랜드 접두어 + 뒤따르는 상품명 조각.
_BRAND_NAME_RE = re.compile(
    r"(" + "|".join(sorted(registry.ETF_BRANDS, key=len, reverse=True)) + r")"
    r"((?:\s+[0-9A-Za-z가-힣&.]+){0,4})",
    re.IGNORECASE,
)

# 여기서부터는 상품명이 아니라 질문 문장이다 — 이름 수집을 끊는다.
_NAME_STOP = {
    "중", "중에", "중에서", "가운데", "뭐", "뭐가", "무엇", "무슨", "어떤", "어느",
    "등", "등의", "같은", "관련", "종류", "상품", "목록", "리스트", "몇", "전부", "모두",
}

# 상품명 뒤에 흔히 붙는 말. 더 줄지 않을 때까지 반복 적용한다.
_NAME_TAIL = re.compile(
    r"\s*(ETF|ETN|펀드|정보|알려줘|가르쳐줘|찾아줘|알려|조회|설명|어때|어떤|있어|있나|"
    r"은|는|이|가|의|을|를|에|와|과)\s*$"
)

# 상품명 근사매칭 임계치. 이 아래면 "그 상품은 없다"로 본다.
PRODUCT_MATCH_THRESHOLD = 0.72
SUGGEST_THRESHOLD = 0.45


@dataclass
class GuardResult:
    """가드가 걸렸을 때의 응답 재료."""

    guard: str  # "G0" ~ "G4"
    reason: str  # think_trace에 남길 내부 판정 사유
    answer: str  # 사용자에게 보일 답변
    context: str  # retrieved_context에 표시할 참조 근거


# =============================================================================
# G1 — 값 도메인 위반
# =============================================================================


def _check_value_domain(question: str) -> GuardResult | None:
    """질의가 지정한 값이 그 속성의 값 체계에 존재하는가.

    온톨로지에서 열거형 속성(rdfs:range가 개념 클래스인 속성)과 허용값을 읽어
    검사한다. 신용등급뿐 아니라 위험등급·상장시장·거래통화·채권종류 등 모든
    열거형에 같은 규칙이 적용된다.

    검사 대상은 두 가지다.

      1. 등급 표기 덩어리   "AAAA", "AA++", "EEE"
      2. 허용값의 숫자 자리를 바꾼 표기   "9등급" (허용값이 1~6등급일 때)

    2번의 패턴은 허용값 라벨에서 자동으로 만들어진다. "1등급"에서 `\\d+등급`을
    유도하는 식이라, 값 체계가 바뀌어도 규칙을 다시 쓸 필요가 없다.

    그 밖의 한글 값은 검사하지 않는다. 표기 변형이 많아 오탐 위험이 크고,
    실제 마스터의 값 분포를 본 뒤에 넓히는 편이 안전하다.
    """
    mentioned = ontology.enum_properties_mentioned(question)
    if not mentioned:
        return None

    # 언급된 열거형들의 허용값을 합친다. 질의가 어느 속성을 가리키는지 모호할 때
    # (예: "등급"이 신용등급인지 위험등급인지) 어느 한쪽에만 있어도 통과시킨다.
    allowed: set[str] = set()
    labels: list[str] = []
    for prop, concepts in mentioned:
        labels.append(prop.label)
        for concept in concepts:
            allowed.add(concept.label.upper())
            allowed.update(alias.upper() for alias in concept.aliases)

    offenders = [
        match.group(1)
        for match in _CODE_RUN_RE.finditer(question)
        if not registry.is_known_token(match.group(1))
    ]
    offenders += _shape_violations(question, allowed)

    for token in offenders:
        upper = token.upper()
        if upper in allowed or ontology.is_known_value(upper):
            continue  # 다른 체계의 값이면 이 속성의 위반으로 보지 않는다

        return GuardResult(
            guard="G1",
            reason=f"{quoted(token, '이/가')} {labels[0]} 값 체계에 없음",
            answer=(
                f"{quoted(token, '은/는')} 확인할 수 없습니다. "
                f"{labels[0]}에 존재하지 않는 값입니다.\n{_describe_domain(mentioned)}\n"
                "찾으시는 값을 다시 알려주시면 조회해 드리겠습니다."
            ),
            context=_context_of(mentioned) + " · 값 도메인 검증",
        )
    return None


def _shape_violations(question: str, allowed: set[str]) -> list[str]:
    """허용값의 숫자 자리만 다른 표기를 찾는다.

    허용값 "1등급"에서 패턴 `\\d+등급`을 만들고, 질의에서 그 모양에 맞지만
    허용값 목록에는 없는 문자열을 골라낸다. 값 체계를 코드에 적지 않고
    온톨로지에서 그때그때 유도하므로 새 열거형에도 그대로 적용된다.
    """
    shapes: set[str] = set()
    for value in allowed:
        if not any(ch.isdigit() for ch in value):
            continue
        shape = re.sub(r"\d+", r"\\d+", re.escape(value))
        shapes.add(shape)

    found: list[str] = []
    for shape in shapes:
        for match in re.finditer(shape, question, re.IGNORECASE):
            token = match.group(0)
            if token.upper() not in allowed:
                found.append(token)
    return found


def _describe_domain(mentioned) -> str:
    """허용값을 사용자에게 보여줄 한 줄로 요약한다."""
    lines = []
    for prop, concepts in mentioned[:2]:
        sample = [c.label for c in concepts]
        shown = ", ".join(sample[:8])
        more = f" 외 {len(sample) - 8}개" if len(sample) > 8 else ""
        lines.append(f"{josa(prop.label, '은/는')} {josa(shown + more, '을/를')} 사용합니다.")
    return "\n".join(lines)


def _context_of(mentioned) -> str:
    sources = []
    for prop, _ in mentioned:
        source = prop.source_label()
        if source not in sources:
            sources.append(source)
    return " · ".join(sources) if sources else "-"


# =============================================================================
# G2 — 엔티티 미해결
# =============================================================================


def _check_unresolved_entity(question: str) -> GuardResult | None:
    """질의의 라틴 고유명사가 KB의 어떤 엔티티에도 매핑되지 않는가.

    한글 고유명사는 실제 마스터가 붙기 전까지 판정하지 않는다. 지금 단계에서
    한글까지 검사하면 답변 가능한 질의를 막을 위험이 크다.
    """
    for token in _LATIN_TOKEN_RE.findall(question):
        if len(token) < 2 or registry.is_known_token(token):
            continue
        if ontology.is_known_value(token):
            continue
        matches = registry.resolve_product(token)
        if matches and matches[0].score >= PRODUCT_MATCH_THRESHOLD:
            continue
        return GuardResult(
            guard="G2",
            reason=f"고유명사 {quoted(token, '이/가')} 상품·기업·테마 인덱스에서 해결되지 않음",
            answer=(
                f"'{token}'에 대한 정보는 확인할 수 없습니다. "
                "보유한 금융상품 데이터에서 해당 이름의 상품·기업·지수를 찾지 못했습니다.\n"
                "정확한 상품명이나 종목명을 알려주시면 다시 조회해 드리겠습니다."
            ),
            context="국내채권 · 국내ETF · 해외ETF · 공모펀드 마스터 · 엔티티 인덱스 조회 결과 없음",
        )
    return None


# =============================================================================
# G3 — 상품명 미존재
# =============================================================================


def _extract_branded_name(question: str) -> str | None:
    """질의에서 브랜드 접두어로 시작하는 상품명 후보를 뽑는다."""
    match = _BRAND_NAME_RE.search(question)
    if not match:
        return None

    words: list[str] = []
    for word in match.group(2).split():
        if word in _NAME_STOP:
            break
        words.append(word)

    candidate = " ".join([match.group(1), *words]).strip()

    while True:
        trimmed = _NAME_TAIL.sub("", candidate).strip()
        if trimmed == candidate:
            break
        candidate = trimmed

    # 브랜드 이름만 남으면 특정 상품을 지목한 질의가 아니다.
    if candidate.upper() in registry.ETF_BRANDS:
        return None
    return candidate or None


def _check_product_name(question: str) -> GuardResult | None:
    """브랜드까지 지목한 상품명이 마스터에 실제로 있는가."""
    candidate = _extract_branded_name(question)
    if not candidate:
        return None

    matches = registry.resolve_product(candidate)
    if matches and matches[0].score >= PRODUCT_MATCH_THRESHOLD:
        return None

    suggestions = [m for m in matches if m.score >= SUGGEST_THRESHOLD]
    if suggestions:
        listed = ", ".join(f"{m.name}({m.code})" for m in suggestions)
        followup = f"\n혹시 다음 상품을 찾으셨나요? {listed}"
    else:
        followup = "\n정확한 상품명을 알려주시면 다시 조회해 드리겠습니다."

    best = matches[0].score if matches else 0.0
    return GuardResult(
        guard="G3",
        reason=f"상품명 '{candidate}' 최고 유사도 {best:.2f} < {PRODUCT_MATCH_THRESHOLD}",
        answer=(
            f"{quoted(candidate, '은/는')} 확인할 수 없습니다. "
            f"해당 이름의 상품이 마스터 데이터에 없습니다.{followup}"
        ),
        context="국내ETF마스터(PREF01N001) · 해외ETF마스터(PREF02N001) · 상품명 인덱스",
    )


# =============================================================================
# G4 — 속성 미수록
# =============================================================================


def _check_property_coverage(question: str) -> GuardResult | None:
    """질의가 요구하는 속성이 그 상품군에 수록되어 있는가.

    상품도 조건도 자연스럽지만 제공 데이터에는 그 컬럼이 없는 경우가 있다.
    공모펀드마스터의 보수 정보가 그렇다. 이런 질의는 검색해도 답이 나오지
    않으므로 온톨로지의 `fp:coverage "none"` 선언을 보고 미리 판정한다.

    상품군을 좁히지 못한 질의는 판정하지 않는다. "총보수 낮은 상품"처럼
    상품군이 불명확하면 해외 ETF로는 답할 수 있기 때문이다.
    """
    classes = ontology.classes_mentioned(question)
    if not classes:
        return None

    for name in ontology.names_mentioned(question):
        applicable = [
            (cls, prop)
            for cls in classes
            for prop in ontology.applicable_properties(name, cls)
        ]
        if not applicable:
            continue
        # 언급된 상품군 어디에서도 수록되지 않은 속성만 차단한다.
        if any(prop.coverage != "none" for _, prop in applicable):
            continue

        cls, prop = applicable[0]
        others = _available_elsewhere(name, exclude={c.uri for c in classes})
        followup = (
            f"\n{', '.join(others)}의 {josa(prop.label, '은/는')} 조회할 수 있습니다. "
            "해당 상품군으로 다시 물어봐 주세요."
            if others
            else ""
        )
        return GuardResult(
            guard="G4",
            reason=f"{cls.label}의 '{prop.label}' 미수록 (coverage=none)",
            answer=(
                f"{cls.label}의 {josa(prop.label, '은/는')} 확인할 수 없습니다. "
                f"제공된 {cls.table_label()}에 해당 정보가 수록되어 있지 않습니다.{followup}"
            ),
            context=f"{cls.table_label()} · {prop.label} 미수록",
        )
    return None


def _available_elsewhere(name: str, exclude: set[str]) -> list[str]:
    """같은 속성을 조회할 수 있는 다른 상품군 이름."""
    out = []
    for cls in ontology.product_classes().values():
        if cls.uri in exclude:
            continue
        props = ontology.applicable_properties(name, cls)
        if props and any(p.coverage in ("full", "partial") for p in props):
            out.append(cls.label)
    return out


# =============================================================================

_GUARDS = (
    _check_value_domain,
    _check_property_coverage,
    _check_product_name,
    _check_unresolved_entity,
)


def check(question: str) -> GuardResult | None:
    """가드를 순서대로 돌린다. 하나라도 걸리면 즉시 반환한다.

    순서는 판정의 구체성을 따른다. 값 도메인·속성 수록 여부처럼 온톨로지가
    확실히 아는 것을 먼저 보고, 추정이 섞이는 엔티티 해결을 마지막에 둔다.
    """
    question = (question or "").strip()
    if not question:
        return GuardResult(
            guard="G0",
            reason="질의가 비어 있음",
            answer="질문 내용을 확인할 수 없습니다. 찾으시는 상품이나 조건을 알려주세요.",
            context="-",
        )

    for guard in _GUARDS:
        result = guard(question)
        if result is not None:
            return result
    return None
