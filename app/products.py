"""금융상품(ETF·펀드·채권) 데이터: 테마 키워드 → 관련 상품 매칭.

종목 매칭(stocks.py)과 같은 방식으로, 문장 속 테마 키워드를 보고
그 테마에 어울리는 금융상품을 이유와 함께 돌려준다.
추천이 아니라 참고 정보 제공이 목적이다.
"""

from __future__ import annotations

import json
from pathlib import Path

_DATA = json.loads(
    (Path(__file__).parent / "data" / "products.json").read_text(encoding="utf-8")
)

PRODUCTS: dict[str, dict] = {p["code"]: p for p in _DATA["products"]}

# (키워드, 테마명) — 긴 키워드 우선 매칭
_THEME_KEYWORDS: list[tuple[str, str]] = sorted(
    ((kw, name) for name, info in _DATA["themes"].items() for kw in info["keywords"]),
    key=lambda x: -len(x[0]),
)

MAX_PER_SENTENCE = 4


def match_sentence(sentence: str) -> list[dict]:
    """문장에서 테마 키워드를 찾아 관련 금융상품 목록을 만든다 (상품당 1회)."""
    out: list[dict] = []
    seen_codes: set[str] = set()
    seen_themes: set[str] = set()

    for kw, theme in _THEME_KEYWORDS:
        if theme in seen_themes or kw not in sentence:
            continue
        seen_themes.add(theme)
        for entry in _DATA["themes"][theme]["products"]:
            code = entry["code"]
            if code in seen_codes or code not in PRODUCTS:
                continue
            seen_codes.add(code)
            p = PRODUCTS[code]
            out.append(
                {
                    "code": code,
                    "name": p["name"],
                    "type": p["type"],
                    "asset": p["asset"],
                    "expense": p["expense"],
                    "risk": p["risk"],
                    "desc": p["desc"],
                    "theme": theme,
                    "reason": entry["reason"],
                }
            )
            if len(out) >= MAX_PER_SENTENCE:
                return out
    return out
