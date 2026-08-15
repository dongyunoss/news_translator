"""엔티티 레지스트리 — 질의에 나온 이름·값을 KB의 실체와 대조한다.

지금은 기존 프로젝트의 `app/data/*.json`을 시드로 쓴다. 주최 측 마스터
4종(국내채권·국내ETF·해외ETF·공모펀드)이 확보되면 `_load_products()`만
DuckDB 조회로 바꾸면 되고, 이 모듈을 쓰는 가드·라우터는 손대지 않는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "app" / "data"

# --- 국내 신용등급 체계 -------------------------------------------------------
# 회사채·금융채 장기등급과 기업어음(CP) 단기등급. 이 집합 밖의 값은 존재하지 않는다.
LONG_TERM_RATINGS = {
    "AAA",
    "AA+", "AA0", "AA", "AA-",
    "A+", "A0", "A", "A-",
    "BBB+", "BBB0", "BBB", "BBB-",
    "BB+", "BB0", "BB", "BB-",
    "B+", "B0", "B", "B-",
    "CCC+", "CCC0", "CCC", "CCC-",
    "CC", "C", "D",
}
SHORT_TERM_RATINGS = {"A1", "A2+", "A2", "A2-", "A3+", "A3", "A3-", "B+", "B", "B-", "C", "D"}
ALL_RATINGS = LONG_TERM_RATINGS | SHORT_TERM_RATINGS

# --- ETF 브랜드(운용사 상품 접두어) -------------------------------------------
# 질의에 이 토큰이 있으면 "특정 상품명을 지목한 질의"로 본다.
ETF_BRANDS = {
    "KODEX", "TIGER", "ACE", "SOL", "PLUS", "RISE", "HANARO", "ARIRANG",
    "KOSEF", "KBSTAR", "KINDEX", "TIMEFOLIO", "WOORI", "HK", "UNICORN",
    "SPDR", "ISHARES", "VANGUARD", "INVESCO", "SCHWAB", "JPMORGAN",
}

# 금융 도메인에서 흔히 쓰이는 라틴 약어 — 미해결 엔티티로 오인하면 안 된다.
FINANCE_TOKENS = {
    "ETF", "ETN", "ETP", "AUM", "TER", "YTM", "MMF", "ISIN", "IRP", "ISA",
    "ESG", "REIT", "REITS", "NAV", "OCF", "CP", "MBS", "ABS", "TR", "PR",
    "KOSPI", "KOSDAQ", "KRX", "MSCI", "NASDAQ", "NYSE", "AMEX", "FTSE",
    "SNP", "SP", "DAX", "NIKKEI", "YTD", "CAGR", "USD", "KRW", "EUR", "JPY",
    "CNY", "HKD", "AI", "IT", "ROE", "PER", "PBR", "EPS", "BPS", "GDP", "CPI",
    "FOMC", "FED", "ECB", "BOK", "OTC", "IPO", "M&A", "LP", "AP", "CU",
}


@dataclass(frozen=True)
class Match:
    """이름 대조 결과."""

    name: str
    code: str
    score: float


def _normalize(text: str) -> str:
    """비교용 정규화 — 공백·구분기호를 지우고 대문자로 맞춘다."""
    return re.sub(r"[\s\-_·,./()]+", "", text).upper()


@lru_cache(maxsize=1)
def _load_products() -> list[dict]:
    """상품 마스터. 마스터 데이터 확보 시 이 함수만 교체한다."""
    path = _SEED_DIR / "products.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        {"code": p["code"], "name": p["name"], "type": p.get("type", "")}
        for p in data.get("products", [])
    ]


@lru_cache(maxsize=1)
def _load_glossary_terms() -> frozenset[str]:
    """용어사전 표제어 — 질의에 나와도 미지의 엔티티가 아니다."""
    path = _SEED_DIR / "glossary.json"
    if not path.is_file():
        return frozenset()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else data.get("terms", [])

    terms: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for key in ("term", "word"):
            if entry.get(key):
                terms.add(_normalize(entry[key]))
        for alias in entry.get("variants", []) + entry.get("aliases", []):
            terms.add(_normalize(alias))
    terms.discard("")
    return frozenset(terms)


def is_valid_rating(token: str) -> bool:
    return token.upper() in ALL_RATINGS


def is_known_token(token: str) -> bool:
    """라틴 토큰이 금융 도메인에서 아는 말인지."""
    upper = token.upper()
    return (
        upper in FINANCE_TOKENS
        or upper in ETF_BRANDS
        or upper in ALL_RATINGS
        or _normalize(token) in _load_glossary_terms()
    )


def resolve_product(name: str, *, limit: int = 3) -> list[Match]:
    """상품명을 마스터와 대조해 유사도 순으로 돌려준다 (0.0 ~ 1.0)."""
    target = _normalize(name)
    if not target:
        return []

    scored: list[Match] = []
    for product in _load_products():
        candidate = _normalize(product["name"])
        if not candidate:
            continue
        # 부분 포함은 확실한 신호이므로 문자열 유사도보다 우선한다.
        if target == candidate:
            score = 1.0
        elif target in candidate or candidate in target:
            score = 0.9
        else:
            score = SequenceMatcher(None, target, candidate).ratio()
        scored.append(Match(name=product["name"], code=product["code"], score=score))

    scored.sort(key=lambda m: -m.score)
    return scored[:limit]


def product_count() -> int:
    return len(_load_products())
