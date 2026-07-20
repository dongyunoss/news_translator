"""종목 데이터: 종목/섹터 매칭, 시세·차트 데이터 제공.

시세는 야후 파이낸스 공개 차트 API를 짧은 타임아웃으로 시도하고,
실패하면 종목 코드로 시드된 결정적 모의(random walk) 데이터로 폴백한다.
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import requests

_DATA = json.loads((Path(__file__).parent / "data" / "stocks.json").read_text(encoding="utf-8"))

STOCKS: dict[str, dict] = {s["code"]: s for s in _DATA["stocks"]}
SECTORS: dict[str, list[str]] = {}
for s in _DATA["stocks"]:
    SECTORS.setdefault(s["sector"], []).append(s["code"])

# 별칭 → 코드 (긴 별칭 우선 매칭)
_ALIASES: list[tuple[str, str]] = sorted(
    ((alias, s["code"]) for s in _DATA["stocks"] for alias in s["aliases"]),
    key=lambda x: -len(x[0]),
)

# 섹터 키워드 → 섹터명 (긴 키워드 우선)
_SECTOR_KEYWORDS: list[tuple[str, str]] = sorted(
    ((kw, name) for name, info in _DATA["sectors"].items() for kw in info["keywords"]),
    key=lambda x: -len(x[0]),
)

_CODE_RE = re.compile(r"\b(\d{6})\b")

CHART_RANGES = {"1m": 22, "3m": 66, "6m": 130, "1y": 260}


def analyze_sentence(sentence: str) -> tuple[list[dict], list[dict]]:
    """문장에서 직접 언급된 종목(mentions)과 관련 종목(related)을 찾는다."""
    mentions: list[dict] = []
    seen: set[str] = set()

    for alias, code in _ALIASES:
        if code not in seen and alias in sentence:
            seen.add(code)
            mentions.append({"code": code, "name": STOCKS[code]["name"], "text": alias})

    for m in _CODE_RE.finditer(sentence):
        code = m.group(1)
        if code in STOCKS and code not in seen:
            seen.add(code)
            mentions.append({"code": code, "name": STOCKS[code]["name"], "text": code})

    related: list[dict] = [
        {"code": m["code"], "name": m["name"], "reason": "기사에 직접 언급"} for m in mentions
    ]
    matched_sectors: set[str] = set()
    for kw, sector in _SECTOR_KEYWORDS:
        if sector not in matched_sectors and kw in sentence:
            matched_sectors.add(sector)
            for code in SECTORS.get(sector, [])[:4]:
                if code not in seen:
                    seen.add(code)
                    related.append(
                        {"code": code, "name": STOCKS[code]["name"], "reason": f"{sector} 관련주"}
                    )

    return mentions, related[:6]


# ---------------------------------------------------------------------------
# 가격 데이터
# ---------------------------------------------------------------------------

_series_lock = threading.Lock()
_mock_cache: dict[str, list[dict]] = {}
_live_cache: dict[str, tuple[float, list[dict] | None]] = {}
_LIVE_TTL_OK = 300.0
_LIVE_TTL_FAIL = 120.0


def _business_days(n: int) -> list[date]:
    days: list[date] = []
    d = date.today()
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


def _mock_series(code: str) -> list[dict]:
    """코드로 시드된 결정적 일봉 시계열(260 영업일)."""
    with _series_lock:
        if code in _mock_cache:
            return _mock_cache[code]

    info = STOCKS[code]
    rng = random.Random(f"{code}-krx")
    days = _business_days(260)
    price = info["base_price"] * rng.uniform(0.75, 0.95)
    base_vol = rng.randint(150_000, 4_000_000)
    out: list[dict] = []
    for d in days:
        drift = rng.gauss(0.0007, 0.021)
        o = price * (1 + rng.gauss(0, 0.006))
        c = price * (1 + drift)
        hi = max(o, c) * (1 + abs(rng.gauss(0, 0.008)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, 0.008)))
        vol = int(base_vol * rng.uniform(0.4, 2.4))
        out.append(
            {
                "date": d.isoformat(),
                "open": round(o),
                "high": round(hi),
                "low": round(lo),
                "close": round(c),
                "volume": vol,
            }
        )
        price = c

    with _series_lock:
        _mock_cache[code] = out
    return out


def _live_series(code: str) -> list[dict] | None:
    """야후 파이낸스 일봉 조회. 실패 시 None (결과는 캐시)."""
    now = time.time()
    with _series_lock:
        hit = _live_cache.get(code)
        if hit is not None:
            ts, series = hit
            ttl = _LIVE_TTL_OK if series is not None else _LIVE_TTL_FAIL
            if now - ts < ttl:
                return series

    suffix = ".KQ" if STOCKS[code]["market"] == "KOSDAQ" else ".KS"
    series: list[dict] | None = None
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{code}{suffix}",
            params={"range": "1y", "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=(2, 4),
        )
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        ts_list = result["timestamp"]
        q = result["indicators"]["quote"][0]
        parsed = []
        for i, ts in enumerate(ts_list):
            if q["close"][i] is None:
                continue
            parsed.append(
                {
                    "date": date.fromtimestamp(ts).isoformat(),
                    "open": round(q["open"][i] or q["close"][i]),
                    "high": round(q["high"][i] or q["close"][i]),
                    "low": round(q["low"][i] or q["close"][i]),
                    "close": round(q["close"][i]),
                    "volume": int(q["volume"][i] or 0),
                }
            )
        if len(parsed) >= 30:
            series = parsed
    except Exception:
        series = None

    with _series_lock:
        _live_cache[code] = (now, series)
    return series


def _get_series(code: str) -> tuple[list[dict], str]:
    live = _live_series(code)
    if live is not None:
        return live, "live"
    return _mock_series(code), "mock"


def get_quote(code: str) -> dict | None:
    if code not in STOCKS:
        return None
    series, source = _get_series(code)
    last, prev = series[-1], series[-2]
    change = last["close"] - prev["close"]
    info = STOCKS[code]
    return {
        "code": code,
        "name": info["name"],
        "market": info["market"],
        "sector": info["sector"],
        "price": last["close"],
        "change": change,
        "change_pct": round(change / prev["close"] * 100, 2),
        "volume": last["volume"],
        "spark": [c["close"] for c in series[-30:]],
        "source": source,
        "currency": "KRW",
    }


def get_chart(code: str, rng: str = "3m") -> dict | None:
    if code not in STOCKS:
        return None
    n = CHART_RANGES.get(rng, CHART_RANGES["3m"])
    series, source = _get_series(code)
    info = STOCKS[code]
    return {
        "code": code,
        "name": info["name"],
        "market": info["market"],
        "sector": info["sector"],
        "range": rng,
        "candles": series[-n:],
        "source": source,
    }
