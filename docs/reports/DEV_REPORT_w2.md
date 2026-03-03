# Week 2 개발 보고서 — FK 규칙 온톨로지 API + LLM 보강 + 평가 자동화
> 작성일: 2026-02-24 | 목적: 2단계 온톨로지 파이프라인 + Claude LLM 보강 + 평가 엔진 + PG 버전 저장

---

## 1. 요약

FK 규칙 엔진(Stage 1) 위에 **Claude LLM 보강(Stage 2), 골든 데이터 평가 엔진, PostgreSQL 버전 저장**을 추가하여 온톨로지 생성 API를 완성했습니다.

| 지표 | 목표 | 실제 | 상태 |
|------|------|------|------|
| POST /api/v1/ontology/generate | 200 | 200 | PASS |
| FK 베이스라인 노드 수 | 9 | 9 | PASS |
| FK 베이스라인 관계 수 | 12 | 12 | PASS |
| 치명 오류율 (critical_error_rate) | 0% | 0% | PASS |
| FK 관계 커버리지 | 100% | 100% | PASS |
| 방향 정확도 | 100% | 100% | PASS |
| 온톨로지 단위/통합 테스트 | 16/16 | 16/16 | PASS |
| 전체 테스트 (기존 + 신규) | 36/36 | 36/36 | PASS |
| demo.py 하위 호환 | All 5 steps | All 5 steps | PASS |

---

## 2. 구현 범위

### 신규 파일 (10개)

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `app/ontology/pipeline.py` | 94 | 2단계 파이프라인 오케스트레이터 |
| `app/ontology/llm_enricher.py` | 126 | Stage 2: Claude API 호출 + diff 계산 |
| `app/ontology/prompts.py` | 82 | Core 시스템 프롬프트 + 이커머스 도메인 힌트 |
| `app/evaluation/evaluator.py` | 80 | 생성 vs 골든 비교 평가 (4개 지표) |
| `app/evaluation/golden_ecommerce.py` | 41 | 골든 데이터 (9노드, 12관계) |
| `app/db/pg_client.py` | 104 | PG 연결 + ontology_versions CRUD |
| `app/routers/ontology.py` | 20 | `POST /api/v1/ontology/generate` |
| `app/db/__init__.py` | 0 | 패키지 init |
| `app/evaluation/__init__.py` | 0 | 패키지 init |
| `tests/test_ontology.py` | 230 | 온톨로지 단위/통합 테스트 16개 |
| **합계** | **777** | |

### 수정 파일 (7개)

| 파일 | 변경 내용 |
|------|----------|
| `app/config.py` | `anthropic_api_key`, `anthropic_model` 필드 추가 |
| `app/exceptions.py` | `OntologyGenerationError`(422), `LLMEnrichmentError`(502), `DatabaseError`(500) + 핸들러 3개 추가 |
| `app/models/schemas.py` | `OntologyGenerateRequest`, `LLMEnrichmentDiff`, `EvalMetrics`, `OntologyGenerateResponse` 4개 모델 추가 |
| `app/main.py` | 온톨로지 라우터 등록, 예외 핸들러 등록, startup PG 테이블 생성 |
| `app/ontology/fk_rule_engine.py` | 조인테이블 관계에 `properties=rel_props` 누락 버그 수정 |
| `tests/conftest.py` | `ecommerce_erd` 픽스처 추가 (파싱된 ERDSchema) |
| `requirements.txt` | `anthropic>=0.42.0`, `pytest-asyncio>=0.23.0` 추가 |
| `.env.example` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` 추가 |

---

## 3. 아키텍처 — 2단계 파이프라인

```
┌─────────────────────────────────────────────────────┐
│  POST /api/v1/ontology/generate                     │
│  { erd: ERDSchema, skip_llm: bool }                 │
└───────────────┬─────────────────────────────────────┘
                │
    ┌───────────▼───────────┐
    │  Stage 1: FK 규칙 엔진  │  ← build_ontology(erd)
    │  (항상 실행, 결정적)     │     9노드, 12관계
    └───────────┬───────────┘
                │
    ┌───────────▼───────────┐
    │  Stage 2: Claude LLM   │  ← skip_llm=true → 스킵
    │  (선택적, 비치명적)      │     API키 없음 → 스킵
    └───────────┬───────────┘     실패 → 경고 로그, 베이스라인 유지
                │
    ┌───────────▼───────────┐
    │  평가 엔진              │  ← evaluate(ontology, golden)
    │  (4개 지표 산출)         │     치명오류율, 커버리지, 방향, LLM채택률
    └───────────┬───────────┘
                │
    ┌───────────▼───────────┐
    │  PG 버전 저장           │  ← best-effort
    │  (ERD 해시 + JSONB)     │     실패 → version_id=null
    └───────────┬───────────┘
                │
    ┌───────────▼───────────┐
    │  OntologyGenerateResponse │
    │  { ontology, eval_report, │
    │    llm_diffs, version_id, │
    │    stage }                 │
    └───────────────────────────┘
```

### 핵심 설계 원칙

| # | 원칙 | 구현 |
|---|------|------|
| 1 | **LLM 실패 = 비치명적** | Claude 호출 실패 시 FK 베이스라인 유지, `stage="fk_only"` |
| 2 | **PG 실패 = 비치명적** | DB 다운 시 `version_id=null`, 나머지 정상 반환 |
| 3 | **동기 파이프라인** | `build_ontology` + `anthropic SDK` 모두 동기, FastAPI threadpool 위임 |
| 4 | **골든 데이터 도메인별 분리** | `golden_ecommerce.py`, 향후 도메인 추가 시 별도 파일 |
| 5 | **ERD 해시 캐시 키** | SHA-256, 같은 ERD 재요청 시 기존 버전 조회 가능 (향후) |

---

## 4. API 엔드포인트

### `POST /api/v1/ontology/generate`

**Request:**
```json
{
  "erd": {
    "tables": [{"name": "customers", "columns": [...], "primary_key": "id"}, ...],
    "foreign_keys": [{"source_table": "orders", "source_column": "customer_id", "target_table": "customers", "target_column": "id"}, ...]
  },
  "skip_llm": false
}
```

**Response (200) — FK only:**
```json
{
  "ontology": {
    "node_types": [{"name": "Customer", "source_table": "customers", "properties": [...]}, ...],
    "relationship_types": [{"name": "PLACED", "source_node": "Customer", "target_node": "Order", "derivation": "fk_direct", ...}, ...]
  },
  "eval_report": {
    "critical_error_rate": 0.0,
    "fk_relationship_coverage": 1.0,
    "direction_accuracy": 1.0,
    "llm_adoption_rate": null,
    "node_count_generated": 9,
    "node_count_golden": 9,
    "relationship_count_generated": 12,
    "relationship_count_golden": 12
  },
  "llm_diffs": [],
  "version_id": 1,
  "stage": "fk_only"
}
```

| 시나리오 | stage | llm_diffs | version_id |
|----------|-------|-----------|------------|
| `skip_llm=true` | `fk_only` | `[]` | PG 성공 시 정수 |
| `skip_llm=false` + API 키 없음 | `fk_only` | `[]` | PG 성공 시 정수 |
| `skip_llm=false` + LLM 성공 | `fk_plus_llm` | 변경 내역 | PG 성공 시 정수 |
| `skip_llm=false` + LLM 실패 | `fk_only` | `[]` | PG 성공 시 정수 |
| PG 다운 | 위 규칙 동일 | 위 규칙 동일 | `null` |

---

## 5. 평가 엔진

### 골든 데이터

**9개 노드:** Address, Category, Supplier, Coupon, Customer, Product, Order, Payment, Review

**12개 관계:**

| # | 관계 | 방향 | derivation |
|---|------|------|------------|
| 1 | LIVES_AT | Customer → Address | fk_direct |
| 2 | BELONGS_TO | Product → Category | fk_direct |
| 3 | SUPPLIED_BY | Product → Supplier | fk_direct |
| 4 | USED_COUPON | Order → Coupon | fk_direct |
| 5 | REVIEWS | Review → Product | fk_direct |
| 6 | PLACED | Customer → Order | fk_direct |
| 7 | PAID_BY | Order → Payment | fk_direct |
| 8 | WROTE | Customer → Review | fk_direct |
| 9 | PARENT_OF | Category → Category | fk_direct |
| 10 | CONTAINS | Order → Product | fk_join_table |
| 11 | WISHLISTED | Customer → Product | fk_join_table |
| 12 | SHIPPED_TO | Order → Address | fk_join_table |

### 평가 지표 (4개)

| 지표 | 수식 | FK 베이스라인 결과 |
|------|------|------------------|
| 치명 오류율 | (골든에 있는데 생성에 없는 노드+관계) / 골든 전체 | **0.0** (0%) |
| FK 관계 커버리지 | 매칭된 관계 / 골든 관계 | **1.0** (100%) |
| 방향 정확도 | (source,target) 일치 / 매칭된 관계 | **1.0** (100%) |
| LLM 채택률 | `llm_suggested` 태그 수 / 전체 관계 | **null** (LLM 미사용) |

---

## 6. LLM 보강 (Stage 2)

### 프롬프트 구조

| 구성 요소 | 내용 |
|-----------|------|
| **System Prompt** | 역할 정의, JSON 출력 스키마, derivation 태깅 규칙 (`llm_suggested`), 기존 FK 관계 삭제 금지 |
| **Domain Hint** | 이커머스 도메인 용어, 추천 관계 패턴 (collaborative filtering, bundles, lifecycle) |
| **User Message** | 베이스라인 온톨로지 JSON + 원본 ERD JSON |

### Diff 추적

LLM이 변경한 항목은 `LLMEnrichmentDiff` 리스트로 추적:

```json
{
  "field": "relationship_type",
  "before": null,
  "after": "Customer-[FREQUENTLY_BOUGHT_WITH]->Product",
  "reason": "LLM added new relationship"
}
```

### 안전장치

- API 키 미설정 → `LLMEnrichmentError` → 베이스라인 유지
- Claude 호출 실패 → 경고 로그 + 베이스라인 유지
- JSON 파싱 실패 → 경고 로그 + 베이스라인 유지
- Pydantic 검증 실패 → 경고 로그 + 베이스라인 유지

---

## 7. PostgreSQL 저장

### 테이블 스키마

```sql
CREATE TABLE IF NOT EXISTS ontology_versions (
    id            SERIAL PRIMARY KEY,
    erd_hash      VARCHAR(64) NOT NULL,    -- SHA-256
    ontology_json JSONB NOT NULL,
    eval_json     JSONB,
    created_at    TIMESTAMP DEFAULT NOW()
);
```

### CRUD 함수

| 함수 | 설명 |
|------|------|
| `ensure_table()` | 앱 startup 시 테이블 자동 생성 (best-effort) |
| `compute_erd_hash(erd_dict)` | ERD dict → SHA-256 해시 (결정적, 재현 가능) |
| `save_version(erd_hash, ontology_json, eval_json)` | INSERT RETURNING id |
| `get_version(version_id)` | SELECT by id |

---

## 8. 테스트 결과 상세

### 온톨로지 테스트 (16개)

| # | 테스트명 | 검증 내용 | 결과 |
|---|---------|----------|------|
| 1 | `test_fk_engine_node_count` | 9 노드 | PASS |
| 2 | `test_fk_engine_relationship_count` | 12 관계 | PASS |
| 3 | `test_fk_engine_derivation_tags` | 9 fk_direct + 3 fk_join_table | PASS |
| 4 | `test_fk_engine_direction_accuracy` | 골든 대비 방향 전수 검증 | PASS |
| 5 | `test_fk_engine_node_names` | 정확한 노드 이름 set | PASS |
| 6 | `test_fk_engine_relationship_names` | 정확한 관계 이름 set | PASS |
| 7 | `test_fk_engine_join_table_properties` | CONTAINS→quantity/unit_price, SHIPPED_TO→carrier 등 | PASS |
| 8 | `test_eval_perfect_score` | FK 베이스라인 → 오류율 0%, 커버리지 100% | PASS |
| 9 | `test_eval_missing_node` | 노드 1개 누락 → 오류율 > 0 | PASS |
| 10 | `test_eval_wrong_direction` | 방향 1개 반전 → direction_accuracy < 1.0 | PASS |
| 11 | `test_erd_hash_deterministic` | 같은 ERD → 같은 해시 | PASS |
| 12 | `test_erd_hash_changes` | ERD 변경 → 다른 해시 | PASS |
| 13 | `test_api_generate_fk_only` | POST skip_llm=true → 200, 9노드, 12관계, stage=fk_only | PASS |
| 14 | `test_api_generate_empty_erd` | 빈 ERD → 200, 0노드, 0관계 | PASS |
| 15 | `test_api_generate_invalid_body` | 잘못된 JSON → 422 | PASS |
| 16 | `test_llm_skipped_no_key` | API키 없음 → stage=fk_only, llm_diffs=[] | PASS |

### 전체 테스트 실행

```
============================= 36 passed in 0.85s ==============================
```

| 테스트 파일 | 테스트 수 | 결과 |
|------------|----------|------|
| `test_ddl_parser.py` | 10 | 10 PASS |
| `test_api_ddl.py` | 3 (×2 backend) | 6 PASS |
| `test_ontology.py` | 16 (4 API ×2 backend) | 20 PASS |
| **합계** | **36** | **36 PASS** |

---

## 9. 버그 수정

### fk_rule_engine.py — 조인테이블 properties 누락

**문제:** 조인테이블(order_items, shipping, wishlists) 관계 생성 시 `rel_props`를 계산하지만 `RelationshipType` 생성자에 `properties=rel_props`를 전달하지 않아 properties가 항상 빈 리스트였음.

**영향:** CONTAINS 관계에 quantity/unit_price, SHIPPED_TO 관계에 carrier/tracking_number/status가 누락.

**수정:** `properties=rel_props` 추가 (1줄).

**검증:** test #7 (`test_fk_engine_join_table_properties`) PASS 확인, demo.py 정상 동작.

---

## 10. 의존성 추가

| 패키지 | 버전 | 용도 |
|--------|------|------|
| anthropic | ≥0.42.0 | Claude API SDK |
| pytest-asyncio | ≥0.23.0 | 비동기 테스트 지원 |

---

## 11. DoD 체크리스트

| # | 검증 항목 | 결과 |
|---|----------|------|
| 1 | `pytest tests/ -v` → 36 passed | PASS |
| 2 | `POST /api/v1/ontology/generate` (skip_llm=true) → 200, 9노드, 12관계 | PASS |
| 3 | eval_report.critical_error_rate = 0.0 | PASS |
| 4 | eval_report.fk_relationship_coverage = 1.0 | PASS |
| 5 | eval_report.direction_accuracy = 1.0 | PASS |
| 6 | stage = "fk_only" (LLM 키 없을 때) | PASS |
| 7 | `python demo.py` → All 5 steps passed | PASS |

---

## 12. 파일 구조 (Week 2 후)

```
GraphRAG/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py                    ← [MOD] +anthropic 설정
│   │   ├── exceptions.py                ← [MOD] +3 예외 + 핸들러
│   │   ├── main.py                      ← [MOD] +ontology 라우터, +startup PG
│   │   ├── models/
│   │   │   └── schemas.py               ← [MOD] +4 모델
│   │   ├── routers/
│   │   │   ├── health.py
│   │   │   ├── ddl.py
│   │   │   └── ontology.py              ← [NEW] POST /api/v1/ontology/generate
│   │   ├── ddl_parser/
│   │   │   └── parser.py
│   │   ├── ontology/
│   │   │   ├── fk_rule_engine.py        ← [FIX] properties 누락 수정
│   │   │   ├── pipeline.py              ← [NEW] 2단계 오케스트레이터
│   │   │   ├── llm_enricher.py          ← [NEW] Claude API 호출
│   │   │   └── prompts.py               ← [NEW] 프롬프트 템플릿
│   │   ├── evaluation/                  ← [NEW]
│   │   │   ├── evaluator.py             ← 골든 대비 평가
│   │   │   └── golden_ecommerce.py      ← 9노드 + 12관계
│   │   ├── db/                          ← [NEW]
│   │   │   └── pg_client.py             ← ontology_versions CRUD
│   │   ├── data_generator/
│   │   │   └── generator.py
│   │   ├── kg_builder/
│   │   │   └── loader.py
│   │   └── query/
│   │       ├── templates.py
│   │       └── executor.py
│   ├── tests/
│   │   ├── conftest.py                  ← [MOD] +ecommerce_erd 픽스처
│   │   ├── test_ddl_parser.py
│   │   ├── test_api_ddl.py
│   │   └── test_ontology.py             ← [NEW] 16개 테스트
│   ├── demo.py
│   └── demo_ecommerce.sql
├── docker-compose.yml
├── requirements.txt                     ← [MOD] +2 패키지
├── .env.example                         ← [MOD] +2 환경변수
└── .gitignore                           ← [NEW]
```

---

## 13. 코드 규모 누적

| 구분 | Demo v0 | Week 1 추가 | Week 2 추가 | 합계 |
|------|---------|------------|------------|------|
| 애플리케이션 코드 | 1,132 | 214 | 547 | 1,893 |
| 테스트 코드 | 0 | 185 | 230 | 415 |
| 인프라 설정 | 31 | 30 | 29 | 90 |
| **총합** | **1,163** | **429** | **806** | **2,398** |

---

## 14. 다음 단계 (Week 3)

| Week 3 작업 | 설명 |
|-------------|------|
| 온톨로지 리뷰 UI | React + TypeScript 프론트엔드 |
| Auto/Review 모드 | 자동 생성 결과 확인 + 수동 편집 |
| KG 시각화 | 노드/관계 그래프 렌더링 |
| CORS 연동 | localhost:3000 ↔ FastAPI 통합 |

---

*Week 2 — 온톨로지 2단계 파이프라인 + 평가 자동화 완성*
