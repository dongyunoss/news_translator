"""한국어 조사 선택.

답변 문장은 평가자가 직접 읽는 산출물이므로 "총보수은(는)" 같은 표기를 남기지
않는다. 앞 글자의 받침 유무로 조사를 고른다.
"""

from __future__ import annotations

_HANGUL_START = 0xAC00
_HANGUL_END = 0xD7A3
_JONGSUNG_COUNT = 28

# 한국어로 읽었을 때 받침으로 끝나는 라틴 문자와 숫자.
# L(엘)·M(엠)·N(엔)·R(알)만 받침이 남고, F는 "에프"라 받침이 없다 — "ETF는".
# 숫자는 0(영)·1(일)·3(삼)·6(육)·7(칠)·8(팔)이 받침으로 끝난다.
_ENDS_WITH_CONSONANT = set("LMNRlmnr013678")


def has_final_consonant(word: str) -> bool:
    """마지막 글자에 받침이 있는가."""
    word = (word or "").strip()
    if not word:
        return False

    last = word[-1]
    code = ord(last)
    if _HANGUL_START <= code <= _HANGUL_END:
        return (code - _HANGUL_START) % _JONGSUNG_COUNT != 0
    return last in _ENDS_WITH_CONSONANT


def particle(word: str, pair: str) -> str:
    """단어에 맞는 조사만 돌려준다. `pair`는 "은/는"처럼 받침있음/없음 순서.

    따옴표로 감싼 값 뒤에 조사를 붙일 때 쓴다. 감싼 문자열을 그대로 `josa()`에
    넘기면 마지막 글자가 따옴표라 받침 판정이 어긋난다.
    """
    with_final, without_final = pair.split("/")
    return with_final if has_final_consonant(word) else without_final


def josa(word: str, pair: str) -> str:
    """단어에 알맞은 조사를 붙인다."""
    return word + particle(word, pair)


def quoted(word: str, pair: str) -> str:
    """따옴표로 감싼 값에 알맞은 조사를 붙인다. `'9등급'은` 처럼."""
    return f"'{word}'{particle(word, pair)}"
