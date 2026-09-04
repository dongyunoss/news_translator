"""뉴스 기사를 주식 초보자('주린이') 눈높이의 쉬운 문장으로 번역한다.

Google Gemini API를 REST로 직접 호출해 사용하고(별도 SDK 불필요),
API 키가 없거나 호출에 실패하면 내장 경제 용어사전 기반 주석 번역으로 폴백한다.
실패 사유는 응답 notice에 담아 사용자에게 그대로 보여준다.
"""

from __future__ import annotations

import json
import hashlib
import os
import random
import re
import threading
from pathlib import Path

import requests

from . import products, stocks

GLOSSARY: list[dict] = json.loads(
    (Path(__file__).parent / "data" / "glossary.json").read_text(encoding="utf-8")
)

_TERM_INDEX: list[tuple[str, dict]] = sorted(
    ((v, entry) for entry in GLOSSARY for v in entry["variants"]),
    key=lambda x: -len(x[0]),
)

_GLOSSARY_POOL = [
    {"term": entry["variants"][0], "easy": entry["easy"], "desc": entry["desc"]}
    for entry in GLOSSARY
]
_GLOSSARY_EASY_POOL = [entry["easy"] for entry in _GLOSSARY_POOL]

_STOCK_POOL = [
    f"{stock['name']} ({code})"
    for code, stock in stocks.STOCKS.items()
]

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
어려운 경제·주식·기술 기사 문장을 받아서, 한 문장씩 쉬운 한국어로 풀어서 설명해.

각 문장마다:
- easy: 전문 용어를 일상적인 말로 풀어 쓴 쉬운 번역. 친근한 해요체(예: "~라는 뜻이에요").
  핵심 의미가 사라지면 안 되고, 원문보다 크게 길어지지 않게 해.
- terms: 그 문장에 등장하는 어려운 경제·금융·기술 용어 목록 (최대 4개).
  * word: 원문에 등장한 표기 그대로 (띄어쓰기·조사 없이 단어만)
  * meaning: 6~15자의 아주 짧은 뜻풀이
  * detail: 주린이 눈높이의 한 문장 설명
  누구나 아는 쉬운 단어는 넣지 마.
- hard: 전문 용어가 많거나 구조가 복잡해서 초보자가 특히 이해하기 어려운 문장이면 true.

summary에는 기사 전체를 주린이가 이해할 수 있게 2~3문장으로 요약해.

응답은 반드시 아래 JSON 형식만 출력해 (다른 텍스트·코드블록 금지):
{"summary": "기사 요약", "sentences": [{"easy": "문장1 번역", "hard": false,
 "terms": [{"word": "밸류에이션", "meaning": "기업 가치 평가", "detail": "주가가 기업의 실제 가치에 비해 싼지 비싼지 따져보는 일이에요."}]}]}"""


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


def _stable_rng(seed_text: str) -> random.Random:
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16)
    return random.Random(seed)


def _build_choices(correct: str, pool: list[str], rng: random.Random, size: int = 4) -> tuple[list[str], int]:
    candidates = [value for value in pool if value != correct]
    if len(candidates) < size - 1:
        candidates = candidates + [v for v in pool if v != correct]
    choices = candidates[: size - 1]
    choices.append(correct)
    rng.shuffle(choices)
    return choices, choices.index(correct)


def _build_term_question(sentence: str, term: dict, rng: random.Random, qid: int) -> dict:
    choices, correct_index = _build_choices(term["easy"], _GLOSSARY_EASY_POOL, rng)
    snippet = sentence[:52].strip()
    if len(sentence) > 52:
        snippet += "…"
    return {
        "id": f"q{qid}",
        "type": "multiple_choice",
        "category": "term",
        "prompt": f"기사 문장 \"{snippet}\"에서 '{term['term']}'의 뜻으로 가장 적절한 것은?",
        "options": choices,
        "answer": correct_index,
        "explanation": term["desc"],
    }


def _build_stock_question(sentence: str, related: list[dict], rng: random.Random, qid: int) -> dict | None:
    if not related:
        return None
    target = related[0]
    choices, correct_index = _build_choices(
        f"{target['name']} ({target['code']})",
        _STOCK_POOL,
        rng,
    )
    snippet = sentence[:52].strip()
    if len(sentence) > 52:
        snippet += "…"
    return {
        "id": f"q{qid}",
        "type": "multiple_choice",
        "category": "stock",
        "prompt": f"문장 \"{snippet}\" 내용으로 가장 관련 있는 종목은?",
        "options": choices,
        "answer": correct_index,
        "explanation": f"관련 근거: {target['name']}은(는) {target.get('reason', '문장 키워드와의 연결')}",
    }


def _fallback_questions(rng: random.Random, qid_start: int, count: int) -> list[dict]:
    questions: list[dict] = []
    qid = qid_start
    while len(questions) < count:
        term = rng.choice(_GLOSSARY_POOL)
        choices, correct_index = _build_choices(term["easy"], _GLOSSARY_EASY_POOL, rng)
        questions.append(
            {
                "id": f"q{qid}",
                "type": "multiple_choice",
                "category": "term",
                "prompt": f"용어 '{term['term']}'의 뜻으로 가장 적절한 것은?",
                "options": choices,
                "answer": correct_index,
                "explanation": term["desc"],
            }
        )
        qid += 1
    return questions

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


# 구조화 출력 강제 스키마 — 모델이 형식이 깨진 JSON을 내놓지 못하게 한다.
# 용어 필드는 word/meaning/detail로 명명해 문장 번역 키(easy)와 겹치지 않게 한다
# (_salvage_json이 "easy"만 찾아 복구하므로 이름이 겹치면 안 됨).
_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "sentences": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "easy": {"type": "STRING"},
                    "hard": {"type": "BOOLEAN"},
                    "terms": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "word": {"type": "STRING"},
                                "meaning": {"type": "STRING"},
                                "detail": {"type": "STRING"},
                            },
                            "required": ["word", "meaning"],
                        },
                    },
                },
                "required": ["easy"],
            },
        },
    },
    "required": ["summary", "sentences"],
}


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
                "responseSchema": _RESPONSE_SCHEMA,
            },
        },
        timeout=90,
    )
    resp.raise_for_status()
    body = resp.json()
    parts = body["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def _salvage_json(text: str) -> dict | None:
    """잘리거나 일부 깨진 JSON 응답에서 summary와 easy 문장들을 최대한 건져낸다."""
    easies: list[str] = []
    for m in re.finditer(r'"easy"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
        try:
            easies.append(json.loads(f'"{m.group(1)}"'))
        except json.JSONDecodeError:
            easies.append(m.group(1))
    if not easies:
        return None
    summary = ""
    sm = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if sm:
        try:
            summary = json.loads(f'"{sm.group(1)}"')
        except json.JSONDecodeError:
            summary = sm.group(1)
    return {"summary": summary, "sentences": [{"easy": e} for e in easies]}


def _gemini_translate(sentences: list[str]) -> tuple[list[dict], str]:
    """Gemini로 문장별 {easy, hard, terms} + 요약을 생성한다. 실패 시 RuntimeError(사유 포함)."""
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
        except (json.JSONDecodeError, TypeError):
            data = _salvage_json(text)  # 깨진 JSON에서 문장 복구 시도
        try:
            result = [
                {
                    "easy": s["easy"],
                    "hard": bool(s.get("hard")),
                    "terms": s.get("terms") or [],
                }
                for s in data["sentences"]
                if isinstance(s, dict) and s.get("easy")
            ]
            if not result:
                raise KeyError("sentences")
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                f"Gemini 응답(JSON) 해석에 실패했어요. 응답 앞부분: {text[:150]!r}"
            ) from exc

        with _model_lock:
            _working_model = model
        # 개수가 모자라면 나머지는 원문 그대로 채운다.
        while len(result) < len(sentences):
            result.append({"easy": sentences[len(result)], "hard": False, "terms": []})
        return result[: len(sentences)], data.get("summary", "")

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
    ai_sentences: list[dict] | None = None
    source = "glossary"

    try:
        ai_sentences, summary = _gemini_translate(sentences)
        source = "gemini"
    except Exception as exc:
        reason = str(exc)
        notice = (
            "Gemini 번역에 실패해 내장 용어사전 기반 간이 번역으로 보여주고 있어요. "
            f"(사유: {reason})"
        )

    result_sentences = []
    for i, (s, terms) in enumerate(zip(sentences, per_terms)):
        ai = ai_sentences[i] if ai_sentences else None
        easy = ai["easy"] if ai else _fallback_easy(s, terms)
        hard = bool(ai and ai.get("hard"))

        # 내장 사전 용어 + Gemini가 찾은 어려운 경제·기술 용어 병합 (사전 우선)
        merged_terms = list(terms)
        seen = {t["term"] for t in merged_terms}
        for t in (ai.get("terms") if ai else None) or []:
            if not isinstance(t, dict):
                continue
            word = (t.get("word") or "").strip()
            # 원문에 실제로 등장하는 새 용어만 (본문 하이라이트가 가능해야 함)
            if not word or word in seen or word not in s:
                continue
            seen.add(word)
            merged_terms.append(
                {
                    "term": word,
                    "easy": (t.get("meaning") or "").strip() or "어려운 용어",
                    "desc": (t.get("detail") or "").strip(),
                }
            )

        mentions, related = stocks.analyze_sentence(s)
        result_sentences.append(
            {
                "original": s,
                "easy": easy,
                "hard": hard,
                "terms": merged_terms,
                "mentions": mentions,
                "related": related,
                "products": products.match_sentence(s),
            }
        )

    return {
        "summary": summary,
        "source": source,
        "notice": notice,
        "sentences": result_sentences,
    }


def generate_quiz(text: str, count: int = 8) -> dict:
    text = text.strip()[:MAX_ARTICLE_CHARS]
    if count <= 0:
        return {
            "source": "local",
            "notice": "문항 수가 0 이하로 요청돼 퀴즈를 만들지 않았어요.",
            "questions": [],
            "question_count": 0,
            "requested_count": 0,
        }

    sentences = split_sentences(text)
    if not sentences:
        return {
            "source": "local",
            "notice": "퀴즈로 만들 문장이 없어요.",
            "questions": [],
            "question_count": 0,
            "requested_count": count,
        }

    rng = _stable_rng(text)
    sentence_meta = []
    for s in sentences:
        _, related = stocks.analyze_sentence(s)
        sentence_meta.append((s, find_terms(s), _, related))

    questions: list[dict] = []
    used_terms: set[str] = set()
    used_stocks: set[str] = set()

    qid = 0
    # 1차: 문장 기반 용어/종목 문제
    for s, terms, _, related in sentence_meta:
        if len(questions) >= count:
            break
        for term in terms:
            if len(questions) >= count:
                break
            if term["term"] in used_terms:
                continue
            q = _build_term_question(s, term, rng, qid)
            qid += 1
            questions.append(q)
            used_terms.add(term["term"])
            if len(questions) >= count:
                break

        if len(questions) >= count:
            break
        if related:
            top_related = [r for r in related if r["code"] not in used_stocks][:1]
            q = _build_stock_question(s, top_related, rng, qid)
            if q:
                qid += 1
                questions.append(q)
                used_stocks.update(r["code"] for r in top_related)

    # 2차: 데이터가 부족하면 기사 외 용어로 보완
    if len(questions) < count:
        questions.extend(_fallback_questions(rng, qid, count - len(questions)))

    # 중복 보정: 퀴즈 수를 초과 방지
    if len(questions) > count:
        questions = questions[:count]

    return {
        "source": "local",
        "questions": questions,
        "question_count": len(questions),
        "requested_count": count,
    }
