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

# ListModels 조회가 실패할 때만 쓰는 예비 후보 목록.
# 실제로는 키로 사용 가능한 모델을 Google에 물어봐서(_discover_models) 고른다.
_MODEL_CANDIDATES = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]
_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_working_model: str | None = None
_discovered_models: list[str] | None = None
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


def _model_score(name: str) -> float | None:
    """텍스트 생성에 적합한 모델일수록 높은 점수. 부적합 모델은 None."""
    n = name.lower()
    # 일반 gemini 텍스트 모델만 (deep-research·learnlm 등 특수 모델 제외)
    if not n.startswith("gemini"):
        return None
    unfit = (
        "embedding", "aqa", "image", "imagen", "veo", "tts", "audio",
        "live", "computer-use", "robotics", "gemma", "deep-research",
        "interaction", "dialog",
    )
    if any(u in n for u in unfit):
        return None
    # 버전은 "gemini-2.5" 처럼 이름 바로 뒤의 숫자만 인정
    # (날짜 접미사 "-12-2025" 등을 버전으로 오인하지 않게)
    m = re.search(r"^gemini-(\d+(?:\.\d+)?)", n)
    score = (float(m.group(1)) if m else 0.0) * 10  # 버전이 높을수록 우선
    if "flash" in n:
        score += 5  # 빠르고 저렴한 flash 계열 우선
    elif "pro" in n:
        score += 2
    if "latest" in n:
        score += 3
    if "lite" in n:
        score -= 1
    if "preview" in n or "exp" in n:
        score -= 4
    if "thinking" in n:
        score -= 3
    return score


def _discover_models(api_key: str) -> list[str]:
    """이 키로 실제 사용 가능한 generateContent 모델을 조회해 우선순위로 정렬한다."""
    global _discovered_models
    with _model_lock:
        if _discovered_models is not None:
            return _discovered_models

    try:
        resp = requests.get(
            _API_BASE, params={"key": api_key, "pageSize": 1000}, timeout=15
        )
        resp.raise_for_status()
        scored: list[tuple[float, str]] = []
        for m in resp.json().get("models", []):
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            name = m["name"].removeprefix("models/")
            score = _model_score(name)
            if score is not None:
                scored.append((score, name))
        scored.sort(key=lambda x: -x[0])
        models = [name for _, name in scored[:8]]
    except Exception:
        models = []  # 조회 실패 → 예비 목록 사용

    if not models:
        models = list(_MODEL_CANDIDATES)
    with _model_lock:
        _discovered_models = models
    return models


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

    # 키로 사용 가능한 모델 목록을 조회하고,
    # 이전에 성공한 모델이 있으면 그것부터 시도한다.
    models = list(_discover_models(api_key))
    with _model_lock:
        if _working_model:
            if _working_model in models:
                models.remove(_working_model)
            models.insert(0, _working_model)

    last_error = "알 수 없는 오류"
    quota_zero = False
    for model in models:
        try:
            text = _call_gemini(model, prompt, api_key)
        except requests.HTTPError as exc:
            status = exc.response.status_code
            try:
                detail = exc.response.json()["error"]["message"]
            except Exception:
                detail = exc.response.text
            detail = detail[:300]
            last_error = f"{model} 호출 실패 (HTTP {status}): {detail}"
            # 404 = 이 키로 못 쓰는 모델, 429 = 할당량 초과/없음,
            # 400(키 문제 제외) = "Interactions API 전용" 같은 모델별 제약
            # → 모두 다음 후보 모델로 넘어간다.
            # 키 자체 문제(API key not valid 등)는 어느 모델이든 같으므로 즉시 중단.
            model_specific = status in (404, 429) or (
                status == 400 and "api key" not in detail.lower()
            )
            if model_specific:
                if status == 429 and "limit: 0" in detail:
                    quota_zero = True
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

    if quota_zero:
        raise RuntimeError(
            "이 API 키의 프로젝트에는 Gemini 무료 할당량이 없어요 (limit: 0). "
            "https://aistudio.google.com/app/apikey 에서 'AIza'로 시작하는 키를 새로 발급해 "
            "GOOGLE_API_KEY에 넣거나, Google Cloud 프로젝트에 결제를 연결해 주세요. "
            f"[마지막 오류: {last_error}]"
        )
    raise RuntimeError(f"시도한 모델: {', '.join(models)} / 마지막 오류: {last_error}")


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
