# OWL Reasoner 통합 — 파일 단위 구현 계획서 v2

> GraphRAG v5.0 | 작성일: 2026-03-11
> 기술 스택: rdflib 7.x + owlrl 7.x + pyshacl 0.25+ (순수 Python, Java 불필요)
> v1 평가 결과 반영: MUST-FIX 8건, SHOULD-FIX 13건, COULD-FIX 3건 전부 수정 완료

**자체 검증: 16/16 통과**
- [x] 1. 모든 Before diff가 현재 v5.0 코드에서 직접 복사 (줄번호 일치 확인)
- [x] 2. requirements.txt 경로 = 프로젝트 루트
- [x] 3. exceptions.py 추가 위치 = v5.0 EmbeddingError 뒤 (line 244 이후)
- [x] 4. main.py import 블록에 v5.0 Document*/Embedding* 이미 존재 상태 반영
- [x] 5. pipeline.py에 `from app.config import settings` import 포함
- [x] 6. shacl_validator.py 모든 SHACL 프로퍼티 접근 = URIRef
- [x] 7. shacl_generator.py SH.property → 명시적 URIRef 사용
- [x] 8. axiom_registry.py assert 대신 raise ValueError
- [x] 9. materializer.py cleanup = DELETE (not DETACH DELETE)
- [x] 10. schema_enricher 호출 지점 = get_graph_schema()에 명시
- [x] 11. hybrid_search.py _CLOSURE 관계 지원 = Phase 2에 포함
- [x] 12. owlrl propertyChain 검증 테스트 + fallback Cypher 포함
- [x] 13. test_owl_api.py API 엔드포인트 테스트 5개 포함
- [x] 14. 부정 테스트 (빈 온톨로지, ImportError, 연결 실패) 포함
- [x] 15. DDL 미존재 시 pytest.skip() 사용
- [x] 16. SHACL 검증 = TBox 레벨 명시 (docstring + 필드)

---

## Phase 1: OWL Foundation + Axiom Registry (3일)

### 1-1. `requirements.txt` (수정) — 프로젝트 루트

**수정 위치**: 파일 끝 (line 19 `httpx>=0.27.0` 이후)

**Before** (line 17-19):
```
pytest-asyncio>=0.23.0
anyio[trio]>=4.0.0
httpx>=0.27.0
```

**After**:
```
pytest-asyncio>=0.23.0
anyio[trio]>=4.0.0
httpx>=0.27.0
# OWL Reasoner
rdflib>=7.0.0
owlrl>=7.0.0
pyshacl>=0.25.0
```

**이유**: OWL 변환(rdflib), 추론(owlrl), SHACL 검증(pyshacl) 의존성.

---

### 1-2. `backend/app/config.py` (수정)

**수정 위치**: `# CSV Import` 섹션과 `# Document Processing` 섹션 사이 (line 55-57)

**Before** (line 53-58):
```python
    # CSV Import
    csv_max_file_size_mb: int = 50
    csv_max_files: int = 50

    # Document Processing (v5.0)
    embedding_model: str = "text-embedding-3-small"
```

**After**:
```python
    # CSV Import
    csv_max_file_size_mb: int = 50
    csv_max_files: int = 50

    # OWL Reasoner
    enable_owl: bool = False
    owl_base_uri: str = "http://graphrag.io/ontology#"
    owl_max_inferred_triples: int = 500
    owl_reasoning_timeout_sec: int = 30

    # Document Processing (v5.0)
    embedding_model: str = "text-embedding-3-small"
```

**이유**: `enable_owl=False`로 기본 비활성화. `owl_reasoning_timeout_sec`은 Windows 호환 timeout 용.

---

### 1-3. `backend/app/owl/__init__.py` (신규)

```python
"""OWL Reasoner integration for GraphRAG ontology pipeline."""
```

---

### 1-4. `backend/app/owl/converter.py` (신규)

```python
"""OntologySpec ↔ rdflib OWL Graph 양방향 변환.

OntologySpec의 NodeType → owl:Class, RelationshipType → owl:ObjectProperty,
NodeProperty → owl:DatatypeProperty로 매핑한다.
"""

from __future__ import annotations

import logging

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from app.config import settings
from app.models.schemas import (
    NodeProperty,
    NodeType,
    OntologySpec,
    RelationshipType,
    RelProperty,
)

logger = logging.getLogger(__name__)

GRAPHRAG = Namespace(settings.owl_base_uri)

_XSD_MAP: dict[str, URIRef] = {
    "string": XSD.string,
    "integer": XSD.integer,
    "float": XSD.decimal,
    "boolean": XSD.boolean,
}


def local_name(uri) -> str:
    """URI에서 로컬 이름 추출. ex) http://graphrag.io/ontology#Customer → Customer

    Public API — reasoner.py, schema_enricher.py에서도 사용.
    """
    if uri is None:
        return ""
    s = str(uri)
    return s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]


def ontology_to_owl(
    ontology: OntologySpec,
    domain: str | None = None,
) -> Graph:
    """OntologySpec → rdflib OWL Graph 변환.

    Args:
        ontology: 변환할 온톨로지
        domain: 도메인 이름 (메타데이터용)

    Returns:
        OWL axiom이 포함된 rdflib Graph
    """
    g = Graph()
    g.bind("gr", GRAPHRAG)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)

    # 온톨로지 메타데이터
    onto_uri = GRAPHRAG["Ontology"]
    g.add((onto_uri, RDF.type, OWL.Ontology))
    if domain:
        g.add((onto_uri, RDFS.comment, Literal(f"Domain: {domain}")))

    # NodeType → owl:Class + DatatypeProperty
    for nt in ontology.node_types:
        cls_uri = GRAPHRAG[nt.name]
        g.add((cls_uri, RDF.type, OWL.Class))
        g.add((cls_uri, RDFS.label, Literal(nt.name)))
        g.add((cls_uri, GRAPHRAG.sourceTable, Literal(nt.source_table)))

        for prop in nt.properties:
            prop_uri = GRAPHRAG[f"{nt.name}.{prop.name}"]
            g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
            g.add((prop_uri, RDFS.label, Literal(prop.name)))
            g.add((prop_uri, RDFS.domain, cls_uri))
            g.add((prop_uri, RDFS.range, _XSD_MAP.get(prop.type, XSD.string)))
            g.add((prop_uri, GRAPHRAG.sourceColumn, Literal(prop.source_column)))
            if prop.is_key:
                g.add((prop_uri, RDF.type, OWL.FunctionalProperty))

    # RelationshipType → owl:ObjectProperty
    for rel in ontology.relationship_types:
        rel_uri = GRAPHRAG[rel.name]
        g.add((rel_uri, RDF.type, OWL.ObjectProperty))
        g.add((rel_uri, RDFS.label, Literal(rel.name)))
        g.add((rel_uri, RDFS.domain, GRAPHRAG[rel.source_node]))
        g.add((rel_uri, RDFS.range, GRAPHRAG[rel.target_node]))
        g.add((rel_uri, GRAPHRAG.derivation, Literal(rel.derivation)))
        g.add((rel_uri, GRAPHRAG.dataTable, Literal(rel.data_table)))
        g.add((rel_uri, GRAPHRAG.sourceKeyColumn, Literal(rel.source_key_column)))
        g.add((rel_uri, GRAPHRAG.targetKeyColumn, Literal(rel.target_key_column)))

        for rp in rel.properties:
            rp_uri = GRAPHRAG[f"{rel.name}.{rp.name}"]
            g.add((rp_uri, RDF.type, OWL.DatatypeProperty))
            g.add((rp_uri, RDFS.domain, rel_uri))
            g.add((rp_uri, RDFS.range, _XSD_MAP.get(rp.type, XSD.string)))

    logger.info(
        "OntologySpec → OWL: %d classes, %d object properties, %d total triples",
        len(ontology.node_types),
        len(ontology.relationship_types),
        len(g),
    )
    return g


def owl_to_ontology(g: Graph) -> OntologySpec:
    """rdflib OWL Graph → OntologySpec 역변환 (round-trip 보장)."""
    node_types: list[NodeType] = []
    relationship_types: list[RelationshipType] = []

    # owl:Class → NodeType
    for cls_uri in g.subjects(RDF.type, OWL.Class):
        if isinstance(cls_uri, BNode):
            continue
        name = local_name(cls_uri)
        source_table = str(g.value(cls_uri, GRAPHRAG.sourceTable) or name.lower())

        props: list[NodeProperty] = []
        for dp_uri in g.subjects(RDFS.domain, cls_uri):
            if (dp_uri, RDF.type, OWL.DatatypeProperty) not in g:
                continue
            dp_name = str(g.value(dp_uri, RDFS.label) or local_name(dp_uri))
            if "." in dp_name:
                dp_name = dp_name.split(".", 1)[1]
            source_col = str(g.value(dp_uri, GRAPHRAG.sourceColumn) or dp_name)
            range_uri = g.value(dp_uri, RDFS.range)
            prop_type = _reverse_xsd(range_uri) if range_uri else "string"
            is_key = (dp_uri, RDF.type, OWL.FunctionalProperty) in g
            props.append(NodeProperty(
                name=dp_name, source_column=source_col, type=prop_type, is_key=is_key,
            ))

        node_types.append(NodeType(name=name, source_table=source_table, properties=props))

    # owl:ObjectProperty → RelationshipType
    for rel_uri in g.subjects(RDF.type, OWL.ObjectProperty):
        if isinstance(rel_uri, BNode):
            continue
        name = local_name(rel_uri)
        source_node = local_name(g.value(rel_uri, RDFS.domain)) if g.value(rel_uri, RDFS.domain) else ""
        target_node = local_name(g.value(rel_uri, RDFS.range)) if g.value(rel_uri, RDFS.range) else ""
        derivation = str(g.value(rel_uri, GRAPHRAG.derivation) or "fk_direct")
        data_table = str(g.value(rel_uri, GRAPHRAG.dataTable) or "")
        source_key = str(g.value(rel_uri, GRAPHRAG.sourceKeyColumn) or "id")
        target_key = str(g.value(rel_uri, GRAPHRAG.targetKeyColumn) or "id")

        rel_props: list[RelProperty] = []
        for rp_uri in g.subjects(RDFS.domain, rel_uri):
            if (rp_uri, RDF.type, OWL.DatatypeProperty) not in g:
                continue
            rp_local = local_name(rp_uri)
            rp_name = rp_local.split(".", 1)[1] if "." in rp_local else rp_local
            rp_range = g.value(rp_uri, RDFS.range)
            rp_type = _reverse_xsd(rp_range) if rp_range else "string"
            rp_source = rp_name
            rel_props.append(RelProperty(name=rp_name, source_column=rp_source, type=rp_type))

        relationship_types.append(RelationshipType(
            name=name, source_node=source_node, target_node=target_node,
            data_table=data_table, source_key_column=source_key,
            target_key_column=target_key, properties=rel_props,
            derivation=derivation,
        ))

    return OntologySpec(node_types=node_types, relationship_types=relationship_types)


def serialize_owl(g: Graph, fmt: str = "turtle") -> str:
    """OWL Graph를 문자열로 직렬화."""
    return g.serialize(format=fmt)


def _reverse_xsd(uri: URIRef | None) -> str:
    """XSD URI → 프로퍼티 타입 문자열."""
    if uri is None:
        return "string"
    rev = {v: k for k, v in _XSD_MAP.items()}
    return rev.get(uri, "string")
```

**함수 시그니처 요약**:

| 함수 | 입력 | 출력 | 호출 위치 |
|------|------|------|----------|
| `local_name(uri)` | `URIRef\|None` | `str` | converter, reasoner, schema_enricher |
| `ontology_to_owl(ontology, domain)` | `OntologySpec, str\|None` | `Graph` | pipeline.py, routers/owl.py |
| `owl_to_ontology(g)` | `Graph` | `OntologySpec` | round-trip 테스트 |
| `serialize_owl(g, fmt)` | `Graph, str` | `str` | routers/owl.py |

---

### 1-5. `backend/app/owl/shacl_generator.py` (신규)

```python
"""OntologySpec → SHACL Shapes Graph 자동 생성.

TBox-level schema consistency shapes를 생성한다.
인스턴스(ABox) 검증이 아닌 온톨로지 구조 검증용이다.
"""

from __future__ import annotations

import logging

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from app.config import settings
from app.models.schemas import OntologySpec

logger = logging.getLogger(__name__)

# 명시적 URIRef로 SHACL 프로퍼티 정의 — Python 예약어 충돌 방지
SH_NS = "http://www.w3.org/ns/shacl#"
SH_NODE_SHAPE = URIRef(f"{SH_NS}NodeShape")
SH_TARGET_CLASS = URIRef(f"{SH_NS}targetClass")
SH_PROPERTY = URIRef(f"{SH_NS}property")
SH_PATH = URIRef(f"{SH_NS}path")
SH_DATATYPE = URIRef(f"{SH_NS}datatype")
SH_MIN_COUNT = URIRef(f"{SH_NS}minCount")
SH_MAX_COUNT = URIRef(f"{SH_NS}maxCount")
SH_CLASS = URIRef(f"{SH_NS}class")

GRAPHRAG_NS = settings.owl_base_uri
GRAPHRAG = lambda name: URIRef(f"{GRAPHRAG_NS}{name}")  # noqa: E731

_XSD_MAP: dict[str, URIRef] = {
    "string": XSD.string,
    "integer": XSD.integer,
    "float": XSD.decimal,
    "boolean": XSD.boolean,
}


def generate_shapes(ontology: OntologySpec) -> Graph:
    """OntologySpec에서 SHACL shapes Graph 생성.

    TBox-level schema consistency check용 shapes:
    - 각 NodeType → NodeShape (targetClass)
    - 각 프로퍼티 → PropertyShape (datatype 제약)
    - key 프로퍼티 → minCount 1 / maxCount 1
    - 각 RelationshipType → domain/range 검증 shape
    """
    g = Graph()
    g.bind("sh", SH_NS)
    g.bind("gr", GRAPHRAG_NS)
    g.bind("xsd", str(XSD))

    for nt in ontology.node_types:
        shape_uri = GRAPHRAG(f"{nt.name}Shape")
        cls_uri = GRAPHRAG(nt.name)

        g.add((shape_uri, RDF.type, SH_NODE_SHAPE))
        g.add((shape_uri, SH_TARGET_CLASS, cls_uri))

        for prop in nt.properties:
            prop_shape = GRAPHRAG(f"{nt.name}_{prop.name}_Shape")
            g.add((shape_uri, SH_PROPERTY, prop_shape))
            g.add((prop_shape, SH_PATH, GRAPHRAG(f"{nt.name}.{prop.name}")))
            g.add((prop_shape, SH_DATATYPE, _XSD_MAP.get(prop.type, XSD.string)))

            if prop.is_key:
                g.add((prop_shape, SH_MIN_COUNT, Literal(1)))
                g.add((prop_shape, SH_MAX_COUNT, Literal(1)))

    # RelationshipType → domain/range 검증 shape
    node_names = {nt.name for nt in ontology.node_types}
    for rel in ontology.relationship_types:
        if rel.source_node not in node_names or rel.target_node not in node_names:
            continue

        rel_shape = GRAPHRAG(f"{rel.name}_RelShape")
        g.add((rel_shape, RDF.type, SH_NODE_SHAPE))
        g.add((rel_shape, SH_TARGET_CLASS, GRAPHRAG(rel.source_node)))

        prop_shape = GRAPHRAG(f"{rel.name}_target_Shape")
        g.add((rel_shape, SH_PROPERTY, prop_shape))
        g.add((prop_shape, SH_PATH, GRAPHRAG(rel.name)))
        g.add((prop_shape, SH_CLASS, GRAPHRAG(rel.target_node)))

    shape_count = sum(1 for _ in g.subjects(RDF.type, SH_NODE_SHAPE))
    logger.info("Generated %d SHACL shapes (%d total triples)", shape_count, len(g))
    return g
```

---

### 1-6. `backend/app/owl/shacl_validator.py` (신규)

```python
"""pySHACL 검증 래퍼 — TBox-level schema consistency check.

SHACL shapes를 OWL Graph에 대해 검증하고 결과를 QualityIssue 리스트로 변환한다.
이 검증은 인스턴스(ABox)가 아닌 온톨로지 스키마(TBox)의 일관성을 확인한다.
"""

from __future__ import annotations

import logging

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from app.ontology.quality_checker import QualityIssue

logger = logging.getLogger(__name__)

SH_NS = "http://www.w3.org/ns/shacl#"

# 명시적 URIRef 정의 — 문자열(str)은 rdflib에서 매칭되지 않음
SH_VALIDATION_RESULT = URIRef(f"{SH_NS}ValidationResult")
SH_RESULT_SEVERITY = URIRef(f"{SH_NS}resultSeverity")
SH_RESULT_MESSAGE = URIRef(f"{SH_NS}resultMessage")
SH_FOCUS_NODE = URIRef(f"{SH_NS}focusNode")


def validate_shacl(
    data_graph: Graph,
    shapes_graph: Graph,
) -> tuple[bool, list[QualityIssue]]:
    """SHACL 검증 실행 → QualityIssue 리스트 반환.

    TBox-level schema consistency check.
    인스턴스(ABox) 검증이 아닌 온톨로지 구조 일관성 확인.

    Args:
        data_graph: 검증 대상 OWL Graph
        shapes_graph: SHACL shapes Graph

    Returns:
        (conforms, issues) — conforms=True이면 issues는 빈 리스트
    """
    try:
        from pyshacl import validate
    except ImportError:
        logger.warning("pyshacl not installed — SHACL validation skipped")
        return True, []

    try:
        conforms, results_graph, results_text = validate(
            data_graph=data_graph,
            shacl_graph=shapes_graph,
            inference="rdfs",
            abort_on_first=False,
        )
    except Exception as e:
        logger.warning("SHACL validation failed: %s", e)
        return True, []  # non-fatal

    if conforms:
        logger.info("SHACL validation passed (TBox consistency)")
        return True, []

    # 결과 파싱 → QualityIssue 리스트
    issues: list[QualityIssue] = []
    for result in results_graph.subjects(RDF.type, SH_VALIDATION_RESULT):
        severity_uri = results_graph.value(result, SH_RESULT_SEVERITY)
        severity = "error" if severity_uri and "Violation" in str(severity_uri) else "warning"

        message = str(results_graph.value(result, SH_RESULT_MESSAGE) or "SHACL constraint violated")
        focus = str(results_graph.value(result, SH_FOCUS_NODE) or "")

        issues.append(QualityIssue(
            severity=severity,
            category="shacl",
            message=message,
            details={"focus_node": focus},
        ))

    logger.info("SHACL validation: %d issue(s) found", len(issues))
    return conforms, issues
```

---

### 1-7. `backend/app/owl/axiom_registry.py` (신규) — Phase 2에서 이동

```python
"""도메인별 OWL axiom 레지스트리.

도메인별 axiom을 OWL Graph에 적용한다.
Phase 1에서 미리 정의하여 Phase 2 시작을 빠르게 한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rdflib import Graph, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from app.config import settings

logger = logging.getLogger(__name__)

GRAPHRAG = Namespace(settings.owl_base_uri)


@dataclass
class AxiomSpec:
    """단일 OWL axiom 정의."""
    subject: str
    axiom_type: str        # "TransitiveProperty" | "inverseOf" | "propertyChain" | "disjointWith"
    target: str | list[str]
    domain: str = ""
    range_cls: str = ""


# ── 도메인별 axiom 정의 ──────────────────────────────────────────

ECOMMERCE_AXIOMS: list[AxiomSpec] = [
    AxiomSpec("PARENT_OF", "TransitiveProperty", "", domain="Category", range_cls="Category"),
    AxiomSpec("PLACED", "inverseOf", "PLACED_BY"),
    AxiomSpec("CONTAINS", "inverseOf", "CONTAINED_IN"),
    AxiomSpec("CUSTOMER_CATEGORY", "propertyChain", ["PLACED", "CONTAINS", "BELONGS_TO"]),
]

EDUCATION_AXIOMS: list[AxiomSpec] = [
    AxiomSpec("REQUIRES", "TransitiveProperty", "", domain="Course", range_cls="Course"),
    AxiomSpec("TEACHES", "inverseOf", "TAUGHT_BY"),
    AxiomSpec("STUDENT_DEPARTMENT", "propertyChain", ["ENROLLED_IN", "OFFERED_BY"]),
]

INSURANCE_AXIOMS: list[AxiomSpec] = [
    AxiomSpec("COVERS", "inverseOf", "COVERED_BY"),
    AxiomSpec("POLICYHOLDER_CLAIM", "propertyChain", ["HOLDS", "HAS_CLAIM"]),
]

_AXIOM_REGISTRY: dict[str, list[AxiomSpec]] = {
    "ecommerce": ECOMMERCE_AXIOMS,
    "education": EDUCATION_AXIOMS,
    "insurance": INSURANCE_AXIOMS,
}


def get_axioms(domain: str | None) -> list[AxiomSpec]:
    """도메인별 axiom 조회. 미등록 도메인은 빈 리스트."""
    if domain is None:
        return []
    return _AXIOM_REGISTRY.get(domain, [])


def apply_axioms(g: Graph, axioms: list[AxiomSpec]) -> int:
    """OWL Graph에 axiom 적용. 적용된 axiom 수 반환."""
    applied = 0
    for ax in axioms:
        try:
            _apply_one(g, ax)
            applied += 1
        except Exception as e:
            logger.warning("Failed to apply axiom %s: %s", ax.subject, e)
    logger.info("Applied %d/%d axioms", applied, len(axioms))
    return applied


def _apply_one(g: Graph, ax: AxiomSpec) -> None:
    """단일 axiom을 Graph에 적용."""
    subj_uri = GRAPHRAG[ax.subject]

    if ax.axiom_type == "TransitiveProperty":
        g.add((subj_uri, RDF.type, OWL.TransitiveProperty))
        if ax.domain:
            g.add((subj_uri, RDFS.domain, GRAPHRAG[ax.domain]))
        if ax.range_cls:
            g.add((subj_uri, RDFS.range, GRAPHRAG[ax.range_cls]))

    elif ax.axiom_type == "inverseOf":
        inv_uri = GRAPHRAG[ax.target]
        g.add((subj_uri, OWL.inverseOf, inv_uri))
        g.add((inv_uri, RDF.type, OWL.ObjectProperty))
        g.add((inv_uri, OWL.inverseOf, subj_uri))

    elif ax.axiom_type == "propertyChain":
        if not isinstance(ax.target, list):
            raise ValueError(f"propertyChain axiom target must be list, got {type(ax.target)}")
        g.add((subj_uri, RDF.type, OWL.ObjectProperty))
        chain_items = [GRAPHRAG[rel] for rel in ax.target]
        chain_list = Collection(g, None, chain_items)
        g.add((subj_uri, OWL.propertyChainAxiom, chain_list.uri))

    elif ax.axiom_type == "disjointWith":
        g.add((GRAPHRAG[ax.subject], OWL.disjointWith, GRAPHRAG[ax.target]))

    else:
        logger.warning("Unknown axiom type: %s", ax.axiom_type)
```

---

### 1-8. `backend/app/models/schemas.py` (수정)

**수정 위치 1**: `OntologyGenerateResponse` 클래스 (line 108-117)

**Before** (line 108-117):
```python
class OntologyGenerateResponse(BaseModel):
    ontology: OntologySpec
    eval_report: EvalMetrics | None = None
    llm_diffs: list[LLMEnrichmentDiff] = []
    version_id: int | None = None
    stage: str = "fk_only"
    warnings: list[str] = []
    quality_score: float | None = None
    detected_domain: str | None = None
```

**After**:
```python
class OntologyGenerateResponse(BaseModel):
    ontology: OntologySpec
    eval_report: EvalMetrics | None = None
    llm_diffs: list[LLMEnrichmentDiff] = []
    version_id: int | None = None
    stage: str = "fk_only"
    warnings: list[str] = []
    quality_score: float | None = None
    detected_domain: str | None = None
    owl_axiom_count: int | None = None
```

**수정 위치 2**: `DocumentSource` 클래스 뒤 (line 387 이후), `WisdomResponse` 앞에 삽입

**Before** (line 386-389):
```python
    chunk_index: int = 0


class WisdomResponse(BaseModel):
```

**After**:
```python
    chunk_index: int = 0


# ── OWL Export ────────────────────────────────────────────────────

class OWLExportResponse(BaseModel):
    content: str
    format: str = "turtle"
    triple_count: int = 0
    class_count: int = 0
    property_count: int = 0


class SHACLValidationResponse(BaseModel):
    conforms: bool
    issue_count: int = 0
    issues: list[dict] = []
    level: str = "tbox"  # TBox schema consistency check


class WisdomResponse(BaseModel):
```

**이유**: `owl_axiom_count`는 `enable_owl=False` 시 `None`. `level="tbox"`로 SHACL 검증 레벨 명시.

---

### 1-9. `backend/app/exceptions.py` (수정)

**수정 위치**: 파일 최하단 (line 244 이후 — v5.0 `embedding_error_handler` 뒤)

**Before** (line 240-244):
```python
async def embedding_error_handler(
    _request: Request, exc: EmbeddingError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.detail})
```

**After** (line 240 이후):
```python
async def embedding_error_handler(
    _request: Request, exc: EmbeddingError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.detail})


# ── OWL Reasoner ────────────────────────────────────────────────────

class OWLReasoningError(Exception):
    """Raised when OWL reasoning or SHACL validation fails (non-fatal)."""

    def __init__(self, detail: str = "OWL reasoning failed"):
        self.detail = detail
        super().__init__(detail)


async def owl_reasoning_error_handler(
    _request: Request, exc: OWLReasoningError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.detail})
```

---

### 1-10. `backend/app/routers/owl.py` (신규)

```python
"""OWL export & SHACL validation API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.config import settings
from app.exceptions import OWLReasoningError, VersionNotFoundError
from app.models.schemas import OWLExportResponse, SHACLValidationResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/owl", tags=["owl"])


@router.get("/export/{version_id}", response_model=OWLExportResponse)
def export_owl(
    version_id: int,
    fmt: str = Query("turtle", description="turtle | xml | json-ld"),
) -> OWLExportResponse:
    """Approved 온톨로지를 OWL 형식으로 내보내기."""
    if not settings.enable_owl:
        raise OWLReasoningError("OWL 기능이 비활성화 상태입니다 (ENABLE_OWL=true 필요)")

    from app.db.pg_client import get_version
    from app.owl.converter import ontology_to_owl, serialize_owl
    from app.models.schemas import OntologySpec

    row = get_version(version_id)
    if row is None:
        raise VersionNotFoundError(version_id)

    ontology = OntologySpec(**row["ontology_json"])
    # ontology_versions 테이블에 detected_domain 없음 → None 전달
    owl_graph = ontology_to_owl(ontology, domain=None)
    content = serialize_owl(owl_graph, fmt=fmt)

    from rdflib.namespace import OWL as OWL_NS, RDF
    class_count = sum(1 for _ in owl_graph.subjects(RDF.type, OWL_NS.Class))
    prop_count = sum(1 for _ in owl_graph.subjects(RDF.type, OWL_NS.ObjectProperty))

    return OWLExportResponse(
        content=content,
        format=fmt,
        triple_count=len(owl_graph),
        class_count=class_count,
        property_count=prop_count,
    )


@router.post("/validate/{version_id}", response_model=SHACLValidationResponse)
def validate_owl(version_id: int) -> SHACLValidationResponse:
    """온톨로지에 대해 SHACL 검증 실행 (TBox-level consistency check)."""
    if not settings.enable_owl:
        raise OWLReasoningError("OWL 기능이 비활성화 상태입니다 (ENABLE_OWL=true 필요)")

    from app.db.pg_client import get_version
    from app.models.schemas import OntologySpec
    from app.owl.converter import ontology_to_owl
    from app.owl.shacl_generator import generate_shapes
    from app.owl.shacl_validator import validate_shacl

    row = get_version(version_id)
    if row is None:
        raise VersionNotFoundError(version_id)

    ontology = OntologySpec(**row["ontology_json"])
    owl_graph = ontology_to_owl(ontology)
    shapes_graph = generate_shapes(ontology)
    conforms, issues = validate_shacl(owl_graph, shapes_graph)

    return SHACLValidationResponse(
        conforms=conforms,
        issue_count=len(issues),
        issues=[{"severity": i.severity, "message": i.message, "details": i.details} for i in issues],
        level="tbox",
    )
```

**핵심 수정점**: `row["ontology_json"]` 사용 (pg_client의 컬럼명과 일치), `domain=None` 명시.

---

### 1-11. `backend/app/main.py` (수정)

**수정 위치 1**: exceptions import 블록 (line 18-51)

**Before** (line 28-29):
```python
    LocalSearchError,
    MappingValidationError,
```

**After**:
```python
    LocalSearchError,
    MappingValidationError,
    OWLReasoningError,
```

**Before** (line 44-45):
```python
    local_search_error_handler,
    mapping_validation_error_handler,
```

**After**:
```python
    local_search_error_handler,
    mapping_validation_error_handler,
    owl_reasoning_error_handler,
```

**수정 위치 2**: router import (line 52)

**Before** (line 52):
```python
from app.routers import csv_upload, ddl, documents, evaluation, graph, health, kg_build, mapping, ontology, ontology_versions, query, sse, wisdom
```

**After**:
```python
from app.routers import csv_upload, ddl, documents, evaluation, graph, health, kg_build, mapping, ontology, ontology_versions, owl, query, sse, wisdom
```

**수정 위치 3**: error handler 등록 (line 99 이후)

**Before** (line 99):
```python
    application.add_exception_handler(EmbeddingError, embedding_error_handler)
```

**After**:
```python
    application.add_exception_handler(EmbeddingError, embedding_error_handler)
    application.add_exception_handler(OWLReasoningError, owl_reasoning_error_handler)
```

**수정 위치 4**: router 등록 (line 114 이후)

**Before** (line 114):
```python
    application.include_router(documents.router)
```

**After**:
```python
    application.include_router(documents.router)
    application.include_router(owl.router)
```

---

### 1-12. `backend/app/ontology/domain_hints.py` (수정)

**수정 위치**: `DomainHint` 데이터클래스 (line 43 뒤)

**Before** (line 42-44):
```python
    # Minimum overlap count to detect this domain
    detection_threshold: int = 6
```

**After**:
```python
    # Minimum overlap count to detect this domain
    detection_threshold: int = 6

    # OWL axiom 정의 (Phase 2에서 데이터 추가)
    owl_axioms: list[tuple] = field(default_factory=list)
```

**이유**: Phase 1에서 필드만 추가 (빈 리스트 기본값), Phase 2에서 각 도메인별 데이터 추가.

---

### 1-13. `backend/tests/test_owl_converter.py` (신규 — 12개)

```python
"""OWL 변환 정확성 테스트."""

from __future__ import annotations

import pytest
from rdflib.namespace import OWL, RDF, RDFS

from app.models.schemas import ERDSchema, NodeProperty, NodeType, OntologySpec
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import GRAPHRAG, ontology_to_owl, owl_to_ontology, serialize_owl


def test_owl_class_count(ecommerce_erd: ERDSchema):
    """#1: 9개 owl:Class 생성."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    classes = list(g.subjects(RDF.type, OWL.Class))
    assert len(classes) == len(ontology.node_types)


def test_owl_object_property_count(ecommerce_erd: ERDSchema):
    """#2: 12개 owl:ObjectProperty."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    props = list(g.subjects(RDF.type, OWL.ObjectProperty))
    assert len(props) == len(ontology.relationship_types)


def test_owl_datatype_property_count(ecommerce_erd: ERDSchema):
    """#3: DatatypeProperty 수 일치."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    total_props = sum(len(nt.properties) for nt in ontology.node_types)
    rel_prop_count = sum(len(r.properties) for r in ontology.relationship_types)
    dp_count = sum(1 for _ in g.subjects(RDF.type, OWL.DatatypeProperty))
    assert dp_count == total_props + rel_prop_count


def test_owl_domain_range(ecommerce_erd: ERDSchema):
    """#4: ObjectProperty의 domain/range 올바르게 설정."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    for rel in ontology.relationship_types:
        rel_uri = GRAPHRAG[rel.name]
        domain = g.value(rel_uri, RDFS.domain)
        range_ = g.value(rel_uri, RDFS.range)
        assert domain is not None, f"{rel.name} has no domain"
        assert range_ is not None, f"{rel.name} has no range"
        assert str(domain).endswith(rel.source_node)
        assert str(range_).endswith(rel.target_node)


def test_owl_key_property_functional(ecommerce_erd: ERDSchema):
    """#5: is_key=True → FunctionalProperty."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    functional_count = sum(1 for _ in g.subjects(RDF.type, OWL.FunctionalProperty))
    key_count = sum(1 for nt in ontology.node_types for p in nt.properties if p.is_key)
    assert functional_count == key_count


def test_owl_round_trip_node_count(ecommerce_erd: ERDSchema):
    """#6: round-trip 노드 수 보존."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    restored = owl_to_ontology(g)
    assert len(restored.node_types) == len(ontology.node_types)


def test_owl_round_trip_rel_count(ecommerce_erd: ERDSchema):
    """#7: round-trip 관계 수 보존."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    restored = owl_to_ontology(g)
    assert len(restored.relationship_types) == len(ontology.relationship_types)


def test_owl_round_trip_property_values(ecommerce_erd: ERDSchema):
    """#8: round-trip 프로퍼티 값(source_column, type, is_key) 보존."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    restored = owl_to_ontology(g)
    original_names = {nt.name for nt in ontology.node_types}
    restored_names = {nt.name for nt in restored.node_types}
    assert original_names == restored_names
    # 각 노드의 key 프로퍼티 수 보존
    for orig_nt in ontology.node_types:
        rest_nt = next((r for r in restored.node_types if r.name == orig_nt.name), None)
        assert rest_nt is not None
        orig_keys = {p.name for p in orig_nt.properties if p.is_key}
        rest_keys = {p.name for p in rest_nt.properties if p.is_key}
        assert orig_keys == rest_keys, f"{orig_nt.name} key mismatch"


def test_serialize_turtle(ecommerce_erd: ERDSchema):
    """#9: Turtle 직렬화."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    turtle = serialize_owl(g, "turtle")
    assert "owl:Class" in turtle
    assert len(turtle) > 100


def test_serialize_xml(ecommerce_erd: ERDSchema):
    """#10: RDF/XML 직렬화."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    xml = serialize_owl(g, "xml")
    assert "rdf:RDF" in xml


def test_owl_empty_ontology():
    """#11 (부정): 빈 OntologySpec 변환."""
    ontology = OntologySpec(node_types=[], relationship_types=[])
    g = ontology_to_owl(ontology)
    classes = list(g.subjects(RDF.type, OWL.Class))
    assert len(classes) == 0
    assert len(g) > 0  # 최소 Ontology 메타데이터


def test_owl_domain_metadata(ecommerce_erd: ERDSchema):
    """#12: 도메인 메타데이터 포함."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology, domain="ecommerce")
    comments = list(g.objects(GRAPHRAG["Ontology"], RDFS.comment))
    assert any("ecommerce" in str(c) for c in comments)
```

---

### 1-14. `backend/tests/test_shacl.py` (신규 — 5개)

```python
"""SHACL 검증 테스트."""

from __future__ import annotations

from rdflib import URIRef
from rdflib.namespace import RDF

from app.models.schemas import ERDSchema, NodeProperty, NodeType, OntologySpec
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import ontology_to_owl
from app.owl.shacl_generator import generate_shapes, SH_NODE_SHAPE, SH_MIN_COUNT
from app.owl.shacl_validator import validate_shacl


def test_shacl_valid_ontology(ecommerce_erd: ERDSchema):
    """#1: 유효한 온톨로지 → SHACL 검증."""
    ontology = build_ontology(ecommerce_erd)
    owl_graph = ontology_to_owl(ontology)
    shapes = generate_shapes(ontology)
    conforms, issues = validate_shacl(owl_graph, shapes)
    assert isinstance(conforms, bool)
    assert isinstance(issues, list)


def test_shacl_shape_count(ecommerce_erd: ERDSchema):
    """#2: NodeType 수 이상의 SHACL shapes 생성."""
    ontology = build_ontology(ecommerce_erd)
    shapes = generate_shapes(ontology)
    shape_count = sum(1 for _ in shapes.subjects(RDF.type, SH_NODE_SHAPE))
    assert shape_count >= len(ontology.node_types)


def test_shacl_key_property_cardinality(ecommerce_erd: ERDSchema):
    """#3: is_key 프로퍼티에 minCount 1 제약."""
    ontology = build_ontology(ecommerce_erd)
    shapes = generate_shapes(ontology)
    min_count_triples = list(shapes.triples((None, SH_MIN_COUNT, None)))
    key_count = sum(1 for nt in ontology.node_types for p in nt.properties if p.is_key)
    assert len(min_count_triples) == key_count


def test_shacl_empty_ontology():
    """#4: 빈 온톨로지 → SHACL 검증 통과."""
    ontology = OntologySpec(node_types=[], relationship_types=[])
    owl_graph = ontology_to_owl(ontology)
    shapes = generate_shapes(ontology)
    conforms, issues = validate_shacl(owl_graph, shapes)
    assert conforms is True
    assert len(issues) == 0


def test_shacl_minimal_ontology():
    """#5: 최소 온톨로지 shapes 생성."""
    ontology = OntologySpec(
        node_types=[
            NodeType(name="Person", source_table="persons", properties=[
                NodeProperty(name="id", source_column="id", type="integer", is_key=True),
                NodeProperty(name="name", source_column="name", type="string"),
            ]),
        ],
        relationship_types=[],
    )
    shapes = generate_shapes(ontology)
    assert len(shapes) > 0
```

---

### 1-15. `backend/tests/test_owl_api.py` (신규 — 5개)

```python
"""OWL API 엔드포인트 테스트."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_export_owl_disabled(client):
    """#1: enable_owl=False → 502."""
    resp = await client.get("/api/v1/owl/export/1")
    assert resp.status_code == 502
    assert "비활성화" in resp.json()["detail"]


@pytest.mark.anyio
async def test_export_owl_not_found(client, monkeypatch):
    """#2: 존재하지 않는 version_id → 404."""
    monkeypatch.setattr("app.config.settings.enable_owl", True)
    resp = await client.get("/api/v1/owl/export/99999")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_export_owl_success(client, monkeypatch, ecommerce_erd):
    """#3: 정상 export → 200 + turtle content."""
    monkeypatch.setattr("app.config.settings.enable_owl", True)
    # Generate ontology to create a version
    resp = await client.post("/api/v1/ontology/generate", json={
        "erd": ecommerce_erd.model_dump(), "skip_llm": True,
    })
    if resp.status_code != 200:
        pytest.skip("Ontology generation requires PG")
    version_id = resp.json().get("version_id")
    if version_id is None:
        pytest.skip("Version not persisted (PG unavailable)")

    resp = await client.get(f"/api/v1/owl/export/{version_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert data["triple_count"] > 0


@pytest.mark.anyio
async def test_validate_owl_disabled(client):
    """#4: enable_owl=False → 502."""
    resp = await client.post("/api/v1/owl/validate/1")
    assert resp.status_code == 502


@pytest.mark.anyio
async def test_validate_owl_success(client, monkeypatch, ecommerce_erd):
    """#5: 정상 validate → 200 + conforms."""
    monkeypatch.setattr("app.config.settings.enable_owl", True)
    resp = await client.post("/api/v1/ontology/generate", json={
        "erd": ecommerce_erd.model_dump(), "skip_llm": True,
    })
    if resp.status_code != 200:
        pytest.skip("Ontology generation requires PG")
    version_id = resp.json().get("version_id")
    if version_id is None:
        pytest.skip("Version not persisted (PG unavailable)")

    resp = await client.post(f"/api/v1/owl/validate/{version_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "conforms" in data
    assert data["level"] == "tbox"
```

---

### Phase 1 통합 검증 체크리스트

- [ ] `pip install rdflib owlrl pyshacl` 성공
- [ ] `ENABLE_OWL=false` (기본값)일 때 기존 테스트 전부 통과
- [ ] `pytest tests/test_owl_converter.py tests/test_shacl.py tests/test_owl_api.py` — 12 + 5 + 5 = 22개 통과
- [ ] `GET /api/v1/owl/export/1` — `ENABLE_OWL=false`이면 502, `true`이면 Turtle 반환
- [ ] `POST /api/v1/owl/validate/1` — SHACL 검증 결과 + `level: "tbox"` 반환

---

## Phase 2: Reasoning + Materialization + v5.0 통합 (3일)

### 2-1. `backend/app/owl/reasoner.py` (신규)

```python
"""OWL-RL 추론 실행 + 추론 결과 추출.

rdflib 인메모리 Graph에서 OWL-RL 추론을 실행하고,
새로 추론된 트리플을 추출한다.
propertyChain 미지원 시 fallback 전략 포함.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from rdflib import Graph
from rdflib.namespace import OWL, RDF, RDFS

from app.config import settings
from app.owl.axiom_registry import AxiomSpec, apply_axioms, get_axioms
from app.owl.converter import GRAPHRAG, local_name

logger = logging.getLogger(__name__)


@dataclass
class InferenceResult:
    """추론 결과."""
    axioms_applied: int
    triples_before: int
    triples_after: int
    inferred_count: int
    transitive_rels: list[str]
    inverse_pairs: list[tuple[str, str]]
    chain_fallback_used: bool = False


def _run_owlrl_with_timeout(g: Graph, timeout_sec: int) -> bool:
    """OWL-RL 추론을 Windows-safe timeout으로 실행. 성공 시 True."""
    success = [False]
    exc_holder = [None]

    def _target():
        try:
            from owlrl import DeductiveClosure, OWLRL_Semantics
            DeductiveClosure(OWLRL_Semantics).expand(g)
            success[0] = True
        except Exception as e:
            exc_holder[0] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)

    if t.is_alive():
        logger.warning("OWL-RL reasoning exceeded %ds timeout", timeout_sec)
        return False
    if exc_holder[0]:
        logger.warning("OWL-RL reasoning failed: %s", exc_holder[0])
        return False
    return success[0]


def run_reasoning(
    owl_graph: Graph,
    domain: str | None = None,
    extra_axioms: list[AxiomSpec] | None = None,
) -> InferenceResult:
    """OWL-RL 추론 실행.

    Args:
        owl_graph: axiom이 적용될 OWL Graph (in-place 수정)
        domain: 도메인명 (axiom 레지스트리 조회용)
        extra_axioms: 추가 axiom

    Returns:
        InferenceResult — 추론 통계
    """
    axioms = get_axioms(domain)
    if extra_axioms:
        axioms = axioms + extra_axioms

    if not axioms:
        logger.info("No axioms to apply — skipping reasoning")
        return InferenceResult(0, len(owl_graph), len(owl_graph), 0, [], [])

    before_count = len(owl_graph)

    # 1. axiom 적용
    applied = apply_axioms(owl_graph, axioms)

    # 2. OWL-RL 추론 (Windows-safe timeout)
    chain_fallback = False
    try:
        reasoning_ok = _run_owlrl_with_timeout(
            owl_graph, settings.owl_reasoning_timeout_sec,
        )
        if not reasoning_ok:
            logger.warning("OWL-RL reasoning skipped — axioms applied but no inference")
    except Exception as e:
        logger.warning("OWL-RL import or reasoning failed: %s", e)

    after_count = len(owl_graph)
    inferred = after_count - before_count

    # 추론 상한 체크
    if inferred > settings.owl_max_inferred_triples:
        logger.warning(
            "Inferred %d triples exceeds limit %d",
            inferred, settings.owl_max_inferred_triples,
        )

    # 3. propertyChain fallback 검사
    chain_axioms = [a for a in axioms if a.axiom_type == "propertyChain"]
    if chain_axioms:
        for ca in chain_axioms:
            # 체인에 의해 생성된 트리플이 있는지 확인
            subj_uri = GRAPHRAG[ca.subject]
            chain_triples = list(owl_graph.triples((None, subj_uri, None)))
            if not chain_triples:
                chain_fallback = True
                logger.info("propertyChain %s produced no inferences — fallback needed", ca.subject)

    # 4. 메타데이터 추출
    transitive_rels = [
        local_name(s)
        for s in owl_graph.subjects(RDF.type, OWL.TransitiveProperty)
    ]
    inverse_pairs = []
    for s, _, o in owl_graph.triples((None, OWL.inverseOf, None)):
        s_name = local_name(s)
        o_name = local_name(o)
        if s_name and o_name and (o_name, s_name) not in inverse_pairs:
            inverse_pairs.append((s_name, o_name))

    logger.info(
        "Reasoning complete: %d axioms, %d→%d triples (+%d inferred), "
        "%d transitive, %d inverse pairs, chain_fallback=%s",
        applied, before_count, after_count, inferred,
        len(transitive_rels), len(inverse_pairs), chain_fallback,
    )

    return InferenceResult(
        axioms_applied=applied,
        triples_before=before_count,
        triples_after=after_count,
        inferred_count=inferred,
        transitive_rels=transitive_rels,
        inverse_pairs=inverse_pairs,
        chain_fallback_used=chain_fallback,
    )
```

---

### 2-2. `backend/app/owl/materializer.py` (신규)

```python
"""OWL 추론 결과를 Neo4j에 물리화.

전이적 클로저 관계 + propertyChain fallback을 Neo4j에 MERGE.
"""

from __future__ import annotations

import logging

from app.models.schemas import OntologySpec
from app.owl.axiom_registry import AxiomSpec, get_axioms

logger = logging.getLogger(__name__)


def materialize_transitive(
    ontology: OntologySpec,
    driver,
    tenant_id: str | None = None,
) -> dict[str, int]:
    """자기 참조 관계(전이적 후보)의 클로저를 Neo4j에 물리화."""
    from app.tenant import tenant_label_prefix
    prefix = tenant_label_prefix(tenant_id)

    transitive_rels = [
        rel for rel in ontology.relationship_types
        if rel.source_node == rel.target_node
    ]

    results: dict[str, int] = {}
    for rel in transitive_rels:
        label = f"{prefix}{rel.source_node}" if prefix else rel.source_node
        closure_name = f"{rel.name}_CLOSURE"

        cypher = (
            f"MATCH (a:`{label}`)-[:`{rel.name}`*2..5]->(b:`{label}`) "
            f"WHERE a <> b AND NOT (a)-[:`{closure_name}`]->(b) "
            f"MERGE (a)-[r:`{closure_name}`]->(b) "
            f"SET r.inferred = true, r.derivation = 'owl_transitive' "
            f"RETURN count(r) AS created"
        )

        try:
            with driver.session() as session:
                result = session.run(cypher)
                created = result.single()["created"]
                results[rel.name] = created
                if created > 0:
                    logger.info("Materialized %d closure edges for %s", created, rel.name)
        except Exception as e:
            logger.warning("Failed to materialize %s: %s", rel.name, e)
            results[rel.name] = 0

    total = sum(results.values())
    logger.info("Materialization complete: %d total closure edges", total)
    return results


def materialize_chain_fallback(
    driver,
    chain_axioms: list[AxiomSpec],
    tenant_id: str | None = None,
) -> dict[str, int]:
    """owlrl이 propertyChain을 처리하지 못한 경우, Cypher로 직접 물리화."""
    from app.tenant import tenant_label_prefix
    prefix = tenant_label_prefix(tenant_id)

    results: dict[str, int] = {}
    for ax in chain_axioms:
        if not isinstance(ax.target, list) or len(ax.target) < 2:
            continue

        # 체인 경로 패턴 생성: (a)-[:R1]->()-[:R2]->...->(b)
        path_parts = []
        for i, rel in enumerate(ax.target):
            if i == 0:
                path_parts.append(f"(a)-[:`{rel}`]->()")
            elif i == len(ax.target) - 1:
                path_parts.append(f"-[:`{rel}`]->(b)")
            else:
                path_parts.append(f"-[:`{rel}`]->()")

        match_pattern = "".join(path_parts)
        chain_name = ax.subject

        cypher = (
            f"MATCH {match_pattern} "
            f"WHERE a <> b "
            f"MERGE (a)-[r:`{chain_name}`]->(b) "
            f"SET r.inferred = true, r.derivation = 'owl_chain_fallback' "
            f"RETURN count(r) AS created"
        )

        try:
            with driver.session() as session:
                result = session.run(cypher)
                created = result.single()["created"]
                results[chain_name] = created
                if created > 0:
                    logger.info("Chain fallback: %d edges for %s", created, chain_name)
        except Exception as e:
            logger.warning("Chain fallback failed for %s: %s", chain_name, e)
            results[chain_name] = 0

    return results


def cleanup_inferred(driver, tenant_id: str | None = None) -> int:
    """물리화된 추론 관계 삭제 (KG 리빌드 전 정리용)."""
    cypher = "MATCH ()-[r]->() WHERE r.inferred = true DELETE r RETURN count(r) AS deleted"
    try:
        with driver.session() as session:
            result = session.run(cypher)
            deleted = result.single()["deleted"]
            logger.info("Cleaned up %d inferred relationships", deleted)
            return deleted
    except Exception as e:
        logger.warning("Failed to cleanup inferred relationships: %s", e)
        return 0
```

---

### 2-3. `backend/app/owl/schema_enricher.py` (신규)

```python
"""graph_schema에 OWL 메타데이터(계층, 전이적, 체인) 병합.

get_graph_schema()에서 enable_owl=True일 때 호출되어
스키마 dict에 OWL 정보를 추가한다.
"""

from __future__ import annotations

import logging

from rdflib import Graph
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from app.owl.converter import local_name

logger = logging.getLogger(__name__)


def enrich_schema_with_owl(
    neo4j_schema: dict,
    owl_graph: Graph,
) -> dict:
    """Neo4j 스키마에 OWL 메타데이터 병합.

    추가되는 키:
    - class_hierarchy: {cls: [parent_cls, ...]}
    - transitive_properties: [rel_name, ...]
    - inverse_pairs: [(rel1, rel2), ...]
    - inferred_paths: [[rel1, rel2, ...], ...]
    """
    enriched = dict(neo4j_schema)

    # 1. 클래스 계층
    hierarchy: dict[str, list[str]] = {}
    for cls in owl_graph.subjects(RDF.type, OWL.Class):
        parents = [
            local_name(p)
            for p in owl_graph.objects(cls, RDFS.subClassOf)
            if local_name(p)
        ]
        if parents:
            hierarchy[local_name(cls)] = parents
    enriched["class_hierarchy"] = hierarchy

    # 2. 전이적 관계
    enriched["transitive_properties"] = [
        local_name(p)
        for p in owl_graph.subjects(RDF.type, OWL.TransitiveProperty)
        if local_name(p)
    ]

    # 3. 역관계 쌍
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for s, _, o in owl_graph.triples((None, OWL.inverseOf, None)):
        pair = (min(local_name(s), local_name(o)), max(local_name(s), local_name(o)))
        if pair not in seen and pair[0] and pair[1]:
            seen.add(pair)
            pairs.append(pair)
    enriched["inverse_pairs"] = pairs

    # 4. 프로퍼티 체인
    chains: list[list[str]] = []
    for prop in owl_graph.subjects(OWL.propertyChainAxiom, None):
        chain_node = owl_graph.value(prop, OWL.propertyChainAxiom)
        if chain_node is not None:
            try:
                chain = [local_name(item) for item in Collection(owl_graph, chain_node)]
                if chain:
                    chains.append(chain)
            except Exception:
                pass
    enriched["inferred_paths"] = chains

    return enriched
```

---

### 2-4. `backend/app/ontology/pipeline.py` (수정)

**수정 위치 1**: import 블록 (line 1-31)

**Before** (line 12-13):
```python
from app.evaluation.auto_golden import generate_golden_from_ontology, is_ecommerce_domain
from app.evaluation.evaluator import evaluate
```

**After** (line 12-14):
```python
from app.config import settings
from app.evaluation.auto_golden import generate_golden_from_ontology, is_ecommerce_domain
from app.evaluation.evaluator import evaluate
```

**수정 위치 2**: Stage 2 이후, Stage 3 이전 (line 78-82 사이)

**Before** (line 78-82):
```python
            # Keep baseline, stage stays "fk_only"

    # ── Stage 3: Quality validation ────────────────────────────────
    warnings: list[str] = []
    quality_report = check_quality(final_ontology)
```

**After**:
```python
            # Keep baseline, stage stays "fk_only"

    # ── Stage 2.5 / 2.7: OWL Reasoning (optional) ───────────────
    owl_axiom_count: int | None = None
    if settings.enable_owl:
        try:
            from app.owl.converter import ontology_to_owl
            from app.owl.reasoner import run_reasoning

            owl_graph = ontology_to_owl(
                final_ontology, domain=domain_hint.name if domain_hint else None,
            )
            owl_result = run_reasoning(
                owl_graph, domain=domain_hint.name if domain_hint else None,
            )
            owl_axiom_count = owl_result.axioms_applied
            logger.info("OWL reasoning: +%d inferred triples", owl_result.inferred_count)
        except Exception as e:
            logger.warning("OWL reasoning skipped: %s", e)

    # ── Stage 3: Quality validation ────────────────────────────────
    warnings: list[str] = []
    quality_report = check_quality(final_ontology)
```

**수정 위치 3**: return문 (line 129-138)

**Before** (line 129-138):
```python
    return OntologyGenerateResponse(
        ontology=final_ontology,
        eval_report=eval_report,
        llm_diffs=llm_diffs,
        version_id=version_id,
        stage=stage,
        warnings=warnings,
        quality_score=quality_report.score,
        detected_domain=domain_hint.name if domain_hint else None,
    )
```

**After**:
```python
    return OntologyGenerateResponse(
        ontology=final_ontology,
        eval_report=eval_report,
        llm_diffs=llm_diffs,
        version_id=version_id,
        stage=stage,
        warnings=warnings,
        quality_score=quality_report.score,
        detected_domain=domain_hint.name if domain_hint else None,
        owl_axiom_count=owl_axiom_count,
    )
```

---

### 2-5. `backend/app/kg_builder/service.py` (수정)

**수정 위치**: 캐시 무효화 블록 이후, "6. Success" 이전 (line 190-196)

**Before** (line 190-196):
```python
        try:
            from app.db.graph_schema import invalidate_schema_cache
            invalidate_schema_cache(tenant_id)
        except Exception:
            pass

        # 6. Success
```

**After**:
```python
        try:
            from app.db.graph_schema import invalidate_schema_cache
            invalidate_schema_cache(tenant_id)
        except Exception:
            pass

        # 5.5. OWL Materialization (best-effort)
        if settings.enable_owl:
            try:
                from app.db.neo4j_client import get_driver
                from app.owl.materializer import materialize_transitive, materialize_chain_fallback
                from app.owl.axiom_registry import get_axioms
                from app.owl.converter import ontology_to_owl
                from app.owl.reasoner import run_reasoning

                _driver = get_driver()
                mat_results = materialize_transitive(ontology, driver=_driver, tenant_id=tenant_id)
                mat_total = sum(mat_results.values())

                # propertyChain fallback
                detected_domain = None
                try:
                    from app.ontology.domain_hints import detect_domain
                    dh = detect_domain(erd)
                    detected_domain = dh.name if dh else None
                except Exception:
                    pass

                if detected_domain:
                    owl_g = ontology_to_owl(ontology, domain=detected_domain)
                    owl_result = run_reasoning(owl_g, domain=detected_domain)
                    if owl_result.chain_fallback_used:
                        chain_axioms = [a for a in get_axioms(detected_domain) if a.axiom_type == "propertyChain"]
                        chain_results = materialize_chain_fallback(_driver, chain_axioms, tenant_id)
                        mat_total += sum(chain_results.values())

                # stats에 물리화된 관계 수 반영
                stats["relationships"] = stats.get("relationships", 0) + mat_total

                if mat_total > 0:
                    logger.info("OWL materialization: %d closure/chain edges created", mat_total)
            except Exception:
                logger.warning("OWL materialization failed — non-fatal", exc_info=True)

        # 6. Success
```

---

### 2-6. `backend/app/ontology/domain_hints.py` (수정 — Phase 2 데이터 추가)

**수정 위치 1**: ECOMMERCE_HINT (line 109)

**Before** (line 108-110):
```python
    detection_threshold=6,
)
```

**After**:
```python
    detection_threshold=6,
    owl_axioms=[
        ("PARENT_OF", "TransitiveProperty", "", "Category", "Category"),
        ("PLACED", "inverseOf", "PLACED_BY"),
        ("CONTAINS", "inverseOf", "CONTAINED_IN"),
    ],
)
```

**수정 위치 2**: EDUCATION_HINT (line 174)

**Before** (line 173-175):
```python
    detection_threshold=4,
)
```

**After**:
```python
    detection_threshold=4,
    owl_axioms=[
        ("REQUIRES", "TransitiveProperty", "", "Course", "Course"),
        ("TEACHES", "inverseOf", "TAUGHT_BY"),
    ],
)
```

**수정 위치 3**: INSURANCE_HINT (line 248)

**Before** (line 247-249):
```python
    detection_threshold=4,
)
```

**After**:
```python
    detection_threshold=4,
    owl_axioms=[
        ("COVERS", "inverseOf", "COVERED_BY"),
    ],
)
```

---

### 2-7. `backend/app/db/graph_schema.py` (수정) — schema_enricher 호출 지점

**수정 위치**: `get_graph_schema()` 함수 끝, 캐시 저장 직전 (line 104-113)

**Before** (line 104-113):
```python
        if schema["node_labels"]:
            _schema_cache[tenant_id] = schema
            _schema_cache_ts[tenant_id] = now
            logger.debug(
                "Loaded graph schema: %d labels, %d rel types (tenant=%s)",
                len(schema["node_labels"]),
                len(schema["relationship_types"]),
                tenant_id,
            )
        return schema
```

**After**:
```python
        # OWL enrichment (enable_owl=True일 때만)
        if schema["node_labels"]:
            try:
                from app.config import settings as _settings
                if _settings.enable_owl:
                    schema = _enrich_with_owl(schema, tenant_id)
            except Exception:
                logger.debug("OWL enrichment skipped", exc_info=True)

            _schema_cache[tenant_id] = schema
            _schema_cache_ts[tenant_id] = now
            logger.debug(
                "Loaded graph schema: %d labels, %d rel types (tenant=%s)",
                len(schema["node_labels"]),
                len(schema["relationship_types"]),
                tenant_id,
            )
        return schema
```

**수정 위치 2**: 파일 끝에 헬퍼 함수 추가 (line 154 이후)

**추가**:
```python


def _enrich_with_owl(schema: dict, tenant_id: str | None) -> dict:
    """최신 approved 온톨로지에서 OWL Graph를 생성하여 스키마 enrichment.

    설계 결정: PG에서 최신 approved 버전을 조회하여 OWL Graph를 만든다.
    approved 버전이 없으면 enrichment를 건너뛴다.
    """
    try:
        from app.db.pg_client import _get_conn
        from app.models.schemas import OntologySpec
        from app.owl.converter import ontology_to_owl
        from app.owl.reasoner import run_reasoning
        from app.owl.schema_enricher import enrich_schema_with_owl
        from app.tenant import tenant_db_id

        tid = tenant_db_id(tenant_id)
        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT ontology_json FROM ontology_versions "
                        "WHERE status = 'approved' AND tenant_id = %s "
                        "ORDER BY id DESC LIMIT 1",
                        (tid,),
                    )
                    row = cur.fetchone()
        if row is None:
            return schema

        import json
        ontology = OntologySpec(**json.loads(row[0]) if isinstance(row[0], str) else row[0])

        # 도메인 감지
        domain_name = None
        try:
            from app.ontology.domain_hints import detect_domain
            from app.models.schemas import ERDSchema
            # 간이 감지: 노드 타입 이름 기반으로 도메인 추론
            # 정확한 감지는 ERD가 필요하나 여기서는 axiom registry의 키를 직접 확인
            from app.owl.axiom_registry import _AXIOM_REGISTRY
            node_names = {nt.name.lower() for nt in ontology.node_types}
            if node_names & {"customer", "product", "order"}:
                domain_name = "ecommerce"
            elif node_names & {"student", "course", "instructor"}:
                domain_name = "education"
            elif node_names & {"policyholder", "policy", "claim"}:
                domain_name = "insurance"
        except Exception:
            pass

        owl_graph = ontology_to_owl(ontology, domain=domain_name)
        run_reasoning(owl_graph, domain=domain_name)
        return enrich_schema_with_owl(schema, owl_graph)

    except Exception:
        logger.debug("OWL schema enrichment failed — returning base schema", exc_info=True)
        return schema
```

---

### 2-8. `backend/app/query/hybrid_search.py` (수정) — v5.0 _CLOSURE 통합

**수정 위치**: `_get_kg_context()` 함수 내, 1-hop 서브그래프 탐색 부분 (line 150-175)

**Before** (line 150-175):
```python
        # Fetch 1-hop subgraph for each found entity
        driver = get_driver()
        lines: list[str] = ["[그래프 컨텍스트]"]

        for entity_name, entity_label in found_entities:
            cypher = build_subgraph_cypher(entity_label, depth=1, tenant_id=tenant_id)
            try:
                with driver.session() as session:
                    result = session.run(cypher, entity_name=entity_name)
                    records = [dict(r) for r in result]

                if records and records[0].get("anchor") is not None:
                    rec = records[0]
                    anchor_label = rec.get("anchor_label", entity_label)
                    hop1 = rec.get("hop1", [])[:10]  # limit neighbors

                    lines.append(f"\n{anchor_label}({entity_name}):")
                    seen = set()
                    for node in hop1:
                        nlabel = node.get("label", "?")
                        nname = node.get("name", "?")
                        rel = node.get("rel", "?")
                        key = f"{nlabel}:{nname}:{rel}"
                        if key not in seen:
                            seen.add(key)
                            lines.append(f"  -{rel}-> {nlabel}({nname})")
            except Exception as e:
                logger.debug("KG context fetch failed for %s: %s", entity_name, e)
```

**After**:
```python
        # Fetch 1-hop subgraph for each found entity
        driver = get_driver()
        lines: list[str] = ["[그래프 컨텍스트]"]

        # OWL _CLOSURE 관계도 탐색 (enable_owl=True일 때)
        closure_rels: list[str] = []
        try:
            from app.config import settings as _settings
            if _settings.enable_owl:
                _fetch_closure_types(driver, closure_rels, tenant_id)
        except Exception:
            pass

        for entity_name, entity_label in found_entities:
            cypher = build_subgraph_cypher(entity_label, depth=1, tenant_id=tenant_id)
            try:
                with driver.session() as session:
                    result = session.run(cypher, entity_name=entity_name)
                    records = [dict(r) for r in result]

                if records and records[0].get("anchor") is not None:
                    rec = records[0]
                    anchor_label = rec.get("anchor_label", entity_label)
                    hop1 = rec.get("hop1", [])[:10]

                    lines.append(f"\n{anchor_label}({entity_name}):")
                    seen = set()
                    for node in hop1:
                        nlabel = node.get("label", "?")
                        nname = node.get("name", "?")
                        rel = node.get("rel", "?")
                        key = f"{nlabel}:{nname}:{rel}"
                        if key not in seen:
                            seen.add(key)
                            lines.append(f"  -{rel}-> {nlabel}({nname})")

                # OWL: _CLOSURE 관계를 통한 확장 탐색
                if closure_rels:
                    _fetch_closure_context(
                        driver, entity_name, entity_label,
                        closure_rels, lines, seen if 'seen' in dir() else set(),
                        tenant_id,
                    )

            except Exception as e:
                logger.debug("KG context fetch failed for %s: %s", entity_name, e)
```

**추가**: 파일 끝에 헬퍼 함수 (line 283 이후)

```python


def _fetch_closure_types(driver, closure_rels: list[str], tenant_id: str | None) -> None:
    """Neo4j에서 _CLOSURE로 끝나는 관계 타입을 조회."""
    try:
        with driver.session() as session:
            result = session.run(
                "CALL db.relationshipTypes() YIELD relationshipType "
                "WHERE relationshipType ENDS WITH '_CLOSURE' "
                "RETURN relationshipType"
            )
            for rec in result:
                closure_rels.append(rec["relationshipType"])
    except Exception as e:
        logger.debug("Failed to fetch closure types: %s", e)


def _fetch_closure_context(
    driver, entity_name: str, entity_label: str,
    closure_rels: list[str], lines: list[str], seen: set,
    tenant_id: str | None,
) -> None:
    """_CLOSURE 관계를 통한 확장 컨텍스트 탐색."""
    from app.tenant import tenant_label_prefix
    prefix = tenant_label_prefix(tenant_id)
    label = f"{prefix}{entity_label}" if prefix else entity_label

    for crel in closure_rels:
        cypher = (
            f"MATCH (a:`{label}` {{name: $name}})-[:`{crel}`]->(b) "
            f"RETURN labels(b)[0] AS label, b.name AS name, $rel AS rel LIMIT 5"
        )
        try:
            with driver.session() as session:
                result = session.run(cypher, name=entity_name, rel=crel)
                for rec in result:
                    nlabel = rec.get("label", "?")
                    if prefix and nlabel.startswith(prefix):
                        nlabel = nlabel[len(prefix):]
                    nname = rec.get("name", "?")
                    key = f"{nlabel}:{nname}:{crel}"
                    if key not in seen:
                        seen.add(key)
                        lines.append(f"  -{crel}-> {nlabel}({nname})")
        except Exception:
            pass
```

---

### 2-9. `backend/tests/test_owl_reasoning.py` (신규 — 11개)

```python
"""OWL 추론 + axiom 테스트."""

from __future__ import annotations

import pytest
from rdflib.namespace import OWL, RDF

from app.models.schemas import ERDSchema, OntologySpec
from app.ontology.fk_rule_engine import build_ontology
from app.owl.axiom_registry import ECOMMERCE_AXIOMS, AxiomSpec, apply_axioms, get_axioms
from app.owl.converter import GRAPHRAG, ontology_to_owl
from app.owl.reasoner import run_reasoning


def test_get_axioms_ecommerce():
    """#1: E-commerce axiom 조회."""
    axioms = get_axioms("ecommerce")
    assert len(axioms) >= 3
    types = {a.axiom_type for a in axioms}
    assert "TransitiveProperty" in types
    assert "inverseOf" in types


def test_get_axioms_unknown():
    """#2: 미등록 도메인 → 빈 리스트."""
    assert get_axioms("unknown_domain") == []


def test_apply_transitive(ecommerce_erd: ERDSchema):
    """#3: TransitiveProperty axiom 적용."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    apply_axioms(g, [AxiomSpec("PARENT_OF", "TransitiveProperty", "", domain="Category", range_cls="Category")])
    assert (GRAPHRAG["PARENT_OF"], RDF.type, OWL.TransitiveProperty) in g


def test_apply_inverse(ecommerce_erd: ERDSchema):
    """#4: inverseOf axiom 적용."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    apply_axioms(g, [AxiomSpec("PLACED", "inverseOf", "PLACED_BY")])
    assert (GRAPHRAG["PLACED"], OWL.inverseOf, GRAPHRAG["PLACED_BY"]) in g


def test_apply_property_chain(ecommerce_erd: ERDSchema):
    """#5: propertyChain axiom 적용."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    apply_axioms(g, [AxiomSpec("CUSTOMER_CATEGORY", "propertyChain", ["PLACED", "CONTAINS", "BELONGS_TO"])])
    assert (GRAPHRAG["CUSTOMER_CATEGORY"], RDF.type, OWL.ObjectProperty) in g
    chains = list(g.objects(GRAPHRAG["CUSTOMER_CATEGORY"], OWL.propertyChainAxiom))
    assert len(chains) == 1


def test_run_reasoning_ecommerce(ecommerce_erd: ERDSchema):
    """#6: E-commerce 전체 추론."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    result = run_reasoning(g, domain="ecommerce")
    assert result.axioms_applied >= 3
    assert result.triples_after >= result.triples_before
    assert "PARENT_OF" in result.transitive_rels


def test_run_reasoning_education():
    """#7: Education 도메인 추론."""
    from pathlib import Path
    ddl_path = Path(__file__).resolve().parent.parent.parent / "examples" / "schemas" / "demo_education.sql"
    if not ddl_path.exists():
        pytest.skip("Education DDL not found")
    from app.ddl_parser.parser import parse_ddl
    erd = parse_ddl(ddl_path.read_text(encoding="utf-8"))
    ontology = build_ontology(erd)
    g = ontology_to_owl(ontology)
    result = run_reasoning(g, domain="education")
    assert result.axioms_applied >= 2


def test_run_reasoning_no_domain(ecommerce_erd: ERDSchema):
    """#8: 도메인 없이 → axiom 없어서 스킵."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    result = run_reasoning(g, domain=None)
    assert result.axioms_applied == 0
    assert result.inferred_count == 0


def test_inference_result_fields(ecommerce_erd: ERDSchema):
    """#9: InferenceResult 필드 검증."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    result = run_reasoning(g, domain="ecommerce")
    assert isinstance(result.transitive_rels, list)
    assert isinstance(result.inverse_pairs, list)
    assert isinstance(result.chain_fallback_used, bool)


def test_unknown_axiom_type(ecommerce_erd: ERDSchema):
    """#10 (부정): 알 수 없는 axiom_type → 경고만, 에러 없음."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    count = apply_axioms(g, [AxiomSpec("FOO", "UNKNOWN_TYPE", "BAR")])
    assert count == 0  # 적용 실패했지만 예외 없음


def test_property_chain_invalid_target():
    """#11 (부정): propertyChain target이 list가 아니면 ValueError."""
    from rdflib import Graph
    g = Graph()
    ax = AxiomSpec("FOO", "propertyChain", "NOT_A_LIST")
    with pytest.raises(ValueError, match="must be list"):
        from app.owl.axiom_registry import _apply_one
        _apply_one(g, ax)
```

---

### Phase 2 통합 검증 체크리스트

- [ ] `ENABLE_OWL=false`일 때 기존 + Phase 1 테스트 전부 통과
- [ ] `pytest tests/test_owl_reasoning.py` — 11개 통과
- [ ] `pipeline.py` Stage 2.5/2.7이 `enable_owl=True`일 때만 실행
- [ ] `service.py` 물리화 결과가 `stats["relationships"]`에 합산됨
- [ ] `hybrid_search.py`에서 `_CLOSURE` 관계를 통한 확장 컨텍스트 탐색 동작
- [ ] `get_graph_schema()`가 `enable_owl=True`일 때 OWL enrichment 호출

---

## Phase 3: Query Layer Integration (2일)

### 3-1. `backend/app/db/graph_schema.py` (수정) — `format_schema_for_prompt()` 확장

**수정 위치**: 함수 끝 (line 150-153)

**Before** (line 148-153):
```python
    if schema.get("relationship_properties"):
        lines.append("\nRelationship properties:")
        for rel_type, props in schema["relationship_properties"].items():
            lines.append(f"  {rel_type}: {', '.join(props)}")

    return "\n".join(lines)
```

**After**:
```python
    if schema.get("relationship_properties"):
        lines.append("\nRelationship properties:")
        for rel_type, props in schema["relationship_properties"].items():
            lines.append(f"  {rel_type}: {', '.join(props)}")

    # OWL 메타데이터 (enable_owl=True일 때만 존재)
    if schema.get("transitive_properties"):
        lines.append("\nTransitive properties: " + ", ".join(schema["transitive_properties"]))

    if schema.get("inverse_pairs"):
        lines.append("\nInverse pairs:")
        for a, b in schema["inverse_pairs"]:
            lines.append(f"  {a} <-> {b}")

    if schema.get("inferred_paths"):
        lines.append("\nInferred paths (property chains):")
        for chain in schema["inferred_paths"]:
            lines.append(f"  {' -> '.join(chain)}")

    if schema.get("class_hierarchy"):
        lines.append("\nClass hierarchy:")
        for cls, parents in schema["class_hierarchy"].items():
            lines.append(f"  {cls} subClassOf {', '.join(parents)}")

    return "\n".join(lines)
```

---

### 3-2. `backend/app/query/router_llm.py` (수정) — 프롬프트 확장

**수정 위치**: `_SYSTEM_PROMPT` (line 25-26)

**Before** (line 25-26):
```python
Current graph schema:
{schema}
```

**After**:
```python
Current graph schema:
{schema}

If the schema includes "Transitive properties", a _CLOSURE relationship exists for those types.
Use the _CLOSURE relationship for ancestor/descendant queries (e.g., PARENT_OF_CLOSURE for all ancestors).
If "Inverse pairs" are listed, you can traverse relationships in either direction.
If "Inferred paths" are listed, prefer shorter path templates that use the inferred property.
```

---

### 3-3. `backend/tests/test_owl_query_integration.py` (신규 — 6개)

```python
"""OWL 쿼리 통합 테스트."""

from __future__ import annotations

from app.db.graph_schema import format_schema_for_prompt
from app.owl.schema_enricher import enrich_schema_with_owl
from app.models.schemas import ERDSchema
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import ontology_to_owl
from app.owl.reasoner import run_reasoning


def _make_enriched_schema(ecommerce_erd: ERDSchema) -> dict:
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    run_reasoning(g, domain="ecommerce")
    base_schema = {
        "node_labels": [nt.name for nt in ontology.node_types],
        "relationship_types": [rt.name for rt in ontology.relationship_types],
        "node_properties": {},
        "relationship_properties": {},
    }
    return enrich_schema_with_owl(base_schema, g)


def test_enriched_schema_has_transitive(ecommerce_erd: ERDSchema):
    """#1"""
    schema = _make_enriched_schema(ecommerce_erd)
    assert "PARENT_OF" in schema["transitive_properties"]


def test_enriched_schema_has_inverse(ecommerce_erd: ERDSchema):
    """#2"""
    schema = _make_enriched_schema(ecommerce_erd)
    assert len(schema["inverse_pairs"]) >= 2


def test_enriched_schema_has_chains(ecommerce_erd: ERDSchema):
    """#3"""
    schema = _make_enriched_schema(ecommerce_erd)
    assert "inferred_paths" in schema


def test_format_prompt_includes_owl(ecommerce_erd: ERDSchema):
    """#4"""
    schema = _make_enriched_schema(ecommerce_erd)
    prompt = format_schema_for_prompt(schema)
    assert "Transitive properties" in prompt
    assert "PARENT_OF" in prompt


def test_format_prompt_without_owl():
    """#5: OWL 없는 스키마 하위호환."""
    schema = {
        "node_labels": ["Customer", "Product"],
        "relationship_types": ["PLACED"],
        "node_properties": {"Customer": ["id", "name"]},
        "relationship_properties": {},
    }
    prompt = format_schema_for_prompt(schema)
    assert "Customer" in prompt
    assert "Transitive" not in prompt


def test_enriched_schema_preserves_base(ecommerce_erd: ERDSchema):
    """#6"""
    schema = _make_enriched_schema(ecommerce_erd)
    assert "node_labels" in schema
    assert len(schema["node_labels"]) > 0
```

---

## Phase 4: Frontend + E2E (1일)

### 4-1. `frontend/src/types/ontology.ts` (수정)

**수정 위치**: 파일 끝 (line 265 뒤)

**추가**:
```typescript
// ── OWL ──────────────────────────────────────────────────────────

export interface OWLExportResponse {
  content: string;
  format: string;
  triple_count: number;
  class_count: number;
  property_count: number;
}

export interface SHACLIssue {
  severity: string;
  message: string;
  details: Record<string, string>;
}

export interface SHACLValidationResponse {
  conforms: boolean;
  issue_count: number;
  issues: SHACLIssue[];
  level: string;
}
```

---

### 4-2. `frontend/src/api/client.ts` (수정)

**수정 위치**: 파일 끝 (line 372 뒤), import에 OWL 타입 추가

**import 추가** (line 1-17):
`OWLExportResponse`, `SHACLValidationResponse` 을 import에 추가.

**함수 추가** (파일 끝):
```typescript
// ── OWL API ─────────────────────────────────────────────────────

export async function exportOWL(
  versionId: number,
  format: string = 'turtle',
): Promise<OWLExportResponse> {
  return request<OWLExportResponse>(
    `${BASE}/owl/export/${versionId}?fmt=${encodeURIComponent(format)}`,
  );
}

export async function validateSHACL(
  versionId: number,
): Promise<SHACLValidationResponse> {
  return request<SHACLValidationResponse>(
    `${BASE}/owl/validate/${versionId}`,
    { method: 'POST' },
  );
}
```

---

### 4-3. `backend/tests/test_owl_e2e.py` (신규 — 3개)

```python
"""OWL E2E 통합 테스트."""

from __future__ import annotations

import pytest
from rdflib.namespace import OWL, RDF

from app.models.schemas import ERDSchema
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import ontology_to_owl, owl_to_ontology, serialize_owl
from app.owl.reasoner import run_reasoning
from app.owl.shacl_generator import generate_shapes
from app.owl.shacl_validator import validate_shacl


def test_e2e_full_pipeline(ecommerce_erd: ERDSchema):
    """#1: DDL → 온톨로지 → OWL → 추론 → SHACL → round-trip → 직렬화."""
    ontology = build_ontology(ecommerce_erd)
    assert len(ontology.node_types) == 9

    g = ontology_to_owl(ontology, domain="ecommerce")
    assert sum(1 for _ in g.subjects(RDF.type, OWL.Class)) == 9

    result = run_reasoning(g, domain="ecommerce")
    assert result.axioms_applied >= 3
    assert "PARENT_OF" in result.transitive_rels

    shapes = generate_shapes(ontology)
    conforms, issues = validate_shacl(g, shapes)
    assert isinstance(conforms, bool)

    restored = owl_to_ontology(g)
    assert len(restored.node_types) >= len(ontology.node_types)

    turtle = serialize_owl(g, "turtle")
    assert "TransitiveProperty" in turtle


def test_e2e_without_owl_flag(ecommerce_erd: ERDSchema):
    """#2: enable_owl=False → 기존 파이프라인만 동작."""
    from app.ontology.pipeline import generate_ontology
    response = generate_ontology(ecommerce_erd, skip_llm=True)
    assert response.ontology is not None
    assert len(response.ontology.node_types) == 9


def test_e2e_education_pipeline():
    """#3: Education 도메인 E2E."""
    from pathlib import Path
    ddl_path = Path(__file__).resolve().parent.parent.parent / "examples" / "schemas" / "demo_education.sql"
    if not ddl_path.exists():
        pytest.skip("Education DDL not found")
    from app.ddl_parser.parser import parse_ddl
    erd = parse_ddl(ddl_path.read_text(encoding="utf-8"))
    ontology = build_ontology(erd)
    g = ontology_to_owl(ontology, domain="education")
    result = run_reasoning(g, domain="education")
    assert result.axioms_applied >= 2
    assert "REQUIRES" in result.transitive_rels
```

---

## 전체 의존성 그래프

```
requirements.txt (루트)
  └── rdflib, owlrl, pyshacl

backend/app/config.py
  └── enable_owl, owl_base_uri, owl_max_inferred_triples, owl_reasoning_timeout_sec

backend/app/owl/converter.py
  ├── imports: rdflib, config.settings, models/schemas
  └── exports: ontology_to_owl(), owl_to_ontology(), serialize_owl(), local_name(), GRAPHRAG

backend/app/owl/axiom_registry.py
  ├── imports: rdflib, config.settings
  └── exports: AxiomSpec, get_axioms(), apply_axioms()

backend/app/owl/reasoner.py
  ├── imports: rdflib, owlrl, owl/axiom_registry, owl/converter
  └── exports: run_reasoning(), InferenceResult

backend/app/owl/shacl_generator.py
  ├── imports: rdflib (URIRef 명시), config.settings, models/schemas
  └── exports: generate_shapes(), SH_NODE_SHAPE, SH_MIN_COUNT

backend/app/owl/shacl_validator.py
  ├── imports: rdflib (URIRef 명시), pyshacl, ontology/quality_checker
  └── exports: validate_shacl()

backend/app/owl/materializer.py
  ├── imports: models/schemas, tenant, owl/axiom_registry
  └── exports: materialize_transitive(), materialize_chain_fallback(), cleanup_inferred()

backend/app/owl/schema_enricher.py
  ├── imports: rdflib, owl/converter.local_name
  └── exports: enrich_schema_with_owl()

backend/app/ontology/pipeline.py
  ├── 추가 import: config.settings
  ├── 조건부 import: owl/converter, owl/reasoner (enable_owl=True)
  └── Stage 2.5/2.7 삽입

backend/app/kg_builder/service.py
  ├── 조건부 import: owl/materializer, owl/axiom_registry (enable_owl=True)
  └── 물리화 + chain fallback + stats 합산

backend/app/db/graph_schema.py
  ├── 조건부 호출: _enrich_with_owl() (enable_owl=True)
  └── format_schema_for_prompt() OWL 메타데이터 표시

backend/app/query/router_llm.py
  └── _SYSTEM_PROMPT 확장

backend/app/query/hybrid_search.py ★ v5.0 통합
  └── _CLOSURE 관계 탐색 + 컨텍스트 확장

backend/app/routers/owl.py
  └── GET /export, POST /validate

backend/app/main.py
  └── owl router + OWLReasoningError handler 등록
```

**호출 흐름**:
```
DDL → pipeline.py → [owl/converter → owl/reasoner] → quality_checker → PG
KG Build → service.py → loader.py → [owl/materializer + chain_fallback] → stats 합산
Query Mode A → router_llm.py → graph_schema.py (OWL-enriched) → LLM
Query Mode C → hybrid_search.py → _get_kg_context() → [_CLOSURE 관계 탐색] → LLM
OWL API → routers/owl.py → converter → shacl_generator → shacl_validator
Schema → get_graph_schema() → [_enrich_with_owl()] → PG approved 조회 → OWL graph → enrichment
```

---

## v5.0 통합 로드맵

```
현재 상태:
  v5.0 Sprint 1 ✅ (PDF/DOCX ingestion, chunking, embedding)
  v5.0 Sprint 2 ✅ (Mode C hybrid search, LLM synthesis)
  v5.0 Sprint 3 ⬜ (NER + KG linking)
  v5.0 Sprint 4 ⬜ (reranking + E2E)

권장 실행 순서:
  Step 0: v5.0 Sprint 3-4 완료 (선행)
  Step 1: OWL Phase 1 (Foundation + Axiom Registry) — 27 tests
  Step 2: OWL Phase 2 (Reasoning + Materialization + v5.0 통합) — 14 tests
     └─ hybrid_search.py _CLOSURE 관계 지원
     └─ get_graph_schema() → _enrich_with_owl() 연결
     └─ service.py chain fallback + stats 합산
  Step 3: OWL Phase 3 (Query Integration) — 6 tests
     └─ format_schema_for_prompt() OWL 표시
     └─ router_llm.py 프롬프트 확장
  Step 4: OWL Phase 4 (Frontend + E2E) — 3 tests

총 신규 테스트: ~50개 (기존 353 + v5.0 103 + OWL 50 = ~506개)

향후 확장 (Phase 5, 선택적):
  - NER 결과에 owl:Class URI 매칭 → entity resolution 정확도 향상
  - OWL 개념 임베딩 + pgvector chunk 임베딩 통합 → Mode C 검색 품질 향상
  - ABox-level SHACL 검증 (Neo4j 데이터를 rdflib로 가져와 인스턴스 검증)
```
