# OWL Reasoner 구현 계획 — 7축 평가 보고서

> 평가 대상: `docs/reports/OWL_REASONER_구현계획.md`
> 평가일: 2026-03-11
> 평가 기준: 현재 코드베이스 v5.0 (unstructured data 진행 중)

---

## 종합 스코어카드

| 축 | 항목 | 점수 | 등급 |
|----|------|------|------|
| 1 | 정합성 (Before/After diff 정확도) | 82/100 | B+ |
| 2 | v5.0 호환성 (Mode C, 문서처리 충돌) | 60/100 | C |
| 3 | 코드 정확성 (버그, 타입 오류) | 70/100 | B- |
| 4 | 테스트 커버리지 (엣지 케이스, 부정 테스트) | 65/100 | C+ |
| 5 | 아키텍처 적합성 (캐싱, 타이밍, 단일 소스) | 75/100 | B |
| 6 | 우선순위 적절성 (ROI, v5.0 Mode C 고려) | 55/100 | C- |
| 7 | 실행 리스크 (owlrl 호환, SHACL, Windows) | 72/100 | B- |
| **종합** | | **68/100** | **C+** |

---

## 축 1: 정합성 (82/100)

### 정확한 diff (5/8)

- **config.py** ✅ Line 53-57 정확. CSV Import → OWL → Document Processing 순서 맞음.
- **schemas.py** ✅ `OntologyGenerateResponse` 필드 추가 정확.
- **main.py router import** ✅ `documents` 포함 상태에서 `owl` 추가 — 정확.
- **router_llm.py `_SYSTEM_PROMPT`** ✅ 삽입 위치 정확.
- **graph_schema.py `format_schema_for_prompt`** ✅ 함수 끝 확장 정확.

### 부정확한 diff (3/8)

#### MUST-FIX 1: `exceptions.py` 삽입 위치 오류

계획서는 "line 244 이후에 추가"라고 명시했지만, 현재 파일은 244줄이 마지막이며 v5.0에서 `DocumentValidationError`, `DocumentNotFoundError`, `EmbeddingError`가 이미 line 197-244에 추가되어 있다.

**현재 실제 상태** (line 244):
```python
async def embedding_error_handler(
    _request: Request, exc: EmbeddingError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.detail})
```

**수정된 삽입 위치**: line 244 이후 (파일 최하단) — 이건 사실 올바름. 다만 계획서의 "line 244"는 v4.0 기준이었으나 우연히 v5.0에서도 244가 마지막이라 결과적으로 일치. **위험도: 낮음** (우연히 정합).

#### MUST-FIX 2: `main.py` exception import 줄번호 불일치

계획서의 "Before (line 28): `LocalSearchError`" → 현재 실제 line 28은 `LocalSearchError`가 맞음. ✅

계획서의 "Before (line 44): `local_search_error_handler`" → 현재 실제 line 44은 `local_search_error_handler`가 맞음. ✅

그러나 계획서에서 v5.0의 `DocumentValidationError`, `DocumentNotFoundError`, `EmbeddingError` 및 그 handler들의 import가 이미 존재한다는 것을 명시하지 않음. 혼동의 여지가 있음.

#### MUST-FIX 3: `domain_hints.py` 줄번호 불일치

계획서: "ECOMMERCE_HINT (line 109)의 `detection_threshold=6,` 뒤에 추가"
현재 실제: line 109는 `detection_threshold=6,` `)` 닫는 줄. 맞음. ✅

계획서: "EDUCATION_HINT (line 174)의 `detection_threshold=4,`"
현재 실제: line 174는 `detection_threshold=4,`가 맞음. ✅

계획서: "INSURANCE_HINT (line 248)의 `detection_threshold=4,`"
현재 실제: line 248는 `detection_threshold=4,`가 맞음. ✅

→ domain_hints.py는 v5.0에서 수정되지 않아 정확함.

#### MUST-FIX 4: `service.py` import 추가 — `get_driver` 이미 부재

계획서: `from app.db.neo4j_client import get_driver` 추가 필요라고 하면서도 "이미 있으면 스킵"이라고 모호하게 처리.

**현재 실제**: `service.py`에서 `get_driver`는 import되어 있지 **않음**. `loader.py`에서만 사용. 그러나 `run_kg_build()`의 예외 처리에서 line 233에 `from app.db.neo4j_client import get_driver`를 런타임에 import하는 패턴이 이미 있음.

**권장**: 조건부 import 패턴으로 통일:
```python
if settings.enable_owl:
    try:
        from app.db.neo4j_client import get_driver
        from app.owl.materializer import materialize_transitive
        mat_results = materialize_transitive(ontology, driver=get_driver(), ...)
```

#### MUST-FIX 5: `pipeline.py`에 `from app.config import settings` 누락

계획서가 정확히 지적했음 ✅. 현재 `pipeline.py`의 import에 `settings`가 없고, OWL 코드에서 `settings.enable_owl`을 사용하므로 반드시 추가해야 함.

---

## 축 2: v5.0 호환성 (60/100)

### 치명적 누락: v5.0과의 통합 시나리오 미기술

#### MUST-FIX 6: Mode C (hybrid_search) + OWL 통합 미계획

현재 `hybrid_search.py`의 Step 2 "KG context enrichment"에서 entity 주변 서브그래프를 탐색한다. OWL `_CLOSURE` 관계가 있으면 이를 활용해야 하나 계획서에 언급 없음.

**영향**: Mode C 사용자가 "전자제품의 모든 하위 카테고리 상품은?" 같은 질문을 하면, `PARENT_OF_CLOSURE`를 모르고 1-hop만 탐색하여 답변 품질 저하.

**수정 방안**: Phase 3에 다음을 추가:
```python
# hybrid_search.py의 KG enrichment에서 _CLOSURE 관계도 탐색
# get_kg_context()에서 relationship_types에 _CLOSURE를 포함
```

#### MUST-FIX 7: 문서 NER + OWL 엔티티 연동 미계획

v5.0 Sprint 3은 NER + KG linking을 구현 예정. OWL의 owl:Class 정보와 NER 결과를 매칭하면 linking 정확도가 크게 향상되나 계획서에 언급 없음.

**수정 방안**: Phase 4에 Optional 항목으로 추가:
```
Sprint 3 NER 결과에 owl:Class URI를 매칭 → 더 정확한 entity resolution
```

#### SHOULD-FIX 1: `requirements.txt` 위치

계획서는 `backend/requirements.txt`에 추가한다고 했지만, 실제 파일은 프로젝트 루트 `requirements.txt`에 있음 (backend/ 하위가 아님).

**수정**: 경로를 `requirements.txt` (루트)로 변경.

#### SHOULD-FIX 2: v5.0 document embeddings와 OWL 개념 임베딩 시너지

pgvector에 저장된 chunk 임베딩과 OWL 개념(owl:Class)의 임베딩을 합치면 Mode C의 검색 품질 향상 가능. 현재 계획에 없음.

**수정 방안**: Phase 4 이후 "Phase 5: OWL + Unstructured 시너지" 선택적 마일스톤으로 추가.

---

## 축 3: 코드 정확성 (70/100)

### MUST-FIX 8: `shacl_validator.py` — URIRef vs 문자열 혼용 버그

```python
# Line 424-428 (계획서)
for result in results_graph.subjects(
    RDF.type,
    Graph().namespace_manager.expand_curie("sh:ValidationResult")
    if hasattr(Graph().namespace_manager, "expand_curie")
    else f"{SH_NS}ValidationResult",
):
```

**문제점**:
1. `Graph().namespace_manager.expand_curie`는 rdflib 7.x에서 존재하지 않는 메서드. `expand_curie`는 rdflib에 없음.
2. fallback `f"{SH_NS}ValidationResult"`은 문자열(str)인데, `g.subjects(predicate, object)`의 object는 `URIRef`여야 rdflib가 매칭함.
3. 매번 새 `Graph()`를 생성하는 것 자체가 낭비.

**수정된 코드**:
```python
from rdflib import URIRef

SH_VALIDATION_RESULT = URIRef(f"{SH_NS}ValidationResult")
SH_RESULT_SEVERITY = URIRef(f"{SH_NS}resultSeverity")
SH_RESULT_MESSAGE = URIRef(f"{SH_NS}resultMessage")
SH_FOCUS_NODE = URIRef(f"{SH_NS}focusNode")

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
```

### MUST-FIX 9: `shacl_validator.py` — severity/message/focus 접근도 문자열 사용

Line 431-438에서 `f"{SH_NS}resultSeverity"` 등을 문자열로 넘기고 있지만, `results_graph.value(subject, predicate)`의 predicate도 `URIRef`여야 함.

→ 위의 MUST-FIX 8 수정에 이미 포함.

### MUST-FIX 10: `shacl_generator.py` — `SH.property`가 rdflib에서 예약어 충돌 가능

```python
g.add((shape_uri, SH.property, prop_shape))
```

rdflib에서 `SH = Namespace("http://www.w3.org/ns/shacl#")`로 정의했지만, `Namespace` 객체의 `property`는 Python builtin `property` descriptor와 충돌할 수 있음.

**검증 필요**: rdflib 7.x에서 `Namespace("...").property`는 정상 동작함 (`Namespace.__getattr__`가 처리). 다만 IDE에서 경고가 뜰 수 있으므로, 안전한 방법:

```python
SH_PROPERTY = URIRef("http://www.w3.org/ns/shacl#property")
g.add((shape_uri, SH_PROPERTY, prop_shape))
```

**위험도: 중간** — 런타임에서는 동작하지만 명시적 URIRef가 더 안전.

### MUST-FIX 11: `shacl_generator.py` — `SH["class"]` 사용

```python
g.add((prop_shape, SH["class"], GRAPHRAG[rel.target_node]))
```

`SH["class"]`는 `URIRef("http://www.w3.org/ns/shacl#class")` — 이것은 올바름. ✅
(`class`는 Python 예약어이므로 `SH.class`가 안 되어 `SH["class"]`로 접근하는 것이 맞음.)

### SHOULD-FIX 3: `converter.py` — `GRAPHRAG` 모듈 레벨 상수의 import-time 부작용

```python
GRAPHRAG = Namespace(settings.owl_base_uri)
```

이것은 모듈 import 시점에 `settings`를 읽는다. `enable_owl=False`일 때도 `from app.owl.converter import ...` 하면 `settings.owl_base_uri`가 평가됨. 기본값이 있으므로 에러는 안 나지만, 테스트에서 settings를 override할 때 이미 바인딩된 `GRAPHRAG` 상수가 변경되지 않는 문제 발생.

**수정 방안**: 함수 내에서 Namespace를 생성하거나, 혹은 현재 구조 유지 (기본값이 있으므로 실질적 문제 낮음).

### SHOULD-FIX 4: `axiom_registry.py` — `assert isinstance(ax.target, list)` → 프로덕션에서 assertion 비활성화 가능

```python
elif ax.axiom_type == "propertyChain":
    assert isinstance(ax.target, list)
```

`-O` 옵션으로 Python 실행 시 assert 무시됨.

**수정**:
```python
elif ax.axiom_type == "propertyChain":
    if not isinstance(ax.target, list):
        raise ValueError(f"propertyChain axiom target must be list, got {type(ax.target)}")
```

### SHOULD-FIX 5: `materializer.py` — `DETACH DELETE r`에서 DETACH 불필요

```python
cypher = "MATCH ()-[r]->() WHERE r.inferred = true DETACH DELETE r RETURN count(r) AS deleted"
```

`DETACH DELETE`는 노드 삭제 시 관계도 함께 삭제하는 구문. 관계만 삭제할 때는 `DELETE r`로 충분.

**수정**:
```python
cypher = "MATCH ()-[r]->() WHERE r.inferred = true DELETE r RETURN count(r) AS deleted"
```

### SHOULD-FIX 6: `routers/owl.py` — `get_version`이 `detected_domain` 키를 반환하지 않음

```python
ontology = OntologySpec(**row["ontology"])
owl_graph = ontology_to_owl(ontology, domain=row.get("detected_domain"))
```

`pg_client.get_version()`은 `ontology_versions` 테이블에서 조회하는데, 이 테이블에 `detected_domain` 컬럼이 없음. `row.get("detected_domain")`은 항상 `None`을 반환.

**수정 방안 (택 1)**:
1. `ontology_versions` 테이블에 `detected_domain` 컬럼 추가 (migration)
2. `domain=None`을 명시적으로 사용하고, 도메인 재감지 로직 추가

---

## 축 4: 테스트 커버리지 (65/100)

### 누락된 테스트 시나리오

#### MUST-FIX 12: API 엔드포인트 테스트 부재

`routers/owl.py`의 `GET /api/v1/owl/export/{version_id}`와 `POST /api/v1/owl/validate/{version_id}` 엔드포인트에 대한 API 테스트가 전혀 없음. 기존 프로젝트 패턴은 `httpx.AsyncClient`를 사용한 API 테스트를 포함함 (`test_kg_build.py`, `test_ontology_versions.py` 참조).

**추가 필요 테스트 (최소 5개)**:
```python
# tests/test_owl_api.py
def test_export_owl_disabled(client):
    """enable_owl=False → 502"""

def test_export_owl_not_found(client):
    """존재하지 않는 version_id → 404"""

def test_export_owl_success(client):
    """정상 export → 200 + turtle content"""

def test_validate_owl_disabled(client):
    """enable_owl=False → 502"""

def test_validate_owl_success(client):
    """정상 validate → 200 + conforms"""
```

#### MUST-FIX 13: 부정 테스트 부재

- `converter.py`: 빈 OntologySpec 변환 테스트 없음
- `reasoner.py`: owlrl 라이브러리 없을 때(ImportError) 테스트 없음
- `materializer.py`: Neo4j 연결 실패 시 graceful degradation 테스트 없음
- `axiom_registry.py`: 잘못된 axiom_type 처리 테스트 없음

#### SHOULD-FIX 7: `test_shacl.py` #2 — `SH_NS + "NodeShape"`는 문자열 결합

```python
shape_count = sum(1 for _ in shapes.subjects(RDF.type, SH_NS + "NodeShape"))
```

`SH_NS`는 문자열이고 `RDF.type`은 `URIRef`. `shapes.subjects(URIRef, str)` 매칭이 rdflib에서 동작하지 않을 수 있음.

**수정**:
```python
from rdflib import URIRef
SH_NODE_SHAPE = URIRef("http://www.w3.org/ns/shacl#NodeShape")
shape_count = sum(1 for _ in shapes.subjects(RDF.type, SH_NODE_SHAPE))
```

동일 문제: `test_shacl.py` #3의 `SH_NS + "minCount"`:
```python
min_count_triples = list(shapes.triples((None, URIRef(SH_NS + "minCount"), None)))
```

#### SHOULD-FIX 8: `test_owl_converter.py` #11 — education DDL 없으면 조용히 return

```python
if not ddl_path.exists():
    return  # 스킵
```

`pytest.skip()`을 사용해야 테스트 결과에서 누락이 아닌 스킵으로 표시됨:
```python
import pytest
if not ddl_path.exists():
    pytest.skip("Education DDL not found")
```

동일 문제: `test_owl_reasoning.py` #7, `test_owl_e2e.py` #3.

#### COULD-FIX 1: Round-trip에서 프로퍼티 값 보존 미검증

`test_owl_round_trip_*`은 count만 비교하지 개별 프로퍼티 값(source_column, type, is_key)이 보존되는지 검증하지 않음.

---

## 축 5: 아키텍처 적합성 (75/100)

### MUST-FIX 14: OWL Graph 캐싱 전략 부재

현재 계획에서 `pipeline.py`에서 매 온톨로지 생성 시 OWL Graph를 새로 만들고, `service.py`에서 KG 빌드 시 물리화를 위해 또 만들며, `routers/owl.py`에서 export 시 또 만든다. 동일한 OntologySpec에 대해 3번 중복 생성.

**수정 방안**: `_owl_graph_cache: dict[int, Graph] = {}` (version_id → Graph)로 캐싱. 또는 OWL Graph는 가벼우므로 현재 구조 유지도 가능 — 성능 임팩트가 낮다면 over-engineering 방지 차원에서 현상 유지.

**결론**: 현상 유지 허용 (COULD-FIX 수준).

### SHOULD-FIX 9: 물리화 타이밍 — KG 빌드 완료 후 `stats` 반영 안 됨

`service.py`에서 물리화된 `_CLOSURE` 관계 수가 `KGBuildProgress.relationships_created`에 반영되지 않음. 사용자에게 "relationships: 12" 표시되지만 실제로는 13 (12 + 1 closure)일 수 있음.

**수정**: mat_total을 stats에 합산:
```python
if settings.enable_owl:
    try:
        from app.owl.materializer import materialize_transitive
        from app.db.neo4j_client import get_driver as _get_driver
        mat_results = materialize_transitive(ontology, driver=_get_driver(), tenant_id=tenant_id)
        mat_total = sum(mat_results.values())
        stats["relationships"] = stats.get("relationships", 0) + mat_total
    except Exception:
        logger.warning("OWL materialization failed — non-fatal", exc_info=True)
```

### SHOULD-FIX 10: `schema_enricher.py` 호출 지점 미정의

`enrich_schema_with_owl()`이 정의되어 있지만, `graph_schema.py`의 `get_graph_schema()`에서 호출하는 코드가 계획에 없음. 어디서 호출?

**현재 상태**: `format_schema_for_prompt()`가 dict에 OWL 키가 있으면 표시하지만, 그 키를 넣어주는 코드가 없음.

**수정 필요**: `get_graph_schema()`에 OWL enrichment 단계 추가, 또는 `router_llm.py`의 `classify_by_llm()`에서 호출:
```python
# graph_schema.py의 get_graph_schema() 끝에 추가
if settings.enable_owl:
    try:
        from app.owl.schema_enricher import enrich_schema_with_owl
        from app.owl.converter import ontology_to_owl
        # 최신 approved 온톨로지에서 OWL graph를 생성하여 enrichment
        # ... 단, 여기서 어떤 version의 온톨로지를 사용할지가 불명확
    except Exception:
        pass
```

**이것은 아키텍처 설계 누락**. 어떤 버전의 OntologySpec을 가져와서 OWL Graph를 만들지 정의되지 않았음.

### COULD-FIX 2: `_local_name()` 중복 정의

`converter.py`, `reasoner.py`, `schema_enricher.py` 3곳에 동일한 `_local_name()` 헬퍼가 정의됨. `converter.py`에 두고 나머지가 import하는 게 나을 수 있으나, private 함수 3개 정도는 허용 범위.

---

## 축 6: 우선순위 적절성 (55/100)

### 핵심 문제: v5.0 Mode C가 주력인 상황에서 OWL의 ROI

현재 프로젝트 상태:
- v5.0 Sprint 1-2 완료 (문서 수집, Mode C hybrid search)
- v5.0 Sprint 3-4 미완 (NER+KG linking, reranking+E2E)

**OWL의 실질적 이익**:
1. **Phase 1 (OWL 변환 + SHACL)**: 온톨로지 품질 검증 강화. 가치 있지만 기존 `quality_checker.py`의 5개 체크와 중복됨. 차별화된 가치: 표준 호환 export (Turtle/RDF-XML).
2. **Phase 2 (추론 + 물리화)**: `PARENT_OF_CLOSURE` 같은 전이적 관계 물리화. E-commerce의 카테고리 계층 정도에서만 유의미. 교육/보험 도메인에서는 REQUIRES 전이가 유용하나 아직 데모 데이터가 깊은 계층을 가지지 않음.
3. **Phase 3 (쿼리 통합)**: LLM router에 OWL 메타데이터 제공. Mode A에서만 효과. Mode B/C는 별도 파이프라인.
4. **Phase 4 (Frontend)**: TS 타입 + API wrapper 2개. 가벼움.

### MUST-FIX 15: Phase 우선순위 재조정 제안

**현재 계획**:
```
Phase 1 → Phase 2 → Phase 3 → Phase 4 (순차)
```

**제안**:
```
[높은 우선순위] v5.0 Sprint 3-4 완료 (NER + reranking)
                   ↓
[중간 우선순위] Phase 1 (OWL Foundation) — 온톨로지 export/validate
                   ↓
[중간 우선순위] Phase 2 (Reasoning) — transitive 물리화
                   ↓  ← 여기서 v5.0 Mode C + OWL 통합을 함께 구현
[낮은 우선순위] Phase 3 (Query Integration) — Mode A에만 해당
                   ↓
[낮은 우선순위] Phase 4 (Frontend + E2E)
```

**이유**: Mode C hybrid search가 v5.0의 핵심 기능이며 현재 미완성. OWL은 Mode A 강화에 집중되어 있어, 사용자가 주로 쓸 Mode C와의 시너지가 Phase 3에야 비로소 나옴. Sprint 3-4 완료 후 OWL을 시작하는 것이 전체 ROI 관점에서 나음.

### SHOULD-FIX 11: Phase 2 → Phase 1로 당길 수 있는 경량 항목

`axiom_registry.py`의 도메인별 axiom 정의는 Phase 1에서 미리 만들어두면 Phase 2 시작이 빨라짐. `domain_hints.py`의 `owl_axioms` 필드도 Phase 1에서 추가 가능.

---

## 축 7: 실행 리스크 (72/100)

### MUST-FIX 16: owlrl `propertyChainAxiom` 지원 제한

owlrl 7.x는 OWL 2 RL 프로파일을 구현하지만, `owl:propertyChainAxiom`은 **OWL 2 RL에 포함되지 않는 일부 구현**에서 부분 지원. owlrl의 `OWLRL_Semantics`가 propertyChain을 처리하지 못하면, `CUSTOMER_CATEGORY` 같은 chain axiom이 추론에 반영되지 않음.

**검증 필요**: owlrl 소스 확인 또는 단위 테스트:
```python
def test_owlrl_property_chain_support():
    """owlrl이 propertyChain을 처리하는지 검증."""
    from rdflib import Graph, Namespace, URIRef
    from rdflib.namespace import OWL, RDF, RDFS
    from rdflib.collection import Collection
    from owlrl import DeductiveClosure, OWLRL_Semantics

    g = Graph()
    NS = Namespace("http://test.org#")
    # A --r1--> B --r2--> C, chain(r3) = [r1, r2]
    g.add((NS.A, NS.r1, NS.B))
    g.add((NS.B, NS.r2, NS.C))
    chain = Collection(g, None, [NS.r1, NS.r2])
    g.add((NS.r3, OWL.propertyChainAxiom, chain.uri))
    g.add((NS.r3, RDF.type, OWL.ObjectProperty))

    DeductiveClosure(OWLRL_Semantics).expand(g)
    assert (NS.A, NS.r3, NS.C) in g, "owlrl does not support propertyChain!"
```

**대안**: owlrl이 미지원이면 `CUSTOMER_CATEGORY` 같은 chain은 직접 Cypher로 물리화:
```cypher
MATCH (c:Customer)-[:PLACED]->()-[:CONTAINS]->()-[:BELONGS_TO]->(cat:Category)
MERGE (c)-[:CUSTOMER_CATEGORY]->(cat)
```

### SHOULD-FIX 12: SHACL 검증의 TBox vs ABox 혼동

계획서의 SHACL 검증은 **TBox (스키마)**를 검증하는데, pyshacl은 주로 **ABox (인스턴스 데이터)** 검증용으로 설계됨. OWL 온톨로지의 owl:Class/owl:ObjectProperty에 대한 SHACL shapes를 만들어 검증하는 것은 비표준적 사용법.

**구체적 문제**: `generate_shapes()`가 `sh:targetClass`로 owl:Class를 가리키지만, data_graph에는 해당 클래스의 인스턴스가 없음 (인스턴스는 Neo4j에 있음). 따라서 SHACL 검증은 항상 `conforms=True`를 반환할 가능성이 높음 — 검증 대상 인스턴스가 없으니까.

**수정 방안**:
1. SHACL 검증을 KG 빌드 후 Neo4j 데이터를 rdflib로 가져와서 ABox 검증으로 변경 (복잡도 높음)
2. 현재 구현을 "TBox consistency check"로 리브랜딩하고, 실제 인스턴스 검증은 Phase 5로 미루기
3. SHACL 대신 기존 `quality_checker.py`를 확장하여 OWL-aware 체크 추가

**권장**: 옵션 2 (리브랜딩 + 문서화).

### SHOULD-FIX 13: Windows에서 rdflib 7.x 호환성

rdflib 7.x는 Windows에서 정상 동작하나, `file://` URI 처리에서 Windows 경로(`C:\...`)를 `file:///C:/...`로 변환하는 데 주의 필요. 현재 계획에서는 파일 I/O를 하지 않으므로 (인메모리 Graph만 사용) 실질적 리스크 낮음.

### COULD-FIX 3: OWL-RL 추론 성능 — 대규모 온톨로지

owlrl의 `DeductiveClosure(OWLRL_Semantics).expand(g)`는 그래프 크기에 따라 기하급수적으로 느려질 수 있음. 현재 e-commerce 온톨로지는 ~200 트리플 수준이므로 문제 없으나, 100+ 노드 타입의 대규모 스키마에서는 `owl_max_inferred_triples` 상한 검사만으로는 부족.

**수정**: timeout 추가:
```python
import signal
# Unix only — Windows에서는 signal.SIGALRM 미지원
# 대안: threading.Timer 사용
```

---

## v5.0 통합 로드맵 (신규 제안)

```
현재 상태:
  v5.0 Sprint 1 ✅ (PDF/DOCX ingestion, chunking, embedding)
  v5.0 Sprint 2 ✅ (Mode C hybrid search, LLM synthesis)
  v5.0 Sprint 3 ⬜ (NER + KG linking)
  v5.0 Sprint 4 ⬜ (reranking + E2E)

제안 순서:
  Step 1: v5.0 Sprint 3-4 완료
     │
  Step 2: OWL Phase 1 (Foundation)
     │    - converter, shacl_generator, shacl_validator
     │    - /owl/export, /owl/validate endpoints
     │    - 17 tests
     │
  Step 3: OWL Phase 2 (Reasoning) + v5.0 통합
     │    - axiom_registry, reasoner, materializer
     │    - pipeline.py Stage 2.5/2.7
     │    - service.py 물리화
     │    - ⭐ hybrid_search.py에 _CLOSURE 관계 지원 추가
     │    - 9 + 5 tests (기존 + v5.0 통합)
     │
  Step 4: OWL Phase 3 (Query Integration)
     │    - schema_enricher, graph_schema 확장
     │    - router_llm 프롬프트 확장
     │    - 6 tests
     │
  Step 5: OWL Phase 4 (Frontend + E2E)
          - TS types, API wrappers
          - 3 E2E tests
```

---

## 수정 우선순위 요약

### MUST-FIX (구현 전 반드시 수정)

| # | 항목 | 축 | 영향도 |
|---|------|-----|--------|
| 6 | Mode C + OWL 통합 계획 추가 | 2 | 높음 |
| 8 | shacl_validator.py URIRef vs 문자열 버그 | 3 | 높음 (런타임 에러) |
| 9 | shacl_validator.py severity/message 접근 | 3 | 높음 (런타임 에러) |
| 10 | schema_enricher 호출 지점 미정의 | 5 | 높음 (기능 미동작) |
| 12 | OWL API 엔드포인트 테스트 부재 | 4 | 높음 |
| 15 | Phase 우선순위 재조정 | 6 | 높음 |
| 16 | owlrl propertyChain 지원 검증 | 7 | 높음 |

### SHOULD-FIX (구현 중 수정)

| # | 항목 | 축 | 영향도 |
|---|------|-----|--------|
| 1 | requirements.txt 경로 수정 | 2 | 중간 |
| 3 | converter.py GRAPHRAG 상수 timing | 3 | 낮음 |
| 4 | axiom_registry assert → raise | 3 | 중간 |
| 5 | materializer DETACH DELETE → DELETE | 3 | 낮음 |
| 6 | routers/owl.py detected_domain 부재 | 3 | 중간 |
| 7 | test_shacl.py URIRef 사용 | 4 | 중간 |
| 8 | pytest.skip() 사용 | 4 | 낮음 |
| 9 | 물리화 stats 반영 | 5 | 중간 |
| 11 | Phase 2 경량 항목 Phase 1로 | 6 | 낮음 |
| 12 | SHACL TBox/ABox 리브랜딩 | 7 | 중간 |
| 13 | 부정 테스트 추가 | 4 | 중간 |

### COULD-FIX (여유 있을 때)

| # | 항목 | 축 |
|---|------|-----|
| 1 | Round-trip 프로퍼티 값 검증 | 4 |
| 2 | _local_name() 중복 제거 | 5 |
| 3 | OWL-RL 추론 timeout | 7 |

---

## 수정된 Phase 계획 (v5.0 통합 반영)

### Phase 1: OWL Foundation (3일)
- 신규 파일 6개: `owl/__init__.py`, `owl/converter.py`, `owl/shacl_generator.py`, `owl/shacl_validator.py`, `routers/owl.py`, `owl/axiom_registry.py` (Phase 2에서 이동)
- 수정 파일 4개: `requirements.txt` (루트), `config.py`, `schemas.py`, `main.py`, `exceptions.py`
- 테스트: 17 (converter) + 5 (shacl) + **5 (API)** = **27개**
- `domain_hints.py`의 `owl_axioms` 필드도 여기서 추가 (빈 리스트 기본값)

### Phase 2: Reasoning + v5.0 통합 (3일)
- 신규 파일 3개: `owl/reasoner.py`, `owl/materializer.py`, `owl/schema_enricher.py` (Phase 3에서 이동)
- 수정 파일 4개: `pipeline.py`, `service.py`, `domain_hints.py`, `graph_schema.py`
- **추가**: `hybrid_search.py`의 KG enrichment에서 `_CLOSURE` 관계 지원
- 테스트: 9 (reasoning) + **2 (부정 테스트)** + **3 (hybrid_search OWL)** = **14개**

### Phase 3: Query Integration (2일)
- 수정 파일 2개: `router_llm.py`, `graph_schema.py` (Phase 2에서 schema_enricher 이동)
- 호출 지점 연결: `get_graph_schema()` → `enrich_schema_with_owl()`
- 테스트: 6 (query integration)

### Phase 4: Frontend + E2E (1일)
- 수정 파일 2개: `ontology.ts`, `client.ts`
- 테스트: 3 (E2E)

**총 테스트: ~50개 신규 (기존 353 + 103 v5.0 + 50 OWL = ~506개)**
