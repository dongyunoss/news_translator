"""온톨로지가 제출용 문서가 아니라 런타임 스키마로 동작하는지 검증한다.

`.ttl`이 깨지거나 어노테이션이 빠지면 가드 판정과 근거 표시가 조용히 약해지므로,
파싱 가능 여부와 필수 어노테이션의 존재를 함께 고정한다.
"""

import pytest
from rdflib import Graph

from src.kb import ontology

REQUIRED_FILES = ["common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"]


@pytest.mark.parametrize("filename", REQUIRED_FILES)
def test_required_ontology_files_parse(filename):
    """과제 필수 제출물 5종이 존재하고 유효한 Turtle이어야 한다."""
    path = ontology.ONTOLOGY_DIR / filename
    assert path.is_file(), f"필수 제출물 누락: {filename}"
    graph = Graph()
    graph.parse(path, format="turtle")
    assert len(graph) > 0


def test_every_product_class_maps_to_a_master_table():
    tables = {cls.table for cls in ontology.product_classes().values()}
    assert tables == {"PRBD01N001", "PREF01N001", "PREF02N001", "PRFD01N001"}


def test_ordered_schemes_have_gapless_ordinals():
    """서열 비교가 성립하려면 등급마다 고유한 순번이 있어야 한다."""
    for name, scheme in ontology.schemes().items():
        if not scheme.ordered:
            continue
        ordinals = [c.ordinal for c in scheme.concepts]
        assert None not in ordinals, f"{name}: 순번 누락"
        assert len(set(ordinals)) == len(ordinals), f"{name}: 순번 중복"


def test_rating_comparison_uses_ordinal_not_alphabetical():
    """'AA- 이상'이 사전순 비교로 풀리면 AA-가 AAA보다 커진다."""
    assert ontology.ordinal_of("AAA") > ontology.ordinal_of("AA+")
    assert ontology.ordinal_of("AA+") > ontology.ordinal_of("AA-")
    assert ontology.ordinal_of("AA-") > ontology.ordinal_of("BBB+")
    assert ontology.ordinal_of("AAAA") is None

    scheme = ontology.scheme_of("AA-")
    floor = ontology.ordinal_of("AA-")
    at_or_above = {c.label for c in scheme.concepts if c.ordinal >= floor}
    assert at_or_above == {"AAA", "AA+", "AA0", "AA-"}


def test_risk_grade_ordinal_is_inverted():
    """위험등급은 숫자가 작을수록 위험이 크다. 숫자 비교를 그대로 쓰면 뒤집힌다."""
    assert ontology.ordinal_of("1등급") > ontology.ordinal_of("6등급")


def test_unavailable_properties_are_declared():
    """공모펀드 보수 미수록이 선언되어 있어야 G4가 동작한다."""
    names = {p.name for p in ontology.unavailable_properties()}
    assert "fundExpenseRatio" in names
    assert all(p.coverage == "none" for p in ontology.unavailable_properties())


@pytest.mark.parametrize(
    "question,expected",
    [
        ("공모펀드 중 총보수 낮은 것", ["공모펀드"]),
        ("해외 ETF 중 총보수 낮은 것", ["해외 ETF"]),
        ("국내채권 중 AA- 이상", ["국내채권"]),
    ],
)
def test_class_detection_is_specific(question, expected):
    """긴 별칭이 먼저 소비되어야 '해외 ETF'가 국내 ETF로도 세지 않는다."""
    assert [c.label for c in ontology.classes_mentioned(question)] == expected


def test_bare_etf_matches_both_listings():
    labels = {c.label for c in ontology.classes_mentioned("ETF 중 총보수 낮은 것")}
    assert labels == {"국내 ETF", "해외 ETF"}


def test_property_scoping_separates_product_groups():
    """같은 '총보수'라도 상품군에 따라 수록 여부가 다르다."""
    classes = {c.label: c for c in ontology.product_classes().values()}

    fund = ontology.applicable_properties("총보수", classes["공모펀드"])
    assert fund and all(p.coverage == "none" for p in fund)

    foreign = ontology.applicable_properties("총보수", classes["해외 ETF"])
    assert any(p.coverage == "full" for p in foreign)


def test_source_labels_are_available_for_evidence():
    """근거 표시(retrieved_context)를 온톨로지에서 만들 수 있어야 한다."""
    prop = ontology.properties()["hasCreditRating"]
    assert prop.source_label() == "국내채권마스터(PRBD01N001) · 신용등급"
