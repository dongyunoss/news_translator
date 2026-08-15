"""HyperCLOVA X (CLOVA Studio) 클라이언트.

기존 `app/translator.py`의 Gemini 계층에서 쓸 만한 부분 — 모델 후보 폴백,
구조화 JSON 강제, 깨진 응답 salvage — 만 가져오고 호출부는 CLOVA Studio로 바꿨다.

설계 제약 두 가지:

1. **평가 항목에 응답 소요 시간이 포함된다.** Gemini 계층은 요청마다 모델 후보를
   순차 시도했는데 그대로 두면 문항당 60초 예산을 잡아먹는다. 여기서는 첫 성공
   조합(엔드포인트 버전 + 인증 방식 + 모델)을 프로세스 수명 동안 고정한다.
2. **LLM 활용 기준이 추후 공지 예정이다.** 다른 모델로 갈아탈 수 있도록 호출부는
   `chat()` / `chat_json()` 두 함수로만 노출한다.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

import requests

# CLOVA Studio 모델 — 설명자료(19p) 기준. 앞쪽이 우선 후보.
# HCX-007은 추론 특화, DASH 계열은 경량·저지연이므로 폴백으로 둔다.
MODEL_CANDIDATES = ["HCX-007", "HCX-005", "HCX-003", "HCX-DASH-002", "HCX-DASH-001"]

DEFAULT_HOST = "https://clovastudio.stream.ntruss.com"

# CLOVA Studio는 신규 키(Bearer)와 구 APIGW 키 방식이 공존한다.
# 어느 쪽 키를 발급받았는지에 따라 경로와 헤더가 달라지므로 둘 다 시도한다.
_ENDPOINT_STYLES = [
    ("v3", "/v3/chat-completions/{model}"),
    ("v1", "/testapp/v1/chat-completions/{model}"),
]

_TIMEOUT = 60
_lock = threading.Lock()
_resolved: dict[str, Any] | None = None  # 첫 성공 조합 캐시


class LLMError(RuntimeError):
    """CLOVA Studio 호출 실패. 상위에서 '확인할 수 없음' 처리로 이어진다."""


def _load_dotenv() -> None:
    """저장소 루트의 .env를 환경변수로 올린다 (라이브러리 불필요)."""
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
    return os.getenv("CLOVASTUDIO_API_KEY") or os.getenv("NCP_CLOVASTUDIO_API_KEY")


def _gateway_key() -> str | None:
    """구 방식에서만 필요한 API Gateway 키."""
    return os.getenv("NCP_APIGW_API_KEY")


def _host() -> str:
    return os.getenv("CLOVASTUDIO_HOST", DEFAULT_HOST).rstrip("/")


def configured() -> bool:
    return bool(_api_key())


def _headers(style: str, api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if style == "v3":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["X-NCP-CLOVASTUDIO-API-KEY"] = api_key
        gw = _gateway_key()
        if gw:
            headers["X-NCP-APIGW-API-KEY"] = gw
    return headers


def _extract_content(payload: dict) -> str:
    """CLOVA Studio 응답에서 본문만 꺼낸다.

    정상 응답은 {"status": {"code": "20000"}, "result": {"message": {"content": ...}}}.
    OpenAI 호환 형태로 오는 배포도 있어 choices 경로도 함께 본다.
    """
    result = payload.get("result") or {}
    message = result.get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content

    # 일부 모델은 content를 파트 배열로 돌려준다.
    if isinstance(content, list):
        joined = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
        if joined.strip():
            return joined

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        alt = (choices[0].get("message") or {}).get("content")
        if isinstance(alt, str) and alt.strip():
            return alt

    raise LLMError(f"응답에서 본문을 찾지 못했습니다: {json.dumps(payload)[:300]}")


def _post(style: str, path: str, model: str, body: dict, api_key: str) -> str:
    url = _host() + path.format(model=model)
    res = requests.post(url, headers=_headers(style, api_key), json=body, timeout=_TIMEOUT)

    if res.status_code != 200:
        raise LLMError(f"HTTP {res.status_code} ({style}/{model}): {res.text[:300]}")

    payload = res.json()
    status_code = str((payload.get("status") or {}).get("code", "20000"))
    if not status_code.startswith("200"):
        message = (payload.get("status") or {}).get("message", "")
        raise LLMError(f"CLOVA {status_code} ({model}): {message}")

    return _extract_content(payload)


def _resolve(body: dict, api_key: str) -> tuple[dict, str]:
    """동작하는 (엔드포인트 스타일, 모델) 조합을 찾아 고정한다."""
    global _resolved

    with _lock:
        if _resolved is not None:
            combo = _resolved
            return combo, _post(combo["style"], combo["path"], combo["model"], body, api_key)

        preferred = os.getenv("CLOVASTUDIO_MODEL")
        models = [preferred, *MODEL_CANDIDATES] if preferred else MODEL_CANDIDATES

        errors: list[str] = []
        for style, path in _ENDPOINT_STYLES:
            for model in models:
                try:
                    text = _post(style, path, model, body, api_key)
                except LLMError as exc:
                    errors.append(str(exc))
                    continue
                _resolved = {"style": style, "path": path, "model": model}
                return _resolved, text

        raise LLMError("사용 가능한 모델을 찾지 못했습니다. " + " | ".join(errors[:4]))


def chat(
    system: str,
    user: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.1,
) -> str:
    """단일 턴 대화. 근거 기반 답변이 목적이라 temperature는 낮게 잡는다."""
    api_key = _api_key()
    if not api_key:
        raise LLMError(
            "CLOVASTUDIO_API_KEY가 없습니다. "
            "CLOVA Studio 콘솔에서 발급한 키를 .env에 넣어 주세요."
        )

    body = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "topP": 0.8,
        "topK": 0,
        "maxTokens": max_tokens,
        "temperature": temperature,
        "repeatPenalty": 1.1,
        "stopBefore": [],
        "includeAiFilters": False,
    }

    _, text = _resolve(body, api_key)
    return text


def active_model() -> str | None:
    """현재 고정된 모델 이름 (아직 호출 전이면 None)."""
    return _resolved["model"] if _resolved else None


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _salvage_json(text: str) -> dict | None:
    """응답이 잘려서 JSON 파싱이 깨졌을 때 가장 바깥 객체만 잘라내 재시도."""
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(text[start:], start):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
        elif ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def chat_json(system: str, user: str, **kwargs) -> dict:
    """JSON 객체 응답을 강제한다. 파싱 실패 시 salvage를 거쳐 그래도 안 되면 예외."""
    guard = "\n\n응답은 반드시 JSON 객체 하나만 출력해. 코드블록·설명 문장 금지."
    text = _strip_code_fence(chat(system + guard, user, **kwargs))

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = _salvage_json(text)

    if not isinstance(parsed, dict):
        raise LLMError(f"JSON 응답을 파싱하지 못했습니다: {text[:300]}")
    return parsed
