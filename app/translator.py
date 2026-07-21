"""뉴스 기사를 주식 초보자('주린이') 눈높이의 쉬운 문장으로 번역한다.

Google Gemini API를 REST로 직접 호출해 사용하고(별도 SDK 불필요),
API 키가 없거나 호출에 실패하면 내장 경제 용어사전 기반 주석 번역으로 폴백한다.
실패 사유는 응답 notice에 담아 사용자에게 그대로 보여준다.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

import requests

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

# 신형 키(AQ. 형식 포함)는 구형 모델에 404를 반환하므로 최신 모델부터 시도한다.
_MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]
_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_working_model: str | None = None
_model_lock = threading.Lock()

_SYSTEM_PROMPT = """\
너는 주식을 처음 시작한 초보 투자자('주린이')를 위한 경제 뉴스 해설가야.
어려운 경제·주식 기사 문장을 받아서, 한 문장씩 쉬운 한국어로 풀어서 설명해.

규칙:
- 문장 개수와 순서를 입력과 똑같이 유지해. 문장을 합치거나 나누지 마.
- 전문 용어는 일상적인 말로 풀어 쓰되, 핵심 의미가 사라지면 안 돼.
- 친근한 해요체를 사용해. (예: "~라는 뜻이에요", "~하고 있어요")
- 각 문장의 쉬운 번역은 원문보다 크게 길어지지 않게 해.
- summary에는 기사 전체를 주린이가 이해할 수 있게 2~3문장으로 요약해.

응답은 반드시 아래 JSON 형식만 출력해 (다른 텍스트·코드블록 금지):
{"summary": "기사 요약", "sentences": [{"easy": "문장1 번역"}, {"easy": "문장2 번역"}]}"""


def _load_dotenv() -> None:
    """프로젝트 루트의 .env 파일을 읽어 환경변수로 넣는다 (라이브러리 불필요)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _api_key() -> str | None:
    # GOOGLE_API_KEY가 표준이지만 흔히 쓰는 GEMINI_API_KEY도 받아준다.
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


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


def _strip_code_fence(text: str) -> str:
    """모델이 ```json ... ``` 로 감싸서 답했을 때 벗겨낸다."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _call_gemini(model: str, prompt: str, api_key: str) -> str:
    """단일 모델 호출. 성공 시 응답 텍스트, 실패 시 requests.HTTPError."""
    resp = requests.post(
        f"{_API_BASE}/{model}:generateContent",
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json",
            },
        },
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    return body["candidates"][0]["content"]["parts"][0]["text"]


def _gemini_translate(sentences: list[str]) -> tuple[list[str], str]:
    """Gemini로 문장별 쉬운 번역 + 요약을 생성한다. 실패 시 RuntimeError(사유 포함)."""
    global _working_model

    api_key = _api_key()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY 환경변수가 설정되지 않았어요.")

    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))
    prompt = f"{_SYSTEM_PROMPT}\n\n다음 경제 뉴스 문장들을 번역해줘. 총 {len(sentences)}문장이야.\n\n{numbered}"

    with _model_lock:
        models = [_working_model] if _working_model else list(_MODEL_CANDIDATES)

    last_error = "알 수 없는 오류"
    for model in models:
        try:
            text = _call_gemini(model, prompt, api_key)
        except requests.HTTPError as exc:
            status = exc.response.status_code
            try:
                detail = exc.response.json()["error"]["message"]
            except Exception:
                detail = exc.response.text[:200]
            last_error = f"{model} 호출 실패 (HTTP {status}): {detail}"
            # 404 = 이 키로 못 쓰는 모델 → 다음 후보 시도. 그 외(키 오류 등)는 즉시 중단.
            if status == 404:
                continue
            raise RuntimeError(last_error) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Gemini 서버에 연결하지 못했어요: {exc}") from exc

        try:
            data = json.loads(_strip_code_fence(text))
            easy = [s["easy"] for s in data["sentences"]]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError(f"Gemini 응답(JSON) 해석에 실패했어요: {exc}") from exc

        with _model_lock:
            _working_model = model
        if len(easy) < len(sentences):
            easy += sentences[len(easy):]
        return easy[: len(sentences)], data.get("summary", "")

    raise RuntimeError(last_error)


def translate_article(text: str) -> dict:
    text = text.strip()[:MAX_ARTICLE_CHARS]
    sentences = split_sentences(text)
    if not sentences:
        return {"summary": None, "source": "none", "notice": "번역할 문장이 없어요.", "sentences": []}

    per_terms = [find_terms(s) for s in sentences]

    summary: str | None = None
    notice: str | None = None
    easy_list: list[str] | None = None
    source = "glossary"

    try:
        easy_list, summary = _gemini_translate(sentences)
        source = "gemini"
    except Exception as exc:
        easy_list = None
        reason = str(exc)
        notice = (
            "Gemini 번역에 실패해 내장 용어사전 기반 간이 번역으로 보여주고 있어요. "
            f"(사유: {reason})"
        )

    if easy_list is None:
        easy_list = [_fallback_easy(s, t) for s, t in zip(sentences, per_terms)]

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
