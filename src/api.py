"""평가용 API 서버 — `GET /answer`.

과제 규격(11p):
  - GET, `question_id` · `question` 두 파라미터. 인증 헤더·POST 바디는 사용하지 않는다.
  - 응답 200 OK JSON, 필드 5개 고정: question_id, question, retrieved_context,
    think_trace, answer.
  - **미정의 파라미터가 들어와도 500 없이 처리되어야 한다.**
  - 확인 불가 질의도 200 OK + 동일 스키마를 유지한다.

FastAPI 기본 동작은 필수 쿼리 파라미터가 없으면 422를 낸다. 평가 호출이 어떤 형태로
오든 스키마를 깨뜨리지 않는 편이 안전하므로, 두 파라미터를 선택값으로 받고 누락·오류를
모두 200 + 확인 불가로 흡수한다.
"""

from __future__ import annotations

import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .agent import pipeline

app = FastAPI(
    title="금융상품 Agent",
    description="정형 금융상품 데이터 기반 근거 지향 QA 에이전트",
)


def _envelope(question_id: str, question: str, context: str, trace: str, answer: str) -> dict:
    return {
        "question_id": question_id,
        "question": question,
        "retrieved_context": context,
        "think_trace": trace,
        "answer": answer,
    }


@app.get("/answer")
def answer(request: Request, question_id: str = "", question: str = ""):
    # 미정의 파라미터는 무시한다 (규격상 500이 나면 안 된다).
    unknown = [key for key in request.query_params if key not in ("question_id", "question")]

    try:
        body = pipeline.answer_question(question_id, question)
    except Exception:  # 어떤 내부 오류에서도 스키마를 유지한다
        body = _envelope(
            question_id,
            question,
            "-",
            f"내부 오류: {traceback.format_exc(limit=1).strip().splitlines()[-1]}",
            "확인할 수 없습니다. 요청을 처리하는 중 오류가 발생했습니다.",
        )

    if unknown:
        body["think_trace"] += f" | 무시한 파라미터: {', '.join(unknown)}"

    return JSONResponse(content=body, media_type="application/json; charset=utf-8")


@app.get("/health")
def health():
    from .kb import registry

    return {"status": "ok", "products_indexed": registry.product_count()}
