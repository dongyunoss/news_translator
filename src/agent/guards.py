"""답변 불가 가드 — Retrieval 이전에 '확인할 수 없음'을 판정한다.

평가 30문항 중 5문항이 데이터로 확인할 수 없는 질의이고, 여기에 답변을 생성하면
감점된다. '확인할 수 없음' 명시 또는 필요한 조건 역질문이 정답 처리다.

가드를 검색·생성보다 **앞에** 두는 이유는 두 가지다. 환각이 LLM에 도달하기 전에
차단되고, 불필요한 검색·생성을 건너뛰어 응답 시간(평가 항목)도 아낀다.

과제 자료의 답변 불가 예시 3건은 서로 다른 실패 유형이라 가드도 3종으로 나눴다.

    G1  신용등급 AAAA인 채권 찾아줘      → 값 도메인 위반
    G2  Kimi 관련 투자 상품 있어?        → 엔티티 미해결
    G3  KODEX AI로봇 ETF 정보 알려줘     → 상품명 근사매칭 실패

오탐(답변 가능한 질의를 막는 것)이 미탐보다 비싸므로 판정은 보수적으로 잡았다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..kb import registry

# 신용등급 모양의 토큰. 한글 조사가 붙은 "AAAA인"도 잡히도록 뒤쪽은 라틴 문자만 배제한다.
# A~D는 한 글자짜리 등급(A, C, D)이 실재하므로 길이 1부터 본다.
_RATING_RE = re.compile(r"(?<![A-Za-z0-9])([A-D]{1,5})((?:[+-]|0|[1-3][+-]?)?)(?![A-Za-z])")
# 등급 자리에 A~D 밖의 글자가 온 경우("EEE 등급")까지 같은 사유로 잡기 위한 넓은 패턴.
# 단, ETF·MSCI 같은 금융 약어를 등급으로 오인하면 안 되므로 호출부에서 걸러낸다.
_RATING_LIKE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,5})((?:[+-]|0|[1-3][+-]?)?)(?![A-Za-z])")

# 등급을 묻는 맥락인지 판별. 이 말이 없으면 G1은 동작하지 않는다.
_RATING_CONTEXT = ("신용등급", "등급", "신용도", "레이팅", "rating")

# 라틴 문자로 된 고유명사 후보.
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&.]{1,}")

# 브랜드 접두어 + 뒤따르는 상품명 조각.
_BRAND_NAME_RE = re.compile(
    r"(" + "|".join(sorted(registry.ETF_BRANDS, key=len, reverse=True)) + r")"
    r"((?:\s+[0-9A-Za-z가-힣&.]+){0,4})",
    re.IGNORECASE,
)

# 여기서부터는 상품명이 아니라 질문 문장이다 — 이름 수집을 끊는다.
# "KODEX ETF 중에 뭐가 있어?" 같은 목록형 질의를 특정 상품 지목으로 오인하지 않기 위함.
_NAME_STOP = {
    "중", "중에", "중에서", "가운데", "뭐", "뭐가", "무엇", "무슨", "어떤", "어느",
    "등", "등의", "같은", "관련", "종류", "상품", "목록", "리스트", "몇", "전부", "모두",
}

# 상품명 뒤에 흔히 붙는 말 — 이름의 일부가 아니므로 잘라낸다.
# "AI로봇 ETF 정보 알려줘"처럼 여러 개가 겹쳐 붙으므로 더 줄지 않을 때까지 반복 적용한다.
_NAME_TAIL = re.compile(
    r"\s*(ETF|ETN|펀드|정보|알려줘|가르쳐줘|찾아줘|알려|조회|설명|어때|어떤|있어|있나|"
    r"은|는|이|가|의|을|를|에|와|과)\s*$"
)

# 상품명 근사매칭 임계치. 이 아래면 "그 상품은 없다"로 본다.
PRODUCT_MATCH_THRESHOLD = 0.72
# 유사 상품을 역질문으로 제안할 최소 점수.
SUGGEST_THRESHOLD = 0.45


@dataclass
class GuardResult:
    """가드가 걸렸을 때의 응답 재료."""

    guard: str  # "G1" | "G2" | "G3"
    reason: str  # think_trace에 남길 내부 판정 사유
    answer: str  # 사용자에게 보일 답변
    context: str  # retrieved_context에 표시할 참조 근거


def _check_rating_domain(question: str) -> GuardResult | None:
    """G1 — 질의 속 등급 값이 국내 신용등급 체계에 존재하는가."""
    if not any(word in question for word in _RATING_CONTEXT):
        return None

    for pattern in (_RATING_RE, _RATING_LIKE_RE):
        for match in pattern.finditer(question):
            letters, suffix = match.group(1), match.group(2) or ""
            token = letters + suffix
            if registry.is_valid_rating(token) or registry.is_known_token(letters):
                continue
            return _rating_domain_error(token)
    return None


def _rating_domain_error(token: str) -> GuardResult:
    return GuardResult(
        guard="G1",
        reason=f"등급 값 '{token}'이(가) 국내 신용등급 체계에 없음",
        answer=(
            f"'{token}' 등급은 확인할 수 없습니다. "
            "국내 신용등급 체계에 존재하지 않는 값입니다.\n"
            "장기등급은 AAA부터 D까지(AAA, AA+, AA0, AA-, A+ …), "
            "단기등급은 A1부터 D까지 사용합니다. "
            "찾으시는 등급을 다시 알려주시면 조회해 드리겠습니다."
        ),
        context="국내채권마스터(PRBD01N001) · 신용등급 도메인 검증",
    )
    return None


def _check_unresolved_entity(question: str) -> GuardResult | None:
    """G2 — 질의의 라틴 고유명사가 KB의 어떤 엔티티에도 매핑되지 않는가.

    한글 고유명사는 실제 마스터가 붙기 전까지 판정하지 않는다. 지금 단계에서
    한글까지 검사하면 답변 가능한 질의를 막을 위험이 크다.
    """
    for token in _LATIN_TOKEN_RE.findall(question):
        if len(token) < 2 or registry.is_known_token(token):
            continue
        if registry.resolve_product(token) and registry.resolve_product(token)[0].score >= PRODUCT_MATCH_THRESHOLD:
            continue
        return GuardResult(
            guard="G2",
            reason=f"고유명사 '{token}'이(가) 상품·기업·테마 인덱스에서 해결되지 않음",
            answer=(
                f"'{token}'에 대한 정보는 확인할 수 없습니다. "
                "보유한 금융상품 데이터에서 해당 이름의 상품·기업·지수를 찾지 못했습니다.\n"
                "정확한 상품명이나 종목명을 알려주시면 다시 조회해 드리겠습니다."
            ),
            context="국내채권 · 국내ETF · 해외ETF · 공모펀드 마스터 · 엔티티 인덱스 조회 결과 없음",
        )
    return None


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
    """G3 — 브랜드까지 지목한 상품명이 마스터에 실제로 있는가."""
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
        answer=f"'{candidate}'는 확인할 수 없습니다. 해당 이름의 상품이 마스터 데이터에 없습니다.{followup}",
        context="국내ETF마스터(PREF01N001) · 해외ETF마스터(PREF02N001) · 상품명 인덱스",
    )


_GUARDS = (_check_rating_domain, _check_unresolved_entity, _check_product_name)


def check(question: str) -> GuardResult | None:
    """세 가드를 순서대로 돌린다. 하나라도 걸리면 즉시 반환한다."""
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
