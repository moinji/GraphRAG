# GraphRAG v4.0 개발 보고서 — 도메인 무관 온톨로지 + YAML 매핑 + 범용 쿼리
> 작성일: 2026-03-10 | 버전: 4.0.0

---

## 1. 요약

v4.0은 **이커머스 전용 → 도메인 무관(domain-agnostic)** 전환이 핵심입니다. 교육, 보험 등 어떤 도메인의 DDL을 넣어도 자동으로 온톨로지를 생성하고, KG를 구축하고, 질의-응답까지 수행할 수 있습니다.

| Feature | 설명 | 상태 |
|---------|------|------|
| **F-01** 도메인 무관 온톨로지 | DomainHint 시스템 + 품질 검증 + 자동 감지 | DONE |
| **F-02** YAML 매핑 레이어 | R2RML 호환, 라운드트립 보장, 4개 API | DONE |
| **F-03** KG 빌드 엔진 보강 | error_count 추적, 스키마 캐시 무효화 | DONE |
| **F-04** 도메인 무관 쿼리 | Neo4j 스키마 인트로스펙션, LLM 라우터 스키마 주입 | DONE |
| **프론트엔드** | 도메인 선택, 품질 점수, YAML 뷰어/편집기 | DONE |
| **데모 DDL** | 교육(11 tables) + 보험(12 tables) 예제 스키마 | DONE |

**변경 규모**: 40 files changed, 3,236 insertions, 177 deletions

---

## 2. F-01: 도메인 무관 온톨로지

### 2.1 DomainHint 시스템 (`domain_hints.py`, 295줄)

```
[DDL 업로드] → detect_domain(erd) → DomainHint 선택 → fk_rule_engine + llm_enricher
                                      ↓
                              signature_tables 매칭
                              ecommerce: orders, products, customers
                              education: courses, students, enrollments
                              insurance: policies, claims, policyholders
```

- `DomainHint` dataclass: `table_to_label`, `join_table_config`, `direction_map`, `signature_tables`, `llm_prompt_hint`
- `detect_domain(erd)`: 테이블명 기반 자동 감지 (overlap ≥ 3 → 도메인 확정)
- 3개 도메인 사전 등록: ecommerce, education, insurance
- 감지 실패 시 generic fallback (기존 FK 규칙 적용)

### 2.2 품질 검증기 (`quality_checker.py`, 240줄)

Protégé 5대 검증 규칙 구현:

| 검증 | 심각도 | 설명 |
|------|--------|------|
| Duplicate Classes | error | 대소문자 무시 중복 노드명 |
| Domain/Range | error | 관계의 source/target 노드 존재 검증 |
| Circular References | warning | DFS 기반 순환 참조 탐지 (self-ref 제외) |
| Orphan Nodes | warning | 관계 없는 고립 노드 |
| Naming Conventions | warning | PascalCase 노드, UPPER_SNAKE 관계 |

- 점수 산출: 1.0 기준, error -0.2, warning -0.05 감점
- `check_quality(ontology)` → `QualityReport(score, issues[])`

### 2.3 파이프라인 통합

`ontology/pipeline.py` 변경:
1. `domain` 파라미터 추가 (None = 자동 감지)
2. `DomainHint` → `fk_rule_engine`에 전달 (table_to_label, join_table_config, direction_map)
3. `DomainHint.llm_prompt_hint` → LLM enricher 시스템 프롬프트에 주입
4. 파이프라인 완료 후 `check_quality()` 실행 → 응답에 `quality_score`, `detected_domain` 포함

---

## 3. F-02: YAML 매핑 레이어

### 3.1 아키텍처

```
OntologySpec ──→ generator.py ──→ DomainMappingConfig ──→ YAML 문자열
                                        ↑↓ 라운드트립
OntologySpec ←── converter.py ←── DomainMappingConfig ←── YAML 문자열
                                        │
                                  validator.py (구조 검증)
```

### 3.2 R2RML 호환 모델 (`mapping/models.py`, 95줄)

```yaml
triples_maps:
  - id: "TM_Customer"
    logical_table:
      table_name: "customers"
    subject_map:
      class: "Customer"
      template: "{id}"
    properties:
      - name: "name"
        column: "name"
        datatype: "string"
        is_key: true

relationship_maps:
  - id: "RM_PLACED"
    source_triples_map: "TM_Customer"
    target_triples_map: "TM_Order"
    relationship_type: "PLACED"
    derivation: "fk_direct"
```

### 3.3 API 엔드포인트 (`routers/mapping.py`, 152줄)

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/mapping/generate` | 승인된 온톨로지 → YAML 생성 |
| GET | `/api/v1/mapping/{version_id}` | YAML 조회 (없으면 자동 생성) |
| PUT | `/api/v1/mapping/{version_id}` | YAML 수정 (검증 후 저장) |
| GET | `/api/v1/mapping/{version_id}/preview` | UI 요약 (노드/관계 수, 테이블 매핑) |

### 3.4 라운드트립 검증

`OntologySpec → YAML → OntologySpec` 왕복 변환 후 동일성 보장:
- 노드 타입 수, 관계 타입 수 일치
- 속성명, 데이터 타입 보존
- join_table 속성 (quantity, unit_price) 유지

---

## 4. F-03: KG 빌드 엔진 보강

### 4.1 error_count 추적

`KGBuildProgress` 모델에 `error_count: int = 0` 필드 추가. FK 무결성 검증 실패 건수를 추적하여 프론트엔드에서 경고 배지 표시.

```python
fk_error_count = len(violations)
progress = KGBuildProgress(
    status="succeeded",
    error_count=fk_error_count,
    ...
)
```

### 4.2 스키마 캐시 무효화

KG 재빌드 후 `invalidate_schema_cache(tenant_id)` 호출 → LLM 라우터가 새 스키마를 즉시 반영.

---

## 5. F-04: 도메인 무관 쿼리

### 5.1 그래프 스키마 인트로스펙션 (`db/graph_schema.py`, 153줄)

```
Neo4j ──CALL db.labels()──────────────→ node_labels: ["Customer", "Order", ...]
      ──CALL db.relationshipTypes()───→ relationship_types: ["PLACED", ...]
      ──MATCH (n) RETURN keys(n)──────→ node_properties: {"Customer": ["name", ...]}
      ──MATCH ()-[r]->() RETURN keys──→ relationship_properties: {...}
```

- 5분 TTL 캐시 (tenant별 독립)
- `format_schema_for_prompt(schema)` → LLM 시스템 프롬프트용 텍스트 포맷

### 5.2 LLM 라우터 스키마 주입 (`router_llm.py`)

**Before** (하드코딩):
```
Available node types: Customer, Product, Order, ...
```

**After** (동적):
```python
schema = get_graph_schema(tenant_id)
prompt = _SYSTEM_PROMPT.format(
    templates=template_text,
    schema=format_schema_for_prompt(schema)
)
```

### 5.3 Local Search 범용화 (`local_search.py`)

| 항목 | Before | After |
|------|--------|-------|
| `_FALLBACK_ENTITIES` | 이커머스 고정 dict | `{}` (빈 dict) |
| 엔티티 추출 | 하드코딩 규칙 | `_load_entities_from_neo4j()` 동적 로드 |
| 집계 쿼리 | 7개 고정 Cypher | `_build_generic_aggregate(tenant_id)` 스키마 기반 생성 |

---

## 6. 프론트엔드 v4.0

### 6.1 UploadPage — 도메인 선택

```
┌─────────────────────────────────┐
│  도메인 선택  [▼ 자동 감지    ] │
│               E-Commerce        │
│               Education         │
│               Insurance         │
└─────────────────────────────────┘
```

`generateOntology(erd, skipLlm, domain)` — optional domain 파라미터 추가

### 6.2 ReviewPage — 품질 점수 + YAML 매핑

헤더 배지:
- `detected_domain` — 보라색 배지 (예: "Education")
- `quality_score` — 녹색(≥80%) / 주황(≥50%) / 빨강(<50%)

새로운 "매핑 (YAML)" 탭:
- YAML 생성/조회/편집/저장 UI
- 구조 검증 후 경고 표시
- monospace 에디터 (textarea)

### 6.3 새로운 API 클라이언트 함수

```typescript
generateMapping(versionId: number): Promise<MappingGenerateResponse>
getMapping(versionId: number): Promise<string>
updateMapping(versionId: number, yamlContent: string): Promise<void>
getMappingPreview(versionId: number): Promise<MappingPreview>
```

---

## 7. 데모 도메인 스키마

| 도메인 | 파일 | 테이블 | FK |
|--------|------|--------|-----|
| E-Commerce | `demo_ecommerce.sql` | 12 | 15 |
| Education | `demo_education.sql` | 11 | 15 |
| Insurance | `demo_insurance.sql` | 12 | 12 |
| Accounting | `demo_accounting.sql` | 10 | — |
| HR | `demo_hr.sql` | 11 | — |
| Hospital | `demo_hospital.sql` | 11 | — |

교육/보험 DDL은 `DomainHint.signature_tables`와 정확히 매칭되어 자동 감지 검증 가능.

---

## 8. 테스트 현황

| 카테고리 | 테스트 수 |
|---------|----------|
| 기존 테스트 | 308 |
| 도메인 힌트 + 품질 검증 (신규) | 13 |
| YAML 매핑 (신규) | 20 |
| 그래프 스키마 + 범용 쿼리 (신규) | 12 |
| **합계** | **353 passed** |

테스트 파일 19개, 프론트엔드 빌드 클린 (`npm run build` 성공).

---

## 9. 파일 변경 내역

### 신규 파일 (12개)

| 파일 | 줄 수 | 설명 |
|------|-------|------|
| `backend/app/ontology/domain_hints.py` | 295 | DomainHint 시스템 (3개 도메인) |
| `backend/app/ontology/quality_checker.py` | 240 | Protégé 5대 품질 검증 |
| `backend/app/mapping/__init__.py` | — | 매핑 패키지 |
| `backend/app/mapping/models.py` | 95 | R2RML Pydantic 모델 |
| `backend/app/mapping/generator.py` | 164 | OntologySpec → YAML 변환기 |
| `backend/app/mapping/converter.py` | 79 | YAML → OntologySpec 역변환 |
| `backend/app/mapping/validator.py` | 77 | YAML 구조 검증기 |
| `backend/app/db/graph_schema.py` | 153 | Neo4j 스키마 인트로스펙션 |
| `backend/app/routers/mapping.py` | 152 | 매핑 CRUD API 4개 |
| `backend/tests/test_domain_hints.py` | 368 | 도메인 힌트 테스트 13개 |
| `backend/tests/test_graph_schema.py` | 249 | 스키마 인트로스펙션 테스트 12개 |
| `backend/tests/test_mapping.py` | 372 | YAML 매핑 테스트 20개 |

### 주요 수정 파일

| 파일 | 변경 |
|------|------|
| `ontology/pipeline.py` | domain 파라미터, DomainHint 통합, quality_score 반환 |
| `ontology/fk_rule_engine.py` | DomainHint 주입 (table_to_label, join_table_config, direction_map) |
| `ontology/prompts.py` | domain_hint 시스템 프롬프트 주입 |
| `ontology/llm_enricher.py` | domain_hint 파라미터 전달 |
| `query/router_llm.py` | 동적 스키마 주입 (tenant_id 전달) |
| `query/router.py` | tenant_id 전달 |
| `query/pipeline.py` | tenant_id 전달 |
| `query/local_search.py` | 동적 엔티티 로드 + 범용 집계 Cypher |
| `kg_builder/service.py` | error_count + schema cache invalidation |
| `models/schemas.py` | KGBuildProgress.error_count, 매핑 관련 모델 |
| `frontend/src/pages/UploadPage.tsx` | 도메인 선택 드롭다운 |
| `frontend/src/pages/ReviewPage.tsx` | 품질 배지 + YAML 매핑 탭 |
| `frontend/src/api/client.ts` | 매핑 API 함수 4개 |
| `frontend/src/types/ontology.ts` | v4.0 TS 타입 추가 |

---

## 10. 기술적 의사결정

### Q: 왜 YAML인가? (JSON이 아니라)
R2RML 표준이 Turtle/XML 기반이지만, 실무에서 YAML이 가독성과 편집 편의성 면에서 우수. 라운드트립 보장으로 YAML ↔ OntologySpec 자유 변환 가능.

### Q: 왜 Neo4j 인트로스펙션인가? (온톨로지에서 읽으면 되지 않나)
KG 빌드 후 실제 적재된 레이블/속성이 온톨로지와 다를 수 있음 (필터링, 변환 등). 실제 그래프 상태 기반 라우팅이 정확도 높음.

### Q: DomainHint 확장은?
새 도메인 추가 = `DomainHint` 인스턴스 1개 + `_HINT_REGISTRY` 등록. 코드 수정 최소화.

---

## 11. 다음 단계

| 우선순위 | 항목 | 설명 |
|---------|------|------|
| P0 | 실 사용자 피드백 | 교육/보험 DDL로 E2E 테스트 |
| P1 | CSV 데이터 도메인 확장 | 교육/보험용 샘플 CSV 데이터 |
| P1 | YAML 편집 후 KG 재빌드 | 매핑 수정 → KG 반영 파이프라인 |
| P2 | 도메인 힌트 커스텀 등록 UI | 사용자 정의 DomainHint |
| P2 | 쿼리 템플릿 자동 생성 | 스키마 기반 Cypher 템플릿 자동 생성 |
