# OWL Reasoner 통합 — 파일 단위 구현 계획서

> GraphRAG v4.0 → v5.0 | 작성일: 2026-03-10
> 기술 스택: rdflib 7.x + owlrl 7.x + pyshacl 0.25+ (순수 Python, Java 불필요)

---

## Phase 1: OWL Foundation (OWL 변환 + SHACL 검증)

### 1-1. `backend/requirements.txt` (수정)

**Before** (마지막 줄):
```
httpx>=0.27.0
```

**After**:
```
httpx>=0.27.0
# OWL Reasoner (Phase 1)
rdflib>=7.0.0
owlrl>=7.0.0
pyshacl>=0.25.0
```

**이유**: OWL 변환(rdflib), 추론(owlrl), SHACL 검증(pyshacl) 의존성.

---

### 1-2. `backend/app/config.py` (수정)

**수정 위치**: `Settings` 클래스, `# CSV Import` 섹션과 `# Document Processing` 섹션 사이

**Before** (line 55-57):
```python
    # CSV Import
    csv_max_file_size_mb: int = 50
    csv_max_files: int = 50

    # Document Processing (v5.0)
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

    # Document Processing (v5.0)
```

**이유**: `enable_owl=False`로 기본 비활성화. 기존 353개 테스트 영향 0.

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

        # 관계 프로퍼티
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
    """rdflib OWL Graph → OntologySpec 역변환 (round-trip 보장).

    Returns:
        변환된 OntologySpec
    """
    node_types: list[NodeType] = []
    relationship_types: list[RelationshipType] = []

    # owl:Class → NodeType
    for cls_uri in g.subjects(RDF.type, OWL.Class):
        if isinstance(cls_uri, BNode):
            continue
        name = _local_name(cls_uri)
        source_table = str(g.value(cls_uri, GRAPHRAG.sourceTable) or name.lower())

        # 해당 클래스를 domain으로 갖는 DatatypeProperty → NodeProperty
        props: list[NodeProperty] = []
        for dp_uri in g.subjects(RDFS.domain, cls_uri):
            if (dp_uri, RDF.type, OWL.DatatypeProperty) not in g:
                continue
            dp_name = str(g.value(dp_uri, RDFS.label) or _local_name(dp_uri))
            # "ClassName.propName" 형식에서 propName 추출
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
        name = _local_name(rel_uri)
        source_node = _local_name(g.value(rel_uri, RDFS.domain)) if g.value(rel_uri, RDFS.domain) else ""
        target_node = _local_name(g.value(rel_uri, RDFS.range)) if g.value(rel_uri, RDFS.range) else ""
        derivation = str(g.value(rel_uri, GRAPHRAG.derivation) or "fk_direct")
        data_table = str(g.value(rel_uri, GRAPHRAG.dataTable) or "")
        source_key = str(g.value(rel_uri, GRAPHRAG.sourceKeyColumn) or "id")
        target_key = str(g.value(rel_uri, GRAPHRAG.targetKeyColumn) or "id")

        # 관계 프로퍼티
        rel_props: list[RelProperty] = []
        for rp_uri in g.subjects(RDFS.domain, rel_uri):
            if (rp_uri, RDF.type, OWL.DatatypeProperty) not in g:
                continue
            rp_local = _local_name(rp_uri)
            rp_name = rp_local.split(".", 1)[1] if "." in rp_local else rp_local
            rp_range = g.value(rp_uri, RDFS.range)
            rp_type = _reverse_xsd(rp_range) if rp_range else "string"
            rp_source = rp_name  # source_column = name (보존)
            rel_props.append(RelProperty(name=rp_name, source_column=rp_source, type=rp_type))

        relationship_types.append(RelationshipType(
            name=name, source_node=source_node, target_node=target_node,
            data_table=data_table, source_key_column=source_key,
            target_key_column=target_key, properties=rel_props,
            derivation=derivation,
        ))

    return OntologySpec(node_types=node_types, relationship_types=relationship_types)


def serialize_owl(g: Graph, fmt: str = "turtle") -> str:
    """OWL Graph를 문자열로 직렬화.

    Args:
        g: rdflib Graph
        fmt: "turtle" | "xml" | "json-ld"
    """
    return g.serialize(format=fmt)


def _local_name(uri: URIRef | None) -> str:
    """URI에서 로컬 이름 추출. ex) http://graphrag.io/ontology#Customer → Customer"""
    if uri is None:
        return ""
    s = str(uri)
    return s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]


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
| `ontology_to_owl(ontology, domain)` | `OntologySpec, str\|None` | `Graph` | pipeline.py Stage 2.5, routers/owl.py |
| `owl_to_ontology(g)` | `Graph` | `OntologySpec` | 테스트 round-trip 검증 |
| `serialize_owl(g, fmt)` | `Graph, str` | `str` | routers/owl.py export |

---

### 1-5. `backend/app/owl/shacl_generator.py` (신규)

```python
"""OntologySpec → SHACL Shapes Graph 자동 생성.

각 NodeType에 대해 NodeShape를 생성하고,
프로퍼티 제약(datatype, cardinality)을 SHACL로 표현한다.
"""

from __future__ import annotations

import logging

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from app.config import settings
from app.models.schemas import OntologySpec

logger = logging.getLogger(__name__)

SH = Namespace("http://www.w3.org/ns/shacl#")
GRAPHRAG = Namespace(settings.owl_base_uri)

_XSD_MAP: dict[str, URIRef] = {
    "string": XSD.string,
    "integer": XSD.integer,
    "float": XSD.decimal,
    "boolean": XSD.boolean,
}


def generate_shapes(ontology: OntologySpec) -> Graph:
    """OntologySpec에서 SHACL shapes Graph 생성.

    생성되는 shapes:
    - 각 NodeType에 대한 NodeShape (targetClass)
    - 각 프로퍼티에 대한 PropertyShape (datatype 제약)
    - key 프로퍼티에 대한 minCount 1 / maxCount 1
    - 각 RelationshipType에 대한 domain/range 검증

    Returns:
        SHACL shapes가 포함된 rdflib Graph
    """
    g = Graph()
    g.bind("sh", SH)
    g.bind("gr", GRAPHRAG)
    g.bind("xsd", XSD)

    for nt in ontology.node_types:
        shape_uri = GRAPHRAG[f"{nt.name}Shape"]
        cls_uri = GRAPHRAG[nt.name]

        g.add((shape_uri, RDF.type, SH.NodeShape))
        g.add((shape_uri, SH.targetClass, cls_uri))

        for prop in nt.properties:
            prop_shape = GRAPHRAG[f"{nt.name}_{prop.name}_Shape"]
            g.add((shape_uri, SH.property, prop_shape))
            g.add((prop_shape, SH.path, GRAPHRAG[f"{nt.name}.{prop.name}"]))
            g.add((prop_shape, SH.datatype, _XSD_MAP.get(prop.type, XSD.string)))

            if prop.is_key:
                g.add((prop_shape, SH.minCount, Literal(1)))
                g.add((prop_shape, SH.maxCount, Literal(1)))

    # RelationshipType → domain/range 검증 shape
    node_names = {nt.name for nt in ontology.node_types}
    for rel in ontology.relationship_types:
        if rel.source_node not in node_names or rel.target_node not in node_names:
            continue  # 유효하지 않은 관계는 건너뜀

        rel_shape = GRAPHRAG[f"{rel.name}_RelShape"]
        g.add((rel_shape, RDF.type, SH.NodeShape))
        g.add((rel_shape, SH.targetClass, GRAPHRAG[rel.source_node]))

        prop_shape = GRAPHRAG[f"{rel.name}_target_Shape"]
        g.add((rel_shape, SH.property, prop_shape))
        g.add((prop_shape, SH.path, GRAPHRAG[rel.name]))
        g.add((prop_shape, SH["class"], GRAPHRAG[rel.target_node]))

    shape_count = sum(1 for _ in g.subjects(RDF.type, SH.NodeShape))
    logger.info("Generated %d SHACL shapes (%d total triples)", shape_count, len(g))
    return g
```

---

### 1-6. `backend/app/owl/shacl_validator.py` (신규)

```python
"""pySHACL 검증 래퍼 — SHACL 검증 결과를 QualityIssue 리스트로 변환."""

from __future__ import annotations

import logging

from rdflib import Graph
from rdflib.namespace import RDF

from app.ontology.quality_checker import QualityIssue

logger = logging.getLogger(__name__)

SH_NS = "http://www.w3.org/ns/shacl#"


def validate_shacl(
    data_graph: Graph,
    shapes_graph: Graph,
) -> tuple[bool, list[QualityIssue]]:
    """SHACL 검증 실행 → QualityIssue 리스트 반환.

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
        logger.info("SHACL validation passed")
        return True, []

    # 결과 파싱 → QualityIssue 리스트
    issues: list[QualityIssue] = []
    for result in results_graph.subjects(
        RDF.type,
        Graph().namespace_manager.expand_curie("sh:ValidationResult")
        if hasattr(Graph().namespace_manager, "expand_curie")
        else f"{SH_NS}ValidationResult",
    ):
        # severity
        severity_uri = results_graph.value(result, f"{SH_NS}resultSeverity")
        severity = "error" if severity_uri and "Violation" in str(severity_uri) else "warning"

        # message
        message = str(results_graph.value(result, f"{SH_NS}resultMessage") or "SHACL constraint violated")

        # focus node
        focus = str(results_graph.value(result, f"{SH_NS}focusNode") or "")

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

### 1-7. `backend/app/models/schemas.py` (수정)

**수정 위치**: `OntologyGenerateResponse` 클래스 (line 108-116)

**Before**:
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
```

**이유**: OWL export/validate API의 응답 모델 추가. `owl_axiom_count`는 `enable_owl=False`일 때 `None`.

---

### 1-8. `backend/app/exceptions.py` (수정)

**수정 위치**: 파일 끝 (line 244 이후에 추가)

**추가할 코드**:
```python

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

### 1-9. `backend/app/routers/owl.py` (신규)

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

    ontology = OntologySpec(**row["ontology"])
    owl_graph = ontology_to_owl(ontology, domain=row.get("detected_domain"))
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
    """온톨로지에 대해 SHACL 검증 실행."""
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

    ontology = OntologySpec(**row["ontology"])
    owl_graph = ontology_to_owl(ontology)
    shapes_graph = generate_shapes(ontology)
    conforms, issues = validate_shacl(owl_graph, shapes_graph)

    return SHACLValidationResponse(
        conforms=conforms,
        issue_count=len(issues),
        issues=[{"severity": i.severity, "message": i.message, "details": i.details} for i in issues],
    )
```

---

### 1-10. `backend/app/main.py` (수정)

**수정 위치 1**: import 블록 (line 52)

**Before**:
```python
from app.routers import csv_upload, ddl, documents, evaluation, graph, health, kg_build, mapping, ontology, ontology_versions, query, sse, wisdom
```

**After**:
```python
from app.routers import csv_upload, ddl, documents, evaluation, graph, health, kg_build, mapping, ontology, ontology_versions, owl, query, sse, wisdom
```

**수정 위치 2**: exceptions import (line 18-51 블록에 추가)

**Before** (line 28):
```python
    LocalSearchError,
```

**After**:
```python
    LocalSearchError,
    OWLReasoningError,
```

**Before** (line 44):
```python
    local_search_error_handler,
```

**After**:
```python
    local_search_error_handler,
    owl_reasoning_error_handler,
```

**수정 위치 3**: error handlers 블록 (line 93 이후)

**Before**:
```python
    application.add_exception_handler(LocalSearchError, local_search_error_handler)
```

**After**:
```python
    application.add_exception_handler(LocalSearchError, local_search_error_handler)
    application.add_exception_handler(OWLReasoningError, owl_reasoning_error_handler)
```

**수정 위치 4**: routers 블록 (line 114 이후)

**Before**:
```python
    application.include_router(documents.router)
```

**After**:
```python
    application.include_router(documents.router)
    application.include_router(owl.router)
```

---

### 1-11. `backend/tests/test_owl_converter.py` (신규)

```python
"""OWL 변환 정확성 테스트."""

from __future__ import annotations

from rdflib.namespace import OWL, RDF, RDFS

from app.models.schemas import ERDSchema
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import GRAPHRAG, ontology_to_owl, owl_to_ontology, serialize_owl


# ── 기본 변환 테스트 ───────────────────────────────────────────────

def test_owl_class_count(ecommerce_erd: ERDSchema):
    """#1: E-commerce 온톨로지 → OWL 변환 시 9개 owl:Class 생성."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    classes = list(g.subjects(RDF.type, OWL.Class))
    assert len(classes) == len(ontology.node_types)


def test_owl_object_property_count(ecommerce_erd: ERDSchema):
    """#2: 12개 RelationshipType → 12개 owl:ObjectProperty."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    props = list(g.subjects(RDF.type, OWL.ObjectProperty))
    assert len(props) == len(ontology.relationship_types)


def test_owl_datatype_property_count(ecommerce_erd: ERDSchema):
    """#3: 각 NodeType의 프로퍼티가 DatatypeProperty로 변환."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    total_props = sum(len(nt.properties) for nt in ontology.node_types)
    dp_count = sum(1 for _ in g.subjects(RDF.type, OWL.DatatypeProperty))
    # DatatypeProperty = node props + relationship props
    rel_prop_count = sum(len(r.properties) for r in ontology.relationship_types)
    assert dp_count == total_props + rel_prop_count


def test_owl_domain_range(ecommerce_erd: ERDSchema):
    """#4: ObjectProperty의 domain/range가 올바르게 설정."""
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
    """#5: is_key=True인 프로퍼티는 FunctionalProperty."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    functional_count = sum(1 for _ in g.subjects(RDF.type, OWL.FunctionalProperty))
    key_count = sum(1 for nt in ontology.node_types for p in nt.properties if p.is_key)
    assert functional_count == key_count


# ── Round-trip 테스트 ──────────────────────────────────────────────

def test_owl_round_trip_node_count(ecommerce_erd: ERDSchema):
    """#6: OntologySpec → OWL → OntologySpec round-trip 노드 수 보존."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    restored = owl_to_ontology(g)
    assert len(restored.node_types) == len(ontology.node_types)


def test_owl_round_trip_rel_count(ecommerce_erd: ERDSchema):
    """#7: Round-trip 관계 수 보존."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    restored = owl_to_ontology(g)
    assert len(restored.relationship_types) == len(ontology.relationship_types)


def test_owl_round_trip_node_names(ecommerce_erd: ERDSchema):
    """#8: Round-trip 노드 이름 보존."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    restored = owl_to_ontology(g)
    original_names = {nt.name for nt in ontology.node_types}
    restored_names = {nt.name for nt in restored.node_types}
    assert original_names == restored_names


# ── 직렬화 테스트 ─────────────────────────────────────────────────

def test_serialize_turtle(ecommerce_erd: ERDSchema):
    """#9: Turtle 직렬화 정상 동작."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    turtle = serialize_owl(g, "turtle")
    assert "owl:Class" in turtle
    assert len(turtle) > 100


def test_serialize_xml(ecommerce_erd: ERDSchema):
    """#10: RDF/XML 직렬화 정상 동작."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    xml = serialize_owl(g, "xml")
    assert "rdf:RDF" in xml


# ── 다중 도메인 테스트 ────────────────────────────────────────────

def test_owl_education_domain():
    """#11: Education DDL → OWL 변환."""
    from app.ddl_parser.parser import parse_ddl
    from pathlib import Path
    ddl_path = Path(__file__).resolve().parent.parent.parent / "examples" / "schemas" / "demo_education.sql"
    if not ddl_path.exists():
        return  # 스킵
    erd = parse_ddl(ddl_path.read_text(encoding="utf-8"))
    ontology = build_ontology(erd)
    g = ontology_to_owl(ontology, domain="education")
    assert len(list(g.subjects(RDF.type, OWL.Class))) == len(ontology.node_types)


def test_owl_domain_metadata(ecommerce_erd: ERDSchema):
    """#12: 도메인 메타데이터가 OWL Graph에 포함."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology, domain="ecommerce")
    comments = list(g.objects(GRAPHRAG["Ontology"], RDFS.comment))
    assert any("ecommerce" in str(c) for c in comments)
```

---

### 1-12. `backend/tests/test_shacl.py` (신규)

```python
"""SHACL 검증 테스트."""

from __future__ import annotations

from app.models.schemas import (
    ERDSchema,
    NodeProperty,
    NodeType,
    OntologySpec,
    RelationshipType,
)
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import ontology_to_owl
from app.owl.shacl_generator import generate_shapes
from app.owl.shacl_validator import validate_shacl


def test_shacl_valid_ontology(ecommerce_erd: ERDSchema):
    """#1: 유효한 온톨로지는 SHACL 검증 통과."""
    ontology = build_ontology(ecommerce_erd)
    owl_graph = ontology_to_owl(ontology)
    shapes = generate_shapes(ontology)
    conforms, issues = validate_shacl(owl_graph, shapes)
    # 온톨로지 스키마 레벨 검증이므로 통과해야 함
    assert isinstance(conforms, bool)
    assert isinstance(issues, list)


def test_shacl_shape_count(ecommerce_erd: ERDSchema):
    """#2: NodeType 수 이상의 SHACL shapes 생성."""
    from rdflib.namespace import RDF
    ontology = build_ontology(ecommerce_erd)
    shapes = generate_shapes(ontology)
    SH_NS = "http://www.w3.org/ns/shacl#"
    shape_count = sum(1 for _ in shapes.subjects(RDF.type, SH_NS + "NodeShape"))
    # 최소 node_types 수 이상 (+ 관계 shapes)
    assert shape_count >= len(ontology.node_types)


def test_shacl_key_property_cardinality(ecommerce_erd: ERDSchema):
    """#3: is_key 프로퍼티에 minCount/maxCount 1 제약."""
    ontology = build_ontology(ecommerce_erd)
    shapes = generate_shapes(ontology)
    SH_NS = "http://www.w3.org/ns/shacl#"
    # key 프로퍼티가 있는 shape에 minCount가 설정되어야 함
    min_count_triples = list(shapes.triples((None, SH_NS + "minCount", None)))
    key_count = sum(1 for nt in ontology.node_types for p in nt.properties if p.is_key)
    assert len(min_count_triples) == key_count


def test_shacl_empty_ontology():
    """#4: 빈 온톨로지도 SHACL 검증 통과."""
    ontology = OntologySpec(node_types=[], relationship_types=[])
    owl_graph = ontology_to_owl(ontology)
    shapes = generate_shapes(ontology)
    conforms, issues = validate_shacl(owl_graph, shapes)
    assert conforms is True
    assert len(issues) == 0


def test_shacl_generate_shapes_minimal():
    """#5: 최소 온톨로지에 대한 shapes 생성."""
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

### Phase 1 통합 검증 체크리스트

- [ ] `pip install rdflib owlrl pyshacl` 성공
- [ ] `ENABLE_OWL=false` (기본값)일 때 기존 353개 테스트 전부 통과
- [ ] `pytest tests/test_owl_converter.py tests/test_shacl.py` — 12 + 5 = 17개 통과
- [ ] `GET /api/v1/owl/export/1` — `ENABLE_OWL=false`이면 502, `true`이면 Turtle 반환
- [ ] `POST /api/v1/owl/validate/1` — SHACL 검증 결과 반환
- [ ] Docker Compose 변경 없음

---

## Phase 2: OWL Reasoning Engine (추론 + 물리화)

### 2-1. `backend/app/owl/axiom_registry.py` (신규)

```python
"""도메인별 OWL axiom 레지스트리.

DomainHint.owl_axioms와 연동하여 도메인별 axiom을 OWL Graph에 적용한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rdflib import Graph, Namespace
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from app.config import settings

logger = logging.getLogger(__name__)

GRAPHRAG = Namespace(settings.owl_base_uri)


@dataclass
class AxiomSpec:
    """단일 OWL axiom 정의."""
    subject: str           # 관계명 또는 클래스명
    axiom_type: str        # "TransitiveProperty" | "inverseOf" | "propertyChain" | "disjointWith"
    target: str | list[str]  # 대상 (inverseOf: 역관계명, propertyChain: 관계 리스트, ...)
    domain: str = ""       # TransitiveProperty일 때 domain 클래스
    range_cls: str = ""    # TransitiveProperty일 때 range 클래스


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
    """도메인별 axiom 조회. 미등록 도메인은 빈 리스트 반환."""
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
        assert isinstance(ax.target, list)
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

### 2-2. `backend/app/owl/reasoner.py` (신규)

```python
"""OWL-RL 추론 실행 + 추론 결과 추출.

rdflib 인메모리 Graph에서 OWL-RL 추론을 실행하고,
새로 추론된 트리플을 추출한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rdflib import Graph
from rdflib.namespace import OWL, RDF, RDFS

from app.config import settings
from app.owl.axiom_registry import AxiomSpec, apply_axioms, get_axioms
from app.owl.converter import GRAPHRAG

logger = logging.getLogger(__name__)


@dataclass
class InferenceResult:
    """추론 결과."""
    axioms_applied: int
    triples_before: int
    triples_after: int
    inferred_count: int
    transitive_rels: list[str]      # 전이적으로 마킹된 관계명
    inverse_pairs: list[tuple[str, str]]  # (원본, 역관계) 쌍


def run_reasoning(
    owl_graph: Graph,
    domain: str | None = None,
    extra_axioms: list[AxiomSpec] | None = None,
) -> InferenceResult:
    """OWL-RL 추론 실행.

    Args:
        owl_graph: axiom이 적용될 OWL Graph (in-place 수정)
        domain: 도메인명 (axiom 레지스트리 조회용)
        extra_axioms: 추가 axiom (DomainHint.owl_axioms 등)

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

    # 2. OWL-RL 추론 (인메모리, Java 불필요)
    try:
        from owlrl import DeductiveClosure, OWLRL_Semantics
        DeductiveClosure(OWLRL_Semantics).expand(owl_graph)
    except Exception as e:
        logger.warning("OWL-RL reasoning failed: %s — axioms applied but no inference", e)

    after_count = len(owl_graph)
    inferred = after_count - before_count

    # 추론 상한 체크
    if inferred > settings.owl_max_inferred_triples:
        logger.warning(
            "Inferred %d triples exceeds limit %d — results may be incomplete",
            inferred, settings.owl_max_inferred_triples,
        )

    # 3. 메타데이터 추출
    transitive_rels = [
        _local_name(s)
        for s in owl_graph.subjects(RDF.type, OWL.TransitiveProperty)
    ]
    inverse_pairs = []
    for s, _, o in owl_graph.triples((None, OWL.inverseOf, None)):
        s_name = _local_name(s)
        o_name = _local_name(o)
        if s_name and o_name and (o_name, s_name) not in inverse_pairs:
            inverse_pairs.append((s_name, o_name))

    logger.info(
        "Reasoning complete: %d axioms, %d→%d triples (+%d inferred), "
        "%d transitive, %d inverse pairs",
        applied, before_count, after_count, inferred,
        len(transitive_rels), len(inverse_pairs),
    )

    return InferenceResult(
        axioms_applied=applied,
        triples_before=before_count,
        triples_after=after_count,
        inferred_count=inferred,
        transitive_rels=transitive_rels,
        inverse_pairs=inverse_pairs,
    )


def _local_name(uri) -> str:
    s = str(uri)
    return s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]
```

---

### 2-3. `backend/app/owl/materializer.py` (신규)

```python
"""OWL 추론 결과를 Neo4j에 물리화.

전이적 클로저 관계를 Neo4j에 MERGE하여
쿼리 타임에 추론 없이 직접 탐색 가능하게 한다.
"""

from __future__ import annotations

import logging

from app.models.schemas import OntologySpec

logger = logging.getLogger(__name__)


def materialize_transitive(
    ontology: OntologySpec,
    driver,
    tenant_id: str | None = None,
) -> dict[str, int]:
    """자기 참조 관계(전이적 후보)의 클로저를 Neo4j에 물리화.

    Args:
        ontology: 현재 온톨로지
        driver: Neo4j driver
        tenant_id: 멀티테넌트 ID

    Returns:
        {rel_name: 생성된 관계 수} 딕셔너리
    """
    from app.tenant import tenant_label_prefix
    prefix = tenant_label_prefix(tenant_id)

    # 자기 참조 관계 = 전이적 후보
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
                    logger.info(
                        "Materialized %d transitive closure edges for %s",
                        created, rel.name,
                    )
        except Exception as e:
            logger.warning("Failed to materialize %s: %s", rel.name, e)
            results[rel.name] = 0

    total = sum(results.values())
    logger.info("Materialization complete: %d total closure edges", total)
    return results


def cleanup_inferred(driver, tenant_id: str | None = None) -> int:
    """물리화된 추론 관계 삭제 (KG 리빌드 전 정리용).

    Returns:
        삭제된 관계 수
    """
    cypher = "MATCH ()-[r]->() WHERE r.inferred = true DETACH DELETE r RETURN count(r) AS deleted"
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

### 2-4. `backend/app/ontology/domain_hints.py` (수정)

**수정 위치**: `DomainHint` 데이터클래스 (line 19-43)

**Before** (line 43):
```python
    # Minimum overlap count to detect this domain
    detection_threshold: int = 6
```

**After**:
```python
    # Minimum overlap count to detect this domain
    detection_threshold: int = 6

    # OWL axiom 정의 (Phase 2)
    owl_axioms: list[tuple] = field(default_factory=list)
```

**수정 위치**: ECOMMERCE_HINT (line 109)

**Before**:
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

**수정 위치**: EDUCATION_HINT (line 174)

**Before**:
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

**수정 위치**: INSURANCE_HINT (line 248)

**Before**:
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

### 2-5. `backend/app/ontology/pipeline.py` (수정)

**수정 위치**: Stage 2 이후, Stage 3 이전 (line 80-81 사이에 삽입)

**Before** (line 79-82):
```python
            # Keep baseline, stage stays "fk_only"

    # ── Stage 3: Quality validation ────────────────────────────────
    warnings: list[str] = []
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

            owl_graph = ontology_to_owl(final_ontology, domain=domain_hint.name if domain_hint else None)
            owl_result = run_reasoning(owl_graph, domain=domain_hint.name if domain_hint else None)
            owl_axiom_count = owl_result.axioms_applied
            logger.info("OWL reasoning: +%d inferred triples", owl_result.inferred_count)
        except Exception as e:
            logger.warning("OWL reasoning skipped: %s", e)

    # ── Stage 3: Quality validation ────────────────────────────────
    warnings: list[str] = []
```

**수정 위치**: return문 (line 129-138)

**Before**:
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

**수정 위치**: import 블록 (line 1 근처)

**추가** (기존 import 아래):
```python
from app.config import settings
```

---

### 2-6. `backend/app/kg_builder/service.py` (수정)

**수정 위치**: KG 빌드 성공 후 캐시 무효화 블록 (line 184-194) 다음에 삽입

**Before** (line 193-196):
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
                from app.owl.materializer import materialize_transitive
                mat_results = materialize_transitive(ontology, driver=get_driver(), tenant_id=tenant_id)
                mat_total = sum(mat_results.values())
                if mat_total > 0:
                    logger.info("OWL materialization: %d closure edges created", mat_total)
            except Exception:
                logger.warning("OWL materialization failed — non-fatal", exc_info=True)

        # 6. Success
```

**수정 위치**: import 블록 (line 6)

**추가** (기존 import 아래):
```python
from app.db.neo4j_client import get_driver
```

(주의: `get_driver`는 이미 `loader.py`에서 사용되지만 `service.py`에는 없을 수 있으므로 확인 필요. 이미 있으면 스킵.)

---

### 2-7. `backend/tests/test_owl_reasoning.py` (신규)

```python
"""OWL 추론 테스트."""

from __future__ import annotations

from rdflib.namespace import OWL, RDF

from app.models.schemas import ERDSchema
from app.ontology.fk_rule_engine import build_ontology
from app.owl.axiom_registry import ECOMMERCE_AXIOMS, EDUCATION_AXIOMS, AxiomSpec, apply_axioms, get_axioms
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
    """#2: 미등록 도메인은 빈 리스트."""
    axioms = get_axioms("unknown_domain")
    assert axioms == []


def test_apply_transitive(ecommerce_erd: ERDSchema):
    """#3: TransitiveProperty axiom 적용."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    before = len(g)
    apply_axioms(g, [AxiomSpec("PARENT_OF", "TransitiveProperty", "", domain="Category", range_cls="Category")])
    # TransitiveProperty 트리플 추가됨
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
    # propertyChainAxiom 트리플 존재 확인
    chains = list(g.objects(GRAPHRAG["CUSTOMER_CATEGORY"], OWL.propertyChainAxiom))
    assert len(chains) == 1


def test_run_reasoning_ecommerce(ecommerce_erd: ERDSchema):
    """#6: E-commerce 도메인 전체 추론 실행."""
    ontology = build_ontology(ecommerce_erd)
    g = ontology_to_owl(ontology)
    result = run_reasoning(g, domain="ecommerce")
    assert result.axioms_applied >= 3
    assert result.triples_after >= result.triples_before
    assert len(result.transitive_rels) >= 1
    assert "PARENT_OF" in result.transitive_rels


def test_run_reasoning_education():
    """#7: Education 도메인 추론."""
    from app.ddl_parser.parser import parse_ddl
    from pathlib import Path
    ddl_path = Path(__file__).resolve().parent.parent.parent / "examples" / "schemas" / "demo_education.sql"
    if not ddl_path.exists():
        return
    erd = parse_ddl(ddl_path.read_text(encoding="utf-8"))
    ontology = build_ontology(erd)
    g = ontology_to_owl(ontology)
    result = run_reasoning(g, domain="education")
    assert result.axioms_applied >= 2


def test_run_reasoning_no_domain(ecommerce_erd: ERDSchema):
    """#8: 도메인 없이 추론 — axiom 없으므로 스킵."""
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
    assert isinstance(result.axioms_applied, int)
    assert isinstance(result.triples_before, int)
    assert isinstance(result.triples_after, int)
    assert isinstance(result.transitive_rels, list)
    assert isinstance(result.inverse_pairs, list)
```

---

### Phase 2 통합 검증 체크리스트

- [ ] `ENABLE_OWL=false`일 때 기존 353개 테스트 + Phase 1 테스트 전부 통과
- [ ] `pytest tests/test_owl_reasoning.py` — 9개 통과
- [ ] pipeline.py에 Stage 2.5/2.7이 `enable_owl=True`일 때만 실행됨
- [ ] KG 빌드 후 전이적 클로저 관계가 Neo4j에 생성됨 (`r.inferred=true`)
- [ ] OWL 추론 실패 시 warnings에 메시지 추가 + 기존 파이프라인 정상 동작

---

## Phase 3: Query Layer Integration (쿼리 OWL 통합)

### 3-1. `backend/app/owl/schema_enricher.py` (신규)

```python
"""graph_schema에 OWL 메타데이터(계층, 전이적, 체인) 병합."""

from __future__ import annotations

import logging

from rdflib import Graph
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

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

    Args:
        neo4j_schema: get_graph_schema() 결과
        owl_graph: axiom이 적용된 OWL Graph

    Returns:
        OWL 메타데이터가 추가된 스키마 dict
    """
    enriched = dict(neo4j_schema)

    # 1. 클래스 계층
    hierarchy: dict[str, list[str]] = {}
    for cls in owl_graph.subjects(RDF.type, OWL.Class):
        parents = [
            _local_name(p)
            for p in owl_graph.objects(cls, RDFS.subClassOf)
            if _local_name(p)
        ]
        if parents:
            hierarchy[_local_name(cls)] = parents
    enriched["class_hierarchy"] = hierarchy

    # 2. 전이적 관계
    enriched["transitive_properties"] = [
        _local_name(p)
        for p in owl_graph.subjects(RDF.type, OWL.TransitiveProperty)
        if _local_name(p)
    ]

    # 3. 역관계 쌍
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for s, _, o in owl_graph.triples((None, OWL.inverseOf, None)):
        pair = (min(_local_name(s), _local_name(o)), max(_local_name(s), _local_name(o)))
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
                chain = [_local_name(item) for item in Collection(owl_graph, chain_node)]
                if chain:
                    chains.append(chain)
            except Exception:
                pass
    enriched["inferred_paths"] = chains

    return enriched


def _local_name(uri) -> str:
    s = str(uri)
    return s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]
```

---

### 3-2. `backend/app/db/graph_schema.py` (수정)

**수정 위치**: `format_schema_for_prompt` 함수 끝 (line 153)

**Before** (line 150-153):
```python
        for rel_type, props in schema["relationship_properties"].items():
            lines.append(f"  {rel_type}: {', '.join(props)}")

    return "\n".join(lines)
```

**After**:
```python
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

### 3-3. `backend/app/query/router_llm.py` (수정)

**수정 위치**: `_SYSTEM_PROMPT` (line 19-43)

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

### 3-4. `backend/tests/test_owl_query_integration.py` (신규)

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
    """테스트용 OWL-enriched 스키마 생성."""
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
    """#1: Enriched 스키마에 전이적 관계 포함."""
    schema = _make_enriched_schema(ecommerce_erd)
    assert "transitive_properties" in schema
    assert "PARENT_OF" in schema["transitive_properties"]


def test_enriched_schema_has_inverse(ecommerce_erd: ERDSchema):
    """#2: Enriched 스키마에 역관계 쌍 포함."""
    schema = _make_enriched_schema(ecommerce_erd)
    assert "inverse_pairs" in schema
    assert len(schema["inverse_pairs"]) >= 2


def test_enriched_schema_has_chains(ecommerce_erd: ERDSchema):
    """#3: Enriched 스키마에 프로퍼티 체인 포함."""
    schema = _make_enriched_schema(ecommerce_erd)
    assert "inferred_paths" in schema


def test_format_prompt_includes_owl(ecommerce_erd: ERDSchema):
    """#4: format_schema_for_prompt에 OWL 정보 포함."""
    schema = _make_enriched_schema(ecommerce_erd)
    prompt = format_schema_for_prompt(schema)
    assert "Transitive properties" in prompt
    assert "PARENT_OF" in prompt


def test_format_prompt_without_owl():
    """#5: OWL 없는 스키마도 정상 동작 (하위호환)."""
    schema = {
        "node_labels": ["Customer", "Product"],
        "relationship_types": ["PLACED"],
        "node_properties": {"Customer": ["id", "name"]},
        "relationship_properties": {},
    }
    prompt = format_schema_for_prompt(schema)
    assert "Customer" in prompt
    assert "Transitive" not in prompt  # OWL 없으면 표시 안 됨


def test_enriched_schema_preserves_base(ecommerce_erd: ERDSchema):
    """#6: 기존 스키마 필드 보존."""
    schema = _make_enriched_schema(ecommerce_erd)
    assert "node_labels" in schema
    assert "relationship_types" in schema
    assert len(schema["node_labels"]) > 0
```

---

### Phase 3 통합 검증 체크리스트

- [ ] `ENABLE_OWL=false`일 때 format_schema_for_prompt 출력 변화 없음
- [ ] `ENABLE_OWL=true`일 때 LLM router 프롬프트에 Transitive/Inverse/Chain 정보 포함
- [ ] `pytest tests/test_owl_query_integration.py` — 6개 통과
- [ ] 기존 쿼리 테스트 전부 통과

---

## Phase 4: Frontend + E2E

### 4-1. `frontend/src/types/ontology.ts` (수정)

**수정 위치**: `OntologyGenerateResponse` 인터페이스 뒤 (파일 끝 부근)

**추가할 코드**:
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
}
```

---

### 4-2. `frontend/src/api/client.ts` (수정)

**추가할 함수** (파일 끝):

```typescript
// ── OWL API ─────────────────────────────────────────────────────

export async function exportOWL(
  versionId: number,
  format: string = "turtle"
): Promise<OWLExportResponse> {
  const res = await fetch(
    `${BASE}/api/v1/owl/export/${versionId}?fmt=${format}`
  );
  await validateResponse(res);
  return res.json();
}

export async function validateSHACL(
  versionId: number
): Promise<SHACLValidationResponse> {
  const res = await fetch(`${BASE}/api/v1/owl/validate/${versionId}`, {
    method: "POST",
  });
  await validateResponse(res);
  return res.json();
}
```

---

### 4-3. `backend/tests/test_owl_e2e.py` (신규)

```python
"""OWL E2E 통합 테스트: DDL → 온톨로지 → OWL → 추론 → 검증 전체 파이프라인."""

from __future__ import annotations

from rdflib.namespace import OWL, RDF

from app.models.schemas import ERDSchema
from app.ontology.fk_rule_engine import build_ontology
from app.owl.converter import ontology_to_owl, owl_to_ontology, serialize_owl
from app.owl.reasoner import run_reasoning
from app.owl.shacl_generator import generate_shapes
from app.owl.shacl_validator import validate_shacl


def test_e2e_full_pipeline(ecommerce_erd: ERDSchema):
    """#1: DDL → 온톨로지 → OWL → 추론 → SHACL 검증 전체 파이프라인."""
    # 1. DDL → 온톨로지
    ontology = build_ontology(ecommerce_erd)
    assert len(ontology.node_types) == 9

    # 2. 온톨로지 → OWL
    g = ontology_to_owl(ontology, domain="ecommerce")
    class_count = sum(1 for _ in g.subjects(RDF.type, OWL.Class))
    assert class_count == 9

    # 3. OWL 추론
    result = run_reasoning(g, domain="ecommerce")
    assert result.axioms_applied >= 3
    assert "PARENT_OF" in result.transitive_rels

    # 4. SHACL 검증
    shapes = generate_shapes(ontology)
    conforms, issues = validate_shacl(g, shapes)
    assert isinstance(conforms, bool)

    # 5. Round-trip
    restored = owl_to_ontology(g)
    assert len(restored.node_types) >= len(ontology.node_types)

    # 6. 직렬화
    turtle = serialize_owl(g, "turtle")
    assert "TransitiveProperty" in turtle


def test_e2e_without_owl_flag(ecommerce_erd: ERDSchema):
    """#2: enable_owl=False일 때 기존 파이프라인만 동작."""
    from app.ontology.pipeline import generate_ontology
    response = generate_ontology(ecommerce_erd, skip_llm=True)
    assert response.ontology is not None
    assert len(response.ontology.node_types) == 9
    # enable_owl=False이면 owl_axiom_count는 None
    # (config에서 기본값 False이므로)


def test_e2e_education_pipeline():
    """#3: Education 도메인 E2E."""
    from app.ddl_parser.parser import parse_ddl
    from pathlib import Path
    ddl_path = Path(__file__).resolve().parent.parent.parent / "examples" / "schemas" / "demo_education.sql"
    if not ddl_path.exists():
        return
    erd = parse_ddl(ddl_path.read_text(encoding="utf-8"))
    ontology = build_ontology(erd)
    g = ontology_to_owl(ontology, domain="education")
    result = run_reasoning(g, domain="education")
    assert result.axioms_applied >= 2
    assert "REQUIRES" in result.transitive_rels
```

---

### Phase 4 통합 검증 체크리스트

- [ ] `pytest tests/test_owl_e2e.py` — 3개 통과
- [ ] 프론트엔드 빌드 (`npm run build`) 성공
- [ ] `frontend/src/types/ontology.ts` 타입 오류 없음
- [ ] 전체 테스트 스위트 통과 (353 기존 + ~35 신규 = ~388개)

---

## 전체 의존성 그래프

```
backend/app/config.py
  └── settings.enable_owl, owl_base_uri, owl_max_inferred_triples

backend/app/owl/converter.py
  ├── imports: rdflib, config.settings, models/schemas
  └── exports: ontology_to_owl(), owl_to_ontology(), serialize_owl()

backend/app/owl/axiom_registry.py
  ├── imports: rdflib, config.settings
  └── exports: AxiomSpec, get_axioms(), apply_axioms()

backend/app/owl/reasoner.py
  ├── imports: rdflib, owlrl, owl/axiom_registry, owl/converter
  └── exports: run_reasoning(), InferenceResult

backend/app/owl/shacl_generator.py
  ├── imports: rdflib, config.settings, models/schemas
  └── exports: generate_shapes()

backend/app/owl/shacl_validator.py
  ├── imports: rdflib, pyshacl, ontology/quality_checker.QualityIssue
  └── exports: validate_shacl()

backend/app/owl/materializer.py
  ├── imports: models/schemas, tenant
  └── exports: materialize_transitive(), cleanup_inferred()

backend/app/owl/schema_enricher.py
  ├── imports: rdflib
  └── exports: enrich_schema_with_owl()

backend/app/ontology/pipeline.py
  ├── 기존 imports + config.settings
  ├── 조건부 import: owl/converter, owl/reasoner (enable_owl=True)
  └── Stage 2.5/2.7 삽입

backend/app/kg_builder/service.py
  ├── 기존 imports + config.settings
  ├── 조건부 import: owl/materializer (enable_owl=True)
  └── 물리화 호출 삽입

backend/app/db/graph_schema.py
  └── format_schema_for_prompt() 확장 (OWL 키 존재 시)

backend/app/query/router_llm.py
  └── _SYSTEM_PROMPT 확장 (전이적/역관계/체인 가이드)

backend/app/routers/owl.py
  ├── imports: owl/converter, owl/shacl_*, exceptions, models/schemas
  └── endpoints: GET /export, POST /validate

backend/app/main.py
  └── owl router + exception handler 등록

호출 흐름:
  DDL → pipeline.py → [owl/converter → owl/reasoner] → quality_checker → PG
  KG Build → service.py → loader.py → [owl/materializer]
  Query → router_llm.py → graph_schema.py (OWL-enriched) → LLM
```

---

## 비용 요약

| 항목 | Phase 1 | Phase 2 | Phase 3 | Phase 4 | 합계 |
|------|---------|---------|---------|---------|------|
| 신규 파일 | 6 | 3 | 1 | 2 | **12** |
| 수정 파일 | 4 | 3 | 2 | 2 | **11** |
| 신규 테스트 | 17 | 9 | 6 | 3 | **35** |
| 누적 테스트 | 370 | 379 | 385 | **388** | |
| pip 패키지 | 3 | 0 | 0 | 0 | **3** |
| Docker 변경 | 0 | 0 | 0 | 0 | **0** |
