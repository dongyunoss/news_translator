"""질의 처리 파이프라인 — `GET /answer` 한 건의 전체 흐름.

    질의 → 답변불가 가드 → Intent 라우팅 → Retrieval → 근거 기반 생성

현재 구현 단계: 가드와 라우팅까지. Retrieval은 주최 측 마스터 4종이 적재된 뒤
붙는다. 아직 검색할 KB가 없는 구간에서 답을 지어내면 과제 규칙("데이터에 근거 없는
내용 생성 금지")을 정면으로 위반하므로, 그 구간은 확인 불가로 처리하고 사유를
think_trace에 남긴다.
"""

from __future__ import annotations

import time

from ..kb import registry
from . import guards, router

# 마스터 데이터 적재 여부. 실제 KB가 붙으면 registry가 판단하도록 바꾼다.
_KB_READY = False

_UNLOADED_ANSWER = (
    "확인할 수 없습니다. 현재 조회 가능한 상품 마스터 데이터가 적재되어 있지 않습니다."
)


def _trace(*lines: str) -> str:
    return " → ".join(line for line in lines if line)


def answer_question(question_id: str, question: str) -> dict:
    """평가 API 응답 본문을 만든다. 어떤 경우에도 동일 스키마를 유지한다."""
    started = time.perf_counter()
    question = (question or "").strip()

    blocked = guards.check(question)
    if blocked is not None:
        elapsed = time.perf_counter() - started
        return {
            "question_id": question_id,
            "question": question,
            "retrieved_context": blocked.context,
            "think_trace": _trace(
                "답변불가 가드 검사",
                f"{blocked.guard} 발동: {blocked.reason}",
                "검색·생성 미수행 (환각 차단)",
                f"소요 {elapsed * 1000:.0f}ms",
            ),
            "answer": blocked.answer,
        }

    route = router.classify(question)
    elapsed = time.perf_counter() - started

    if not _KB_READY:
        return {
            "question_id": question_id,
            "question": question,
            "retrieved_context": "-",
            "think_trace": _trace(
                "답변불가 가드 통과",
                route.describe(),
                f"KB 미적재 (상품 인덱스 {registry.product_count()}건, 시드 데이터)",
                f"소요 {elapsed * 1000:.0f}ms",
            ),
            "answer": _UNLOADED_ANSWER,
        }

    raise NotImplementedError("Retrieval 단계는 마스터 적재 후 구현한다")
