"""온톨로지 로더 — `.ttl`을 에이전트가 조회하는 런타임 스키마로 만든다.

온톨로지를 제출용 문서로만 두면 코드와 따로 놀다가 어긋난다. 여기서는 반대로,
`ontology/*.ttl`을 유일한 스키마 원본으로 삼고 아래 세 가지를 코드가 읽어 쓴다.

    값 도메인   skos:ConceptScheme + fp:ordinal
                → "체계에 없는 값" 판정, "AA- 이상" 같은 서열 비교

    수록 범위   fp:coverage (full / partial / none / external)
                → "데이터에 없는 것을 묻는 질의" 판정

    출처        fp:sourceTable / fp:sourceColumn
                → retrieved_context 자동 생성

이렇게 두면 컬럼이 하나 늘거나 등급 체계가 바뀔 때 `.ttl`만 고치면 되고,
가드·라우터·근거 표시가 함께 따라온다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

FP = Namespace("http://mafest.ai/product#")
ONTOLOGY_DIR = Path(__file__).resolve().parent.parent.parent / "ontology"

# 상품군별 온톨로지 파일과 마스터 테이블의 대응.
DOMAIN_FILES = {
    "common": "common.ttl",
    "bond_kr": "bond_kr.ttl",
    "etf_kr": "etf_kr.ttl",
    "etf_gl": "etf_gl.ttl",
    "fund_pub": "fund_pub.ttl",
}

TABLE_LABELS = {
    "PRBD01N001": "국내채권마스터",
    "PREF01N001": "국내ETF마스터",
    "PREF02N001": "해외ETF마스터",
    "PRFD01N001": "공모펀드마스터",
}


@dataclass(frozen=True)
class Concept:
    """값 도메인의 한 항목."""

    uri: str
    scheme: str
    label: str
    aliases: tuple[str, ...] = ()
    ordinal: int | None = None

    @property
    def ordered(self) -> bool:
        return self.ordinal is not None


@dataclass(frozen=True)
class Scheme:
    """하나의 값 도메인 체계."""

    uri: str
    label: str
    concepts: tuple[Concept, ...]

    @property
    def ordered(self) -> bool:
        return any(c.ordered for c in self.concepts)

    def labels(self) -> set[str]:
        out: set[str] = set()
        for concept in self.concepts:
            out.add(concept.label)
            out.update(concept.aliases)
        return out


@dataclass(frozen=True)
class Property:
    """상품 속성 하나의 정의."""

    uri: str
    label: str
    coverage: str  # full | partial | none | external | unknown
    table: str | None
    column: str | None
    comment: str = ""
    domain: str | None = None
    range: str | None = None
    aliases: tuple[str, ...] = field(default=())

    @property
    def name(self) -> str:
        return self.uri.rsplit("#", 1)[-1]

    def source_label(self) -> str:
        """근거 표시에 쓸 사람이 읽는 출처 문자열.

        테이블이 없는 속성은 두 종류다. 여러 마스터가 공유하는 공통 속성
        (위험등급 등)과 마스터 밖에서 수집하는 관계(편입종목 등). coverage로
        구분하지 않으면 공통 속성이 외부 데이터로 잘못 표기된다.
        """
        if not self.table:
            return "외부 수집 데이터" if self.coverage == "external" else f"{self.label}(공통)"
        table = f"{TABLE_LABELS.get(self.table, self.table)}({self.table})"
        return f"{table} · {self.column}" if self.column else table


def _text(value) -> str:
    return str(value).strip()


@lru_cache(maxsize=1)
def graph() -> Graph:
    """5개 `.ttl`을 하나의 그래프로 합쳐 읽는다."""
    merged = Graph()
    for filename in DOMAIN_FILES.values():
        path = ONTOLOGY_DIR / filename
        if path.is_file():
            merged.parse(path, format="turtle")
    return merged


@lru_cache(maxsize=1)
def schemes() -> dict[str, Scheme]:
    """모든 값 도메인 체계. 키는 체계의 로컬 이름."""
    g = graph()
    out: dict[str, Scheme] = {}

    for scheme_uri in g.subjects(RDF.type, SKOS.ConceptScheme):
        concepts: list[Concept] = []
        for concept_uri in g.subjects(SKOS.inScheme, scheme_uri):
            label = g.value(concept_uri, SKOS.prefLabel)
            if label is None:
                continue
            ordinal = g.value(concept_uri, FP.ordinal)
            concepts.append(
                Concept(
                    uri=str(concept_uri),
                    scheme=str(scheme_uri),
                    label=_text(label),
                    aliases=tuple(
                        _text(a) for a in g.objects(concept_uri, SKOS.altLabel)
                    ),
                    ordinal=int(ordinal) if ordinal is not None else None,
                )
            )

        scheme_label = g.value(scheme_uri, RDFS.label)
        name = str(scheme_uri).rsplit("#", 1)[-1]
        out[name] = Scheme(
            uri=str(scheme_uri),
            label=_text(scheme_label) if scheme_label else name,
            concepts=tuple(sorted(concepts, key=lambda c: -(c.ordinal or 0))),
        )
    return out


@lru_cache(maxsize=1)
def properties() -> dict[str, Property]:
    """모든 속성 정의. 키는 속성의 로컬 이름."""
    g = graph()
    out: dict[str, Property] = {}

    for kind in (OWL.DatatypeProperty, OWL.ObjectProperty):
        for uri in g.subjects(RDF.type, kind):
            if not isinstance(uri, URIRef) or not str(uri).startswith(str(FP)):
                continue
            label = g.value(uri, RDFS.label)
            coverage = g.value(uri, FP.coverage)
            table = g.value(uri, FP.sourceTable)
            column = g.value(uri, FP.sourceColumn)
            comment = g.value(uri, RDFS.comment)
            domain = g.value(uri, RDFS.domain)
            range_ = g.value(uri, RDFS.range)

            name = str(uri).rsplit("#", 1)[-1]
            out[name] = Property(
                uri=str(uri),
                label=_text(label) if label else name,
                coverage=_text(coverage) if coverage else "unknown",
                table=_text(table) if table else None,
                column=_text(column) if column else None,
                comment=_text(comment) if comment else "",
                domain=str(domain) if domain else None,
                range=str(range_) if range_ else None,
                aliases=tuple(_text(a) for a in g.objects(uri, SKOS.altLabel)),
            )
    return out


@dataclass(frozen=True)
class ProductClass:
    """상품군 하나. 마스터 테이블과 1:1로 대응한다."""

    uri: str
    label: str
    table: str
    aliases: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.uri.rsplit("#", 1)[-1]

    def table_label(self) -> str:
        return f"{TABLE_LABELS.get(self.table, self.table)}({self.table})"


@lru_cache(maxsize=1)
def product_classes() -> dict[str, ProductClass]:
    """마스터 테이블을 가진 상품군 클래스."""
    g = graph()
    out: dict[str, ProductClass] = {}
    for uri in g.subjects(RDF.type, OWL.Class):
        table = g.value(uri, FP.sourceTable)
        if table is None:
            continue
        label = g.value(uri, RDFS.label)
        name = str(uri).rsplit("#", 1)[-1]
        out[name] = ProductClass(
            uri=str(uri),
            label=_text(label) if label else name,
            table=_text(table),
            aliases=tuple(_text(a) for a in g.objects(uri, SKOS.altLabel)),
        )
    return out


@lru_cache(maxsize=512)
def superclasses(class_uri: str) -> frozenset[str]:
    """자기 자신을 포함한 상위 클래스 집합 (rdfs:subClassOf 전이 폐포)."""
    g = graph()
    seen: set[str] = set()
    stack = [URIRef(class_uri)]
    while stack:
        current = stack.pop()
        if str(current) in seen:
            continue
        seen.add(str(current))
        stack.extend(g.objects(current, RDFS.subClassOf))
    return frozenset(seen)


@lru_cache(maxsize=1)
def _class_alias_index() -> list[tuple[str, tuple[ProductClass, ...]]]:
    """정규화한 별칭 → 해당 상품군들. 긴 별칭이 먼저 오도록 정렬한다.

    "ETF"는 국내·해외 양쪽의 별칭이므로 두 클래스를 함께 돌려준다. 상품군을
    좁히지 못한 질의를 한쪽으로 단정하면 안 되기 때문이다.
    """
    buckets: dict[str, list[ProductClass]] = {}
    for cls in product_classes().values():
        for alias in (cls.label, *cls.aliases):
            buckets.setdefault(_normalize(alias), []).append(cls)
    return sorted(
        ((alias, tuple(classes)) for alias, classes in buckets.items()),
        key=lambda pair: -len(pair[0]),
    )


def classes_mentioned(question: str) -> list[ProductClass]:
    """질의가 가리키는 상품군. 긴 별칭부터 소비하며 매칭한다.

    "해외 ETF"가 잡히면 그 자리를 지워서 짧은 별칭 "ETF"가 같은 글자에
    다시 걸리지 않게 한다. 그래야 "해외 ETF"를 국내 ETF로도 세지 않는다.
    """
    haystack = _normalize(question)
    found: dict[str, ProductClass] = {}

    for alias, classes in _class_alias_index():
        if len(alias) < 2 or alias not in haystack:
            continue
        haystack = haystack.replace(alias, " " * len(alias))
        for cls in classes:
            found.setdefault(cls.uri, cls)
    return list(found.values())


def applicable_properties(name: str, cls: ProductClass) -> list[Property]:
    """해당 상품군에 적용되는, 주어진 이름(라벨 또는 별칭)의 속성들.

    rdfs:domain이 그 상품군이거나 상위 클래스인 속성만 남긴다. 이 필터가
    "공모펀드의 총보수"와 "해외 ETF의 총보수"를 갈라놓는다.
    """
    target = _normalize(name)
    ancestors = superclasses(cls.uri)
    return [
        prop
        for prop in properties().values()
        if prop.domain
        and prop.domain in ancestors
        and target in {_normalize(n) for n in (prop.label, *prop.aliases) if n}
    ]


@lru_cache(maxsize=1)
def _ordered_labels() -> dict[str, list[tuple[str, Scheme]]]:
    """서열 있는 체계의 라벨 → (라벨, 체계) 역색인. 대소문자 무시."""
    index: dict[str, list[tuple[str, Scheme]]] = {}
    for scheme in schemes().values():
        if not scheme.ordered:
            continue
        for label in scheme.labels():
            index.setdefault(label.upper(), []).append((label, scheme))
    return index


def all_domain_values() -> set[str]:
    """모든 값 도메인의 라벨·별칭 합집합 (대문자 정규화)."""
    out: set[str] = set()
    for scheme in schemes().values():
        out.update(label.upper() for label in scheme.labels())
    return out


def is_known_value(token: str) -> bool:
    return token.upper() in all_domain_values()


def ordinal_of(token: str) -> int | None:
    """등급 라벨의 서열. \"AA- 이상\" 같은 비교를 정수 비교로 옮길 때 쓴다."""
    for label, scheme in _ordered_labels().get(token.upper(), []):
        for concept in scheme.concepts:
            if concept.label == label or label in concept.aliases:
                return concept.ordinal
    return None


def scheme_of(token: str) -> Scheme | None:
    """값이 속한 체계를 찾는다."""
    upper = token.upper()
    for scheme in schemes().values():
        if any(label.upper() == upper for label in scheme.labels()):
            return scheme
    return None


def unavailable_properties() -> list[Property]:
    """제공 데이터에 수록되지 않은 속성 (coverage = none)."""
    return [p for p in properties().values() if p.coverage == "none"]


def partial_properties() -> list[Property]:
    """일부 종목만 수록된 속성 — 전수 집계 시 한계를 밝혀야 한다."""
    return [p for p in properties().values() if p.coverage == "partial"]


def _normalize(text: str) -> str:
    return re.sub(r"[\s\-_·]+", "", text).upper()


@lru_cache(maxsize=1)
def _label_index() -> list[tuple[str, tuple[Property, ...]]]:
    """정규화한 라벨·별칭 → 그 이름을 쓰는 속성들.

    "총보수"는 세 상품군에 각각 정의되어 있으므로 하나의 이름이 여러 속성을
    가리킨다. 상품군을 좁히는 일은 호출부(applicable_properties)가 한다.
    """
    buckets: dict[str, list[Property]] = {}
    for prop in properties().values():
        for name in (prop.label, *prop.aliases):
            if name:
                buckets.setdefault(_normalize(name), []).append(prop)
    return sorted(
        ((name, tuple(props)) for name, props in buckets.items()),
        key=lambda pair: -len(pair[0]),
    )


def properties_mentioned(question: str) -> list[Property]:
    """질의에 언급된 속성. 같은 라벨의 상품군별 변형을 모두 돌려준다."""
    haystack = _normalize(question)
    seen: set[str] = set()
    found: list[Property] = []
    for name, props in _label_index():
        if len(name) < 2 or name not in haystack:
            continue
        for prop in props:
            if prop.uri not in seen:
                seen.add(prop.uri)
                found.append(prop)
    return found


def names_mentioned(question: str) -> list[str]:
    """질의에 등장한 속성 이름(라벨 또는 별칭)의 목록. 중복 판정을 피하는 데 쓴다."""
    haystack = _normalize(question)
    return [name for name, _ in _label_index() if len(name) >= 2 and name in haystack]


@lru_cache(maxsize=1)
def _concepts_by_class() -> dict[str, tuple[Concept, ...]]:
    """개념 클래스(fp:CreditRating 등) → 그 클래스의 값 목록."""
    g = graph()
    buckets: dict[str, list[Concept]] = {}
    for scheme in schemes().values():
        for concept in scheme.concepts:
            for cls in g.objects(URIRef(concept.uri), RDF.type):
                buckets.setdefault(str(cls), []).append(concept)
    return {cls: tuple(items) for cls, items in buckets.items()}


def concepts_in_range(range_uri: str) -> tuple[Concept, ...]:
    """속성의 rdfs:range가 가리키는 값 목록. 열거형이 아니면 비어 있다."""
    return _concepts_by_class().get(range_uri, ())


def enum_properties_mentioned(question: str) -> list[tuple[Property, tuple[Concept, ...]]]:
    """질의에 언급된 열거형 속성과 그 허용값. 값 도메인 검증의 입력이다."""
    out = []
    for prop in properties_mentioned(question):
        if not prop.range:
            continue
        allowed = concepts_in_range(prop.range)
        if allowed:
            out.append((prop, allowed))
    return out


def stats() -> dict:
    """적재 상태 확인용."""
    return {
        "triples": len(graph()),
        "schemes": len(schemes()),
        "concepts": sum(len(s.concepts) for s in schemes().values()),
        "properties": len(properties()),
        "unavailable": len(unavailable_properties()),
        "partial": len(partial_properties()),
    }
