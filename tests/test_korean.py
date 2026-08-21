"""조사 선택 — 답변 문장은 평가자가 직접 읽으므로 "총보수은(는)"을 남기지 않는다."""

import pytest

from src.korean import has_final_consonant, josa, particle, quoted


@pytest.mark.parametrize(
    "word,expected",
    [
        ("총보수", "총보수는"),
        ("순자산", "순자산은"),
        ("공모펀드", "공모펀드는"),
        ("9등급", "9등급은"),
        ("듀레이션", "듀레이션은"),
    ],
)
def test_hangul_particle(word, expected):
    assert josa(word, "은/는") == expected


@pytest.mark.parametrize(
    "word,expected",
    [
        # 한국어로 읽었을 때의 받침을 따른다: ETF는 "에프"라 받침이 없다
        ("ETF", "ETF는"),
        ("AAAA", "AAAA는"),
        ("AUM", "AUM은"),  # "에이유엠"
        ("ISIN", "ISIN은"),  # "아이에스아이엔"
        ("KODEX 200", "KODEX 200은"),  # "이백"
        ("A1", "A1은"),  # "일"
    ],
)
def test_latin_and_digit_particle(word, expected):
    assert josa(word, "은/는") == expected


def test_quoted_uses_the_word_not_the_quote():
    """따옴표를 포함한 채로 판정하면 마지막 글자가 따옴표라 조사가 어긋난다."""
    assert quoted("9등급", "은/는") == "'9등급'은"
    assert quoted("AAAA", "은/는") == "'AAAA'는"
    assert josa("'9등급'", "은/는") != "'9등급'은"  # 감싼 채로 넘기면 틀린다


def test_particle_returns_only_the_particle():
    assert particle("총보수", "이/가") == "가"
    assert particle("순자산", "이/가") == "이"


def test_empty_input_is_safe():
    assert has_final_consonant("") is False
    assert josa("", "은/는") == "는"
