# OWL Reasoner 통합 분석 및 개발 계획

> GraphRAG v4.0 → v5.0 | 작성일: 2026-03-10

---

## 목차
1. [기술 타당성 분석](#1-기술-타당성-분석)
2. [아키텍처 설계](#2-아키텍처-설계)
3. [단계별 개발 계획](#3-단계별-개발-계획)
4. [도메인별 임팩트 분석](#4-도메인별-임팩트-분석)
5. [트레이드오프 분석](#5-트레이드오프-분석)
6. [최종 추천](#6-최종-추천)

---

## 1. 기술 타당성 분석

### 1.1 Python OWL/RDF 라이브러리 비교

| 라이브러리 | OWL 프로파일 | Java 필요 | 추론 성능(10-50 클래스) | 메모리 | 설치 복잡도 |
|-----------|------------|----------|---------------------|--------|-----------|
| **owlready2 + HermiT** | OWL 2 DL (Full) | Yes (JVM) | < 1s (JVM 시작 ~3s) | ~100MB | `pip install owlready2` + JVM |
| **rdflib + OWL-RL** | OWL 2 RL | No | < 1s | ~20MB | `pip install rdflib owlrl` |
| **rdflib + reasonable** | OWL 2 RL | No (Rust) | < 0.1s | ~10MB | `pip install reasonable` |
| **pySHACL** | 검증 전용 | No | < 0.5s | ~15MB | `pip install pyshacl` |
| **커스텀 순수 Python** | 선택적 서브셋 | No | < 0.01s | ~5MB | 없음 |

### 1.2 기능별 실현 가능성 평가

#### (a) OWL 온톨로지 생성: OntologySpec → OWL/RDF 변환

**실현 가능성: 높음 (난이도: 낮음)**

현재 OntologySpec의 모든 필드가 OWL로 직접 매핑 가능:

```python
# backend/app/owl/converter.py — OntologySpec → OWL 변환 예시
from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD, Literal, URIRef

GRAPHRAG = Namespace("http://graphrag.io/ontology#")

def ontology_to_owl(ontology: OntologySpec, domain: str = "default") -> Graph:
    g = Graph()
    g.bind("gr", GRAPHRAG)
    g.bind("owl", OWL)

    # NodeType → owl:Class
    for nt in ontology.node_types:
        cls = GRAPHRAG[nt.name]
        g.add((cls, RDF.type, OWL.Class))
        g.add((cls, RDFS.label, Literal(nt.name)))
        g.add((cls, GRAPHRAG.sourceTable, Literal(nt.source_table)))

        # NodeProperty → owl:DatatypeProperty
        for prop in nt.properties:
            dp = GRAPHRAG[f"{nt.name}.{prop.name}"]
            g.add((dp, RDF.type, OWL.DatatypeProperty))
            g.add((dp, RDFS.domain, cls))
            g.add((dp, RDFS.range, _xsd_type(prop.type)))
            if prop.is_key:
                g.add((dp, RDF.type, OWL.FunctionalProperty))

    # RelationshipType → owl:ObjectProperty
    for rel in ontology.relationship_types:
        op = GRAPHRAG[rel.name]
        g.add((op, RDF.type, OWL.ObjectProperty))
        g.add((op, RDFS.domain, GRAPHRAG[rel.source_node]))
        g.add((op, RDFS.range, GRAPHRAG[rel.target_node]))
        g.add((op, GRAPHRAG.derivation, Literal(rel.derivation)))

    return g

def _xsd_type(prop_type: str) -> URIRef:
    return {
        "string": XSD.string,
        "integer": XSD.integer,
        "float": XSD.decimal,
        "boolean": XSD.boolean,
    }.get(prop_type, XSD.string)
```

**YAML 매핑과의 관계**: 공존. YAML은 RDB→LPG 매핑, OWL은 시맨틱 스키마 레이어. 동일 OntologySpec에서 양쪽 생성.

```
OntologySpec ──┬── ontology_to_mapping() → YAML (RDB→LPG)
               └── ontology_to_owl()     → OWL  (시맨틱 스키마)
```

**ROI: 높음** — 다른 모든 OWL 기능의 기반.

---

#### (b) Reasoning 통합: OWL Reasoner로 추론

**실현 가능성: 중간 (난이도: 중간)**

##### 전이적 관계 추론 (owl:TransitiveProperty)

```python
# OWL Manchester Syntax
ObjectProperty: PARENT_OF
    Characteristics: Transitive
    Domain: Category
    Range: Category
```

```python
# Python (rdflib + OWL-RL)
from owlrl import DeductiveClosure, OWLRL_Semantics

g = ontology_to_owl(ontology)
# PARENT_OF를 TransitiveProperty로 마킹
parent_of = GRAPHRAG["PARENT_OF"]
g.add((parent_of, RDF.type, OWL.TransitiveProperty))

# 추론 실행
DeductiveClosure(OWLRL_Semantics).expand(g)

# 추론 결과: Category A PARENT_OF B, B PARENT_OF C → A PARENT_OF C (자동 생성)
```

**Neo4j Materialization 전략**:

```python
# 추론된 전이적 관계를 Neo4j에 물리화
def materialize_transitive(driver, rel_name: str, label: str):
    """전이적 관계의 클로저를 Neo4j에 저장"""
    cypher = f"""
    MATCH (a:{label})-[:{rel_name}*2..]->(b:{label})
    WHERE NOT (a)-[:{rel_name}]->(b) AND a <> b
    MERGE (a)-[r:{rel_name}_CLOSURE]->(b)
    SET r.inferred = true, r.derivation = 'owl_transitive'
    RETURN count(r) AS created
    """
    with driver.session() as session:
        result = session.run(cypher)
        return result.single()["created"]
```

##### 클래스 계층 추론 (rdfs:subClassOf)

```python
# OWL Manchester Syntax
Class: ElectronicsProduct
    SubClassOf: Product

Class: DigitalProduct
    SubClassOf: ElectronicsProduct
    # 추론: DigitalProduct rdfs:subClassOf Product (전이적)
```

**활용 시나리오**: "모든 Product를 보여줘" → ElectronicsProduct, DigitalProduct 포함

```cypher
-- OWL 추론 없이 (현재)
MATCH (p:Product) RETURN p

-- OWL 추론 후 (서브클래스 인식)
MATCH (p) WHERE p:Product OR p:ElectronicsProduct OR p:DigitalProduct RETURN p
```

##### 프로퍼티 체인 추론 (owl:propertyChainAxiom)

```python
# OWL Manchester Syntax
ObjectProperty: ORDERED_PRODUCT_CATEGORY
    SubPropertyChain: PLACED o CONTAINS o BELONGS_TO
    # "고객이 주문한 상품의 카테고리" = Customer → PLACED → Order → CONTAINS → Product → BELONGS_TO → Category
```

```python
# rdflib로 프로퍼티 체인 정의
chain = BNode()
g.add((GRAPHRAG.ORDERED_PRODUCT_CATEGORY, OWL.propertyChainAxiom, chain))
Collection(g, chain, [
    GRAPHRAG.PLACED,
    GRAPHRAG.CONTAINS,
    GRAPHRAG.BELONGS_TO,
])
```

**추론 결과 → Neo4j Materialization vs Query-Time**:

| 전략 | 장점 | 단점 | 적합한 경우 |
|------|------|------|-----------|
| **Materialization** | 쿼리 속도 빠름, Cypher 단순 | 스토리지 증가, 데이터 변경 시 재계산 | 전이적 관계, 카테고리 계층 |
| **Query-Time** | 항상 최신, 스토리지 없음 | Cypher 복잡, 실행 느림 | 프로퍼티 체인, 동적 관계 |

**추천**: 전이적 관계/계층은 Materialization, 프로퍼티 체인은 Query-Time (Cypher 가변 경로).

**ROI: 높음** — 쿼리 정확도와 도메인 범용성 직접 향상.

---

#### (c) SHACL 제약 검증: quality_checker 확장

**실현 가능성: 높음 (난이도: 낮음)**

현재 5-point 검사와 SHACL 매핑:

| 현재 검사 | SHACL 대응 | 추가 가능한 SHACL 검증 |
|----------|-----------|---------------------|
| 중복 클래스명 | `sh:uniqueLang` | - |
| Domain/Range 오류 | `sh:class` | `sh:nodeKind sh:IRI` |
| 순환 참조 | (커스텀 SPARQL) | `sh:sparql` 기반 사이클 탐지 |
| 고아 노드 | `sh:minCount 1` | 관계 카디널리티 제약 |
| 네이밍 컨벤션 | `sh:pattern` | `^[A-Z][a-zA-Z]*$` 등 |

**추가 가능한 SHACL 검증**:

```turtle
# 카디널리티 제약: Order는 반드시 1명의 Customer가 있어야 함
gr:OrderShape a sh:NodeShape ;
    sh:targetClass gr:Order ;
    sh:property [
        sh:path gr:PLACED_BY ;    # inverse of PLACED
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:class gr:Customer ;
    ] .

# 값 범위 제약: Product.price > 0
gr:ProductPriceShape a sh:PropertyShape ;
    sh:path gr:price ;
    sh:datatype xsd:decimal ;
    sh:minExclusive 0 ;
    sh:maxExclusive 99999999 .

# 패턴 제약: email 형식
gr:CustomerEmailShape a sh:PropertyShape ;
    sh:path gr:email ;
    sh:pattern "^[\\w.-]+@[\\w.-]+\\.[a-z]{2,}$" .
```

```python
# pySHACL 통합 예시
from pyshacl import validate

def validate_with_shacl(
    ontology_graph: Graph,
    shapes_graph: Graph,
) -> tuple[bool, Graph, str]:
    """SHACL 검증 실행 → QualityReport 통합"""
    conforms, results_graph, results_text = validate(
        data_graph=ontology_graph,
        shacl_graph=shapes_graph,
        inference="rdfs",        # RDFS 추론 활성화
        abort_on_first=False,
    )
    return conforms, results_graph, results_text
```

**기존 quality_checker와의 통합**:

```python
# quality_checker.py 확장
def check_quality(ontology: OntologySpec) -> QualityReport:
    issues = []
    # 기존 5개 검사 (유지)
    issues.extend(_check_duplicate_classes(ontology))
    issues.extend(_check_domain_range(ontology))
    issues.extend(_check_circular_refs(ontology))
    issues.extend(_check_orphan_nodes(ontology))
    issues.extend(_check_naming_conventions(ontology))

    # NEW: SHACL 검증 (OWL 레이어 활성화 시)
    if settings.enable_owl:
        owl_graph = ontology_to_owl(ontology)
        shapes = load_domain_shapes(ontology.detected_domain)
        shacl_issues = _check_shacl(owl_graph, shapes)
        issues.extend(shacl_issues)

    return _build_report(issues)
```

**ROI: 중간** — 기존 검사를 표준화하고 카디널리티/값 범위 제약 추가.

---

#### (d) 쿼리 계층 강화

**실현 가능성: 중간 (난이도: 중-상)**

##### 추론 관계 → template_registry 자동 등록

```python
# OWL 추론으로 발견된 경로를 템플릿으로 변환
def infer_templates(owl_graph: Graph) -> list[TemplateSpec]:
    """OWL 프로퍼티 체인 → Cypher 템플릿 자동 생성"""
    templates = []
    for chain in owl_graph.subjects(OWL.propertyChainAxiom):
        chain_rels = list(Collection(owl_graph, chain))
        if len(chain_rels) == 2:
            templates.append(_make_two_hop_template(chain_rels))
        elif len(chain_rels) == 3:
            templates.append(_make_three_hop_template(chain_rels))
    return templates
```

##### graph_schema.py 확장 — OWL 메타데이터 주입

```python
# graph_schema.py 확장
def get_graph_schema(tenant_id: str | None = None) -> dict:
    schema = _get_neo4j_schema(tenant_id)  # 기존 로직

    if settings.enable_owl:
        owl_meta = get_owl_metadata(tenant_id)
        schema["owl_classes"] = owl_meta.get("classes", {})
        schema["owl_properties"] = owl_meta.get("properties", {})
        schema["inferred_paths"] = owl_meta.get("chains", [])
        schema["class_hierarchy"] = owl_meta.get("hierarchy", {})

    return schema

def format_schema_for_prompt(schema: dict) -> str:
    text = _format_neo4j_schema(schema)  # 기존

    if "class_hierarchy" in schema:
        text += "\n\nClass Hierarchy:\n"
        for cls, parents in schema["class_hierarchy"].items():
            text += f"  {cls} subClassOf {', '.join(parents)}\n"

    if "inferred_paths" in schema:
        text += "\nInferred Paths:\n"
        for path in schema["inferred_paths"]:
            text += f"  {' -> '.join(path)}\n"

    return text
```

##### LLM Router에 OWL 정보 주입

```python
# router_llm.py — 시스템 프롬프트 확장
_SYSTEM_PROMPT = """
Current graph schema:
{schema}

OWL Ontology Axioms:
{owl_axioms}

Use the class hierarchy and inferred paths to choose the most appropriate template.
If a question asks about a superclass, include all subclasses.
If a transitive property is available, prefer shorter path templates.
"""
```

**ROI: 높음** — LLM 라우터 정확도 향상 + 템플릿 자동 생성으로 도메인 범용성 대폭 개선.

---

## 2. 아키텍처 설계

### 2.1 파이프라인 삽입 위치

```
[DDL Parser] → ERDSchema
      ↓
[Domain Detection] → DomainHint
      ↓
[FK Rule Engine] → OntologySpec (baseline)        ← Stage 1
      ↓
[LLM Enricher] → OntologySpec (enriched)          ← Stage 2 (optional)
      ↓
┌─────────────────────────────────────────┐
│  NEW: OWL Conversion Layer              │        ← Stage 2.5
│  ontology_to_owl() → RDF Graph          │
│  + Domain OWL Axioms (DomainHint 연동)   │
│  + SHACL Shapes 생성                     │
└─────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────┐
│  NEW: OWL Reasoning                     │        ← Stage 2.7
│  Reasoner(OWL-RL/HermiT) → 추론 실행    │
│  → 추론된 관계/클래스 추출               │
│  → OntologySpec에 owl_inferred 관계 추가 │
└─────────────────────────────────────────┘
      ↓
[Quality Checker] → QualityReport                  ← Stage 3 (SHACL 확장)
      ↓
[Evaluation] → EvalMetrics                         ← Stage 4
      ↓
[PG Storage] → version_id                          ← Stage 5
      ↓                    ↓
[YAML Mapping]        [OWL Export]                  ← 병렬 출력
      ↓                    ↓
[KG Build] ←──── OWL Materialization               ← Stage 6 (추론 관계 물리화)
      ↓
[Query Pipeline] ←── OWL-enriched Schema           ← Stage 7 (스키마 주입)
```

### 2.2 신규 모듈 구조

```
backend/app/owl/
├── __init__.py
├── converter.py          # OntologySpec → RDF Graph (rdflib)
├── axiom_registry.py     # 도메인별 OWL axiom 레지스트리
├── reasoner.py           # Reasoner 실행 + 추론 결과 추출
├── shacl_generator.py    # OntologySpec → SHACL shapes
├── shacl_validator.py    # pySHACL 검증 래퍼
├── materializer.py       # 추론 결과 → Neo4j MERGE
└── schema_enricher.py    # graph_schema에 OWL 메타데이터 주입
```

### 2.3 기존 코드 수정 범위

| 파일 | 수정 내용 | 변경 규모 |
|------|----------|----------|
| `models/schemas.py` | `OntologyGenerateResponse.owl_axiom_count`, `RelationshipType.derivation`에 `"owl_inferred"` 추가 | 소 (+5줄) |
| `ontology/pipeline.py` | Stage 2.5/2.7 삽입, `enable_owl` 분기 | 중 (+40줄) |
| `ontology/quality_checker.py` | SHACL 검증 호출 추가 | 소 (+15줄) |
| `ontology/domain_hints.py` | `DomainHint.owl_axioms: list[str]` 필드 추가 | 소 (+10줄) |
| `db/graph_schema.py` | OWL 메타데이터 주입, `format_schema_for_prompt` 확장 | 중 (+30줄) |
| `query/router_llm.py` | 시스템 프롬프트에 OWL axiom 추가 | 소 (+10줄) |
| `query/local_search.py` | 서브그래프에 추론 관계 포함 | 소 (+15줄) |
| `kg_builder/loader.py` | 추론 관계 물리화 호출 | 소 (+10줄) |
| `config.py` | `enable_owl`, `owl_reasoner`, `owl_profile` 설정 | 소 (+5줄) |
| `requirements.txt` | `rdflib`, `owlrl`, `pyshacl` 추가 | 소 (+3줄) |
| `frontend/src/types/ontology.ts` | `owl_axiom_count` 타입 추가 | 소 (+3줄) |

### 2.4 Neo4j-Only 전략 (트리플스토어 이중화 X)

**결정: Neo4j-Only 유지**

이유:
1. OWL 추론은 rdflib 인메모리 그래프에서 수행 (외부 트리플스토어 불필요)
2. 추론 결과만 Neo4j에 물리화 (새 관계로 MERGE)
3. 프로젝트 규모(10-50 노드타입)에서 인메모리 추론 < 1초
4. Docker Compose에 추가 서비스 없음

```
rdflib Graph (인메모리)     Neo4j (영구 저장)
┌──────────────┐           ┌──────────────┐
│ OWL Classes  │           │ :Customer    │
│ OWL Props    │──추론──→  │ :Product     │
│ OWL Axioms   │  결과     │ :PLACED      │
│ SHACL Shapes │  물리화   │ :CLOSURE_OF  │ ← 추론 관계
└──────────────┘           └──────────────┘
     ↑                          ↑
  ontology_to_owl()      load_to_neo4j()
     ↑                          ↑
  OntologySpec ──────────────────┘
```

---

## 3. 단계별 개발 계획

### Phase 1: OWL 변환 기반 (Foundation)

**목표**: OntologySpec ↔ OWL/RDF 양방향 변환 + SHACL 기본 검증

**산출물**:

| 구분 | 파일 | 설명 |
|------|------|------|
| 신규 | `backend/app/owl/__init__.py` | 패키지 초기화 |
| 신규 | `backend/app/owl/converter.py` | `ontology_to_owl()`, `owl_to_ontology()` |
| 신규 | `backend/app/owl/shacl_generator.py` | `generate_shapes()` — OntologySpec → SHACL |
| 신규 | `backend/app/owl/shacl_validator.py` | `validate_shacl()` — pySHACL 래퍼 |
| 신규 | `backend/app/routers/owl.py` | `GET /api/v1/owl/export`, `POST /api/v1/owl/validate` |
| 신규 | `backend/tests/test_owl_converter.py` | OWL 변환 테스트 |
| 신규 | `backend/tests/test_shacl.py` | SHACL 검증 테스트 |
| 수정 | `requirements.txt` | `rdflib>=7.0`, `pyshacl>=0.25`, `owlrl>=7.0` 추가 |
| 수정 | `config.py` | `enable_owl: bool = False` 추가 |
| 수정 | `models/schemas.py` | `OntologyGenerateResponse.owl_axiom_count` 추가 |

**엔드포인트**:
- `GET /api/v1/owl/export/{version_id}` — OWL/XML 또는 Turtle 내보내기
- `POST /api/v1/owl/validate` — SHACL 검증 실행 (QualityReport 확장)

**의존성**: rdflib, pyshacl, owlrl (전부 pip install, Java 불필요)

**예상 테스트**: +20개
- OntologySpec → OWL 변환 정확성 (3 도메인 × 4 케이스 = 12)
- OWL → OntologySpec round-trip (3)
- SHACL 검증 (5: 통과/실패/카디널리티/패턴/값범위)

**리스크**:
- RDF 직렬화 포맷 호환성 → 완화: Turtle + RDF/XML 두 포맷 지원
- SHACL shapes의 도메인 특화 → 완화: 도메인 무관 기본 shapes + DomainHint 확장

---

### Phase 2: OWL Reasoning 엔진 (Core)

**목표**: OWL-RL 추론 실행 + 추론 결과 OntologySpec 반영 + Neo4j 물리화

**산출물**:

| 구분 | 파일 | 설명 |
|------|------|------|
| 신규 | `backend/app/owl/axiom_registry.py` | 도메인별 OWL axiom 레지스트리 |
| 신규 | `backend/app/owl/reasoner.py` | `run_reasoning()`, `extract_inferences()` |
| 신규 | `backend/app/owl/materializer.py` | `materialize_to_neo4j()` |
| 신규 | `backend/tests/test_owl_reasoning.py` | 추론 테스트 |
| 신규 | `backend/tests/test_owl_materializer.py` | 물리화 테스트 |
| 수정 | `ontology/pipeline.py` | Stage 2.5 (OWL 변환), Stage 2.7 (추론) 삽입 |
| 수정 | `ontology/domain_hints.py` | `DomainHint.owl_axioms` 필드 추가 |
| 수정 | `kg_builder/loader.py` | 추론 관계 물리화 후크 추가 |
| 수정 | `models/schemas.py` | `derivation: "owl_inferred"` 허용 |

**axiom_registry.py 예시**:

```python
# 도메인별 OWL axiom 정의
ECOMMERCE_AXIOMS = [
    # 전이적 관계
    ("PARENT_OF", "TransitiveProperty", "Category", "Category"),
    # 역관계
    ("PLACED", "inverseOf", "PLACED_BY"),
    ("CONTAINS", "inverseOf", "CONTAINED_IN"),
    # 프로퍼티 체인
    ("CUSTOMER_CATEGORY", "propertyChain", ["PLACED", "CONTAINS", "BELONGS_TO"]),
    # Disjoint 클래스
    ("Customer", "disjointWith", "Product"),
    ("Order", "disjointWith", "Category"),
]

EDUCATION_AXIOMS = [
    ("REQUIRES", "TransitiveProperty", "Course", "Course"),
    ("TEACHES", "inverseOf", "TAUGHT_BY"),
    ("STUDENT_DEPARTMENT", "propertyChain", ["ENROLLED_IN", "OFFERED_BY"]),
    ("Student", "disjointWith", "Instructor"),
]

INSURANCE_AXIOMS = [
    ("COVERS", "inverseOf", "COVERED_BY"),
    ("POLICYHOLDER_CLAIM", "propertyChain", ["HOLDS", "HAS_CLAIM"]),
    ("Policy", "disjointWith", "Claim"),
]
```

**reasoner.py 핵심 로직**:

```python
from owlrl import DeductiveClosure, OWLRL_Semantics
from rdflib import Graph

def run_reasoning(
    owl_graph: Graph,
    axioms: list[tuple],
) -> tuple[Graph, list[dict]]:
    """OWL-RL 추론 실행, 새 트리플 반환"""
    # 1. axiom 적용
    for axiom in axioms:
        _apply_axiom(owl_graph, axiom)

    # 2. 추론 전 트리플 수 기록
    before_count = len(owl_graph)

    # 3. OWL-RL 추론 실행 (인메모리, Java 불필요)
    DeductiveClosure(OWLRL_Semantics).expand(owl_graph)

    # 4. 새로 추론된 트리플 추출
    after_count = len(owl_graph)
    inferences = _extract_new_triples(owl_graph, before_count)

    return owl_graph, inferences
```

**의존성**: Phase 1 완료

**예상 테스트**: +18개
- 전이적 추론 (3 도메인 × 2 = 6)
- 프로퍼티 체인 (3 도메인 × 1 = 3)
- 역관계 (3)
- Disjoint 검증 (3)
- 물리화 (3)

**리스크**:
- OWL-RL이 프로퍼티 체인 미지원 → 완화: 커스텀 체인 추론 로직 구현
- 추론 결과 폭발 (과다 트리플) → 완화: 도메인 axiom을 보수적으로 정의, 추론 트리플 상한 설정

---

### Phase 3: 쿼리 계층 강화 (Integration)

**목표**: OWL 추론 결과를 query router/pipeline에 반영

**산출물**:

| 구분 | 파일 | 설명 |
|------|------|------|
| 신규 | `backend/app/owl/schema_enricher.py` | graph_schema에 OWL 메타데이터 주입 |
| 신규 | `backend/tests/test_owl_query_integration.py` | 쿼리 통합 테스트 |
| 수정 | `db/graph_schema.py` | `get_graph_schema()` OWL 메타데이터 병합 |
| 수정 | `query/router_llm.py` | 시스템 프롬프트에 OWL axiom 추가 |
| 수정 | `query/template_registry.py` | 추론 기반 동적 템플릿 등록 |
| 수정 | `query/local_search.py` | 서브그래프에 추론 관계 포함 |
| 수정 | `query/pipeline.py` | OWL 경로 우선 라우팅 |

**schema_enricher.py 핵심**:

```python
def enrich_schema_with_owl(
    neo4j_schema: dict,
    owl_graph: Graph,
) -> dict:
    """Neo4j 스키마에 OWL 메타데이터 병합"""
    enriched = dict(neo4j_schema)

    # 클래스 계층
    hierarchy = {}
    for cls in owl_graph.subjects(RDF.type, OWL.Class):
        parents = list(owl_graph.objects(cls, RDFS.subClassOf))
        if parents:
            hierarchy[_local_name(cls)] = [_local_name(p) for p in parents]
    enriched["class_hierarchy"] = hierarchy

    # 추론된 경로
    chains = []
    for prop in owl_graph.subjects(OWL.propertyChainAxiom):
        chain = list(Collection(owl_graph, owl_graph.value(prop, OWL.propertyChainAxiom)))
        chains.append([_local_name(r) for r in chain])
    enriched["inferred_paths"] = chains

    # 전이적 관계
    enriched["transitive_properties"] = [
        _local_name(p)
        for p in owl_graph.subjects(RDF.type, OWL.TransitiveProperty)
    ]

    return enriched
```

**의존성**: Phase 2 완료

**예상 테스트**: +15개
- OWL-enriched 스키마 포맷 (3)
- LLM router OWL prompt 주입 (3)
- 동적 템플릿 생성 (3)
- local_search 추론 관계 포함 (3)
- E2E OWL 쿼리 (3)

**리스크**:
- LLM router 프롬프트 길이 증가 → 완화: 상위 10개 axiom만 주입
- 동적 템플릿 정확도 → 완화: 기존 하드코딩 템플릿은 유지, 동적 템플릿은 보조

---

### Phase 4: Frontend + 도메인 확장 (Polish)

**목표**: OWL 시각화 UI + 도메인별 axiom 편집 + 전체 통합 테스트

**산출물**:

| 구분 | 파일 | 설명 |
|------|------|------|
| 신규 | `frontend/src/components/review/OWLAxiomPanel.tsx` | OWL axiom 뷰어/에디터 |
| 신규 | `frontend/src/components/review/SHACLReportPanel.tsx` | SHACL 검증 결과 표시 |
| 수정 | `frontend/src/pages/ReviewPage.tsx` | OWL 탭 추가 |
| 수정 | `frontend/src/api/client.ts` | `exportOWL()`, `validateSHACL()` API 래퍼 |
| 수정 | `frontend/src/types/ontology.ts` | OWL 관련 타입 추가 |
| 신규 | `backend/tests/test_owl_e2e.py` | 전체 E2E 테스트 (DDL→OWL→추론→KG→Query) |

**의존성**: Phase 3 완료

**예상 테스트**: +12개

**리스크**:
- 프론트엔드 복잡도 증가 → 완화: 기존 탭 UI 패턴 재활용 (YAML 탭 참조)

---

### Phase 요약

| Phase | 목표 | 기간 | 새 파일 | 수정 파일 | 테스트 추가 | 누적 테스트 |
|-------|------|------|--------|----------|-----------|-----------|
| **P1** | OWL 변환 + SHACL | 1주 | 6 | 3 | +20 | 373 |
| **P2** | OWL 추론 엔진 | 1주 | 5 | 4 | +18 | 391 |
| **P3** | 쿼리 계층 강화 | 1주 | 2 | 5 | +15 | 406 |
| **P4** | Frontend + E2E | 1주 | 3 | 4 | +12 | 418 |
| **합계** | | **4주** | **16** | **16** | **+65** | **418** |

---

## 4. 도메인별 임팩트 분석

### 4.1 E-Commerce

**가장 큰 가치**: 카테고리 계층 추론 + 프로퍼티 체인

```
# OWL Manchester Syntax
Class: ElectronicsProduct
    SubClassOf: Product
    EquivalentTo: Product and (BELONGS_TO some Electronics)

ObjectProperty: PARENT_OF
    Characteristics: Transitive
    Domain: Category
    Range: Category

ObjectProperty: CUSTOMER_CATEGORY
    SubPropertyChain: PLACED o CONTAINS o BELONGS_TO
```

**사용 예시**:
1. "노트북 카테고리와 하위 카테고리의 총 매출은?" → PARENT_OF 전이적 추론으로 모든 서브카테고리 자동 포함
2. "김민수가 관심 있는 카테고리는?" → CUSTOMER_CATEGORY 프로퍼티 체인으로 1-hop 쿼리 가능 (현재: 3-hop 필요)
3. "전자제품 구매 고객에게 오디오 제품 추천" → 카테고리 계층 활용

**기존 DomainHint와의 관계**:

```python
# domain_hints.py 확장
ECOMMERCE_HINT = DomainHint(
    name="ecommerce",
    # ... 기존 필드 유지 ...
    owl_axioms=[                                    # NEW
        ("PARENT_OF", "TransitiveProperty", "Category", "Category"),
        ("PLACED", "inverseOf", "PLACED_BY"),
        ("CUSTOMER_CATEGORY", "propertyChain", ["PLACED", "CONTAINS", "BELONGS_TO"]),
    ],
)
```

DomainHint.owl_axioms = 도메인별 OWL TBox의 선언적 정의. axiom_registry.py에서 이를 읽어 OWL Graph에 적용.

### 4.2 Education

**가장 큰 가치**: 선수과목 전이적 추론 + 학생→학과 체인

```
# OWL Manchester Syntax
ObjectProperty: REQUIRES
    Characteristics: Transitive
    Domain: Course
    Range: Course

ObjectProperty: STUDENT_DEPARTMENT
    SubPropertyChain: ENROLLED_IN o OFFERED_BY

Class: GraduateCourse
    SubClassOf: Course
    EquivalentTo: Course and (hasLevel value "graduate")
```

**사용 예시**:
1. "데이터베이스 과목의 모든 선수과목 체인은?" → REQUIRES 전이적 추론 (현재: 수동 multi-hop)
2. "컴퓨터공학과 학생 수는?" → STUDENT_DEPARTMENT 체인으로 1-hop (현재: 2-hop ENROLLED_IN → OFFERED_BY)
3. "대학원 과목을 수강 중인 학부생은?" → GraduateCourse 서브클래스 인식

### 4.3 Insurance

**가장 큰 가치**: 보장→제외 상호 배타 + 보험계약자→청구 체인

```
# OWL Manchester Syntax
ObjectProperty: COVERS
    Domain: Policy
    Range: Coverage
    InverseOf: COVERED_BY

ObjectProperty: EXCLUDES
    Domain: Policy
    Range: Exclusion

Class: Coverage
    DisjointWith: Exclusion

ObjectProperty: POLICYHOLDER_CLAIM
    SubPropertyChain: HOLDS o HAS_CLAIM

ObjectProperty: HAS_CLAIM
    Characteristics: InverseFunctional  # 하나의 청구는 하나의 보험에만 귀속
```

**사용 예시**:
1. "보험계약자 홍길동의 모든 청구 현황은?" → POLICYHOLDER_CLAIM 체인으로 1-hop
2. "보장과 제외가 동시에 적용된 항목은?" → DisjointWith 위반 탐지 (데이터 품질)
3. "하나의 보험에 청구가 여러 개 있는 경우는?" → InverseFunctional 위반 감지

### 4.4 도메인 무관 (미등록 도메인)

OWL 기본 axiom만 적용:
- 네이밍 기반 자동 역관계 생성 (PLACED ↔ PLACED_BY)
- 자기 참조 관계 TransitiveProperty 후보 탐지
- Domain/Range 기반 기본 SHACL shapes 생성

---

## 5. 트레이드오프 분석

### 5.1 성능

| 시나리오 | 현재 | OWL 추가 후 | 차이 |
|---------|------|-----------|------|
| 온톨로지 생성 | ~200ms | ~400ms (+OWL 변환 + 추론) | +200ms |
| KG 빌드 | ~3s | ~3.5s (+물리화) | +500ms |
| 쿼리 (Mode A) | ~100ms | ~100ms (캐시된 스키마) | 0 |
| 쿼리 (Mode B) | ~2s | ~2s (LLM 지배적) | 0 |

**결론**: 온톨로지 생성 시 1회성 비용. 쿼리 타임에는 영향 없음.

### 5.2 복잡도 vs 가치

```
                높음
                 │
     가         │    ★ 전이적 추론    ★ 프로퍼티 체인
     치         │    ★ SHACL 검증     ★ LLM router 강화
                │
                │    ○ 클래스 계층     ○ 역관계
                │
                │    △ OWL Export      △ 프론트엔드 UI
     낮음       │
                └────────────────────────────
                  낮음                높음
                        구현 난이도
```

### 5.3 대안 비교

| 접근법 | 장점 | 단점 | 적합도 |
|--------|------|------|--------|
| **OWL Reasoner (rdflib+OWL-RL)** | 표준 기반, 선언적 axiom, 자동 추론 | 학습 곡선, RDF 변환 필요 | **높음** |
| **Neo4j GDS** | APOC/GDS 프로시저로 그래프 알고리즘 | Community Edition 제한, 추론 아닌 분석 | 중간 |
| **LLM 직접 추론** | 구현 단순, 유연함 | 비결정적, API 비용, 환각 위험 | 낮음 |
| **커스텀 Python 규칙** | 의존성 최소, 빠름 | 유지보수 부담, 표준 아님, 확장 어려움 | 중간 |

### 5.4 최소 구현 MVP: 최고 ROI 단일 기능

**MVP 추천: 전이적 관계 추론 + Neo4j 물리화**

이유:
1. 3개 도메인 모두에서 즉시 가치 (PARENT_OF, REQUIRES, 체인)
2. 구현량 최소 (~150줄)
3. LLM 없이 동작 (Graceful Degradation 유지)
4. 쿼리 정확도 직접 향상 (3-hop → 1-hop)

```python
# MVP 전체 코드 (~50줄 핵심)
def infer_and_materialize_transitive(
    ontology: OntologySpec,
    driver,
    tenant_id: str | None = None,
) -> int:
    """전이적 관계 추론 + Neo4j 물리화 (MVP)"""
    # 1. 자기 참조 관계 = 전이적 후보
    transitive_rels = [
        rel for rel in ontology.relationship_types
        if rel.source_node == rel.target_node
    ]

    total_created = 0
    for rel in transitive_rels:
        label = rel.source_node
        prefix = f"{tenant_id}:" if tenant_id else ""
        cypher = f"""
        MATCH (a:`{prefix}{label}`)-[:`{rel.name}`*2..5]->(b:`{prefix}{label}`)
        WHERE a <> b AND NOT (a)-[:`{rel.name}_CLOSURE`]->(b)
        MERGE (a)-[r:`{rel.name}_CLOSURE`]->(b)
        SET r.inferred = true, r.derivation = 'owl_transitive'
        RETURN count(r) AS created
        """
        with driver.session() as session:
            result = session.run(cypher)
            total_created += result.single()["created"]

    return total_created
```

---

## 6. 최종 추천

### 이렇게 하세요

#### 기술 스택 선택
```
rdflib 7.x + owlrl 7.x + pyshacl 0.25+
```
- Java 불필요 (Docker Compose 변경 없음)
- 순수 Python (기존 기술 스택과 일관)
- pip install 3줄로 끝남
- 프로젝트 규모(10-50 노드타입)에서 성능 충분

#### 구현 순서

```
[즉시] MVP: 전이적 관계 추론 + 물리화 (1-2일)
  ↓
[Phase 1] OWL 변환 + SHACL 검증 (1주)
  ↓
[Phase 2] OWL 추론 엔진 + axiom 레지스트리 (1주)
  ↓
[Phase 3] 쿼리 계층 OWL 통합 (1주)
  ↓
[Phase 4] Frontend + E2E (1주)
```

#### 핵심 원칙
1. **`enable_owl: bool = False`** — 기본 비활성화, 기존 353개 테스트 영향 없음
2. **Graceful Degradation** — OWL 추론 실패 시 기존 파이프라인 그대로 동작
3. **Materialization 우선** — 추론 결과를 Neo4j에 물리화하여 쿼리 타임 영향 제로
4. **도메인 Axiom은 DomainHint 확장** — 기존 플러거블 구조 재활용
5. **derivation: "owl_inferred"** — 기존 fk_direct/fk_join_table/llm_suggested와 일관된 추적

#### 우선순위 매트릭스

```
┌─────────────────────────┬──────────┬────────┬──────────┐
│ 기능                     │ Impact   │ Effort │ Priority │
├─────────────────────────┼──────────┼────────┼──────────┤
│ 전이적 관계 추론          │ ★★★★★   │ ★★     │ P0       │
│ SHACL 기본 검증           │ ★★★★    │ ★★     │ P0       │
│ OntologySpec→OWL 변환     │ ★★★★    │ ★      │ P0       │
│ 프로퍼티 체인 추론         │ ★★★★    │ ★★★    │ P1       │
│ LLM router OWL 주입       │ ★★★★    │ ★★     │ P1       │
│ 도메인별 axiom 레지스트리  │ ★★★     │ ★★     │ P1       │
│ 클래스 계층 추론           │ ★★★     │ ★★★    │ P2       │
│ 역관계 자동 생성           │ ★★      │ ★      │ P2       │
│ 동적 템플릿 생성           │ ★★★     │ ★★★★   │ P2       │
│ OWL Frontend UI           │ ★★      │ ★★★    │ P3       │
│ Disjoint 검증             │ ★★      │ ★      │ P3       │
│ OWL Export 엔드포인트      │ ★       │ ★      │ P3       │
└─────────────────────────┴──────────┴────────┴──────────┘
```

#### 비용 요약

| 항목 | 수량 |
|------|------|
| 신규 파일 | 16개 |
| 수정 파일 | 16개 |
| 신규 테스트 | +65개 (353→418) |
| 신규 pip 패키지 | 3개 (rdflib, owlrl, pyshacl) |
| Docker 변경 | 없음 |
| 총 기간 | 4주 (MVP는 1-2일) |
