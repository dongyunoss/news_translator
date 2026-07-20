"""뉴스 기사를 주식 초보자('주린이') 눈높이의 쉬운 문장으로 번역한다.

Google Gemini API(gemini-1.5-flash)를 우선 사용하고,
API 키가 없거나 호출에 실패하면 내장 경제 용어사전 기반 주석 번역으로 폴백한다.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from . import stocks

GLOSSARY: list[dict] = json.loads(
    (Path(__file__).parent / "data" / "glossary.json").read_text(encoding="utf-8")
)

_TERM_INDEX: list[tuple[str, dict]] = sorted(
    ((v, entry) for entry in GLOSSARY for v in entry["variants"]),
    key=lambda x: -len(x[0]),
)

MAX_ARTICLE_CHARS = 8000

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")

_client = None
_client_lock = threading.Lock()
_gemini_disabled = False

_SYSTEM_PROMPT = """\
너는 주식을 처음 시작한 초보 투자자('주린이')를 위한 경제 뉴스 해설가야.
어려운 경제·주식 기사 문장을 받아서, 한 문장씩 쉬운 한국어로 풀어서 설명해.

규칙:
- 문장 개수와 순서를 입력과 똑같이 유지해. 문장을 합치거나 나누지 마.
- 전문 용어는 일상적인 말로 풀어 쓰되, 핵심 의미가 사라지면 안 돼.
- 친근한 해요체를 사용해. (예: "~라는 뜻이에요", "~하고 있어요")
- 각 문장의 쉬운 번역은 원문보다 크게 길어지지 않게 해.
- summary에는 기사 전체를 주린이가 이해할 수 있게 2~3문장으로 요약해.

응답은 반드시 다음 JSON 형식으로 해:
{
  "summary": "기사 요약",
  "sentences": [
    {"easy": "첫 번째 문장의 쉬운 번역"},
    {"easy": "두 번째 문장의 쉬운 번역"}
  ]
}"""


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p and p.strip()]


def find_terms(sentence: str) -> list[dict]:
    """문장에 등장하는 용어사전 항목을 찾는다 (항목당 1회)."""
    found: list[dict] = []
    seen_ids: set[int] = set()
    for variant, entry in _TERM_INDEX:
        if id(entry) in seen_ids:
            continue
        haystack = sentence
        for ex in entry.get("exclude", []):
            haystack = haystack.replace(ex, "")
        if variant in haystack:
            seen_ids.add(id(entry))
            found.append({"term": variant, "easy": entry["easy"], "desc": entry["desc"]})
    return found


def _fallback_easy(sentence: str, terms: list[dict]) -> str:
    """용어 뒤에 괄호 설명을 붙이는 간이 번역."""
    easy = sentence
    for t in terms:
        marker = f"{t['term']}({t['easy']})"
        if marker not in easy:
            easy = easy.replace(t["term"], marker, 1)
    return easy


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            import google.generativeai as genai
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
            _client = genai.GenerativeModel("gemini-1.5-flash")
        return _client


def _gemini_translate(sentences: list[str]) -> tuple[list[str], str]:
    """Gemini로 문장별 쉬운 번역 + 요약을 생성한다. 실패 시 예외."""
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))

    prompt = f"{_SYSTEM_PROMPT}\n\n다음 경제 뉴스 문장들을 번역해줘. 총 {len(sentences)}문장이야.\n\n{numbered}"

    try:
        response = _get_client().generate_content(prompt)
        text = response.text
        data = json.loads(text)
        easy = [s["easy"] for s in data["sentences"]]

        if len(easy) < len(sentences):
            easy += sentences[len(easy):]
        return easy[: len(sentences)], data["summary"]
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {text}") from e


def translate_article(text: str) -> dict:
    global _gemini_disabled

    text = text.strip()[:MAX_ARTICLE_CHARS]
    sentences = split_sentences(text)
    if not sentences:
        return {"summary": None, "source": "none", "notice": "번역할 문장이 없어요.", "sentences": []}

    per_terms = [find_terms(s) for s in sentences]

    summary: str | None = None
    notice: str | None = None
    easy_list: list[str] | None = None
    source = "glossary"

    if not _gemini_disabled:
        try:
            easy_list, summary = _gemini_translate(sentences)
            source = "gemini"
        except Exception as exc:
            # API 키 없음 또는 다른 인증 오류
            if "API_KEY" in str(exc) or "api_key" in str(exc).lower():
                _gemini_disabled = True
            easy_list = None

    if easy_list is None:
        easy_list = [_fallback_easy(s, t) for s, t in zip(sentences, per_terms)]
        notice = (
            "Google Gemini API를 사용할 수 없어 내장 용어사전 기반 간이 번역으로 보여주고 있어요. "
            "GOOGLE_API_KEY를 설정하면 문장 전체를 자연스러운 쉬운 말로 번역해 드려요."
        )

    result_sentences = []
    for s, easy, terms in zip(sentences, easy_list, per_terms):
        mentions, related = stocks.analyze_sentence(s)
        result_sentences.append(
            {
                "original": s,
                "easy": easy,
                "terms": terms,
                "mentions": mentions,
                "related": related,
            }
        )

    return {
        "summary": summary,
        "source": source,
        "notice": notice,
        "sentences": result_sentences,
    }
