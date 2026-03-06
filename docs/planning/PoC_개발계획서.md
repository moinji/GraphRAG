# B2B SaaS · ERD → Knowledge Graph → GraphRAG
## PoC 개발 계획서 v1.2
> 도메인: 이커머스 | 팀: 1인 풀스택 | LLM: Claude | 데이터: 10~15 테이블
> 작성일: 2026-02-24 | v1.1 개정: 2026-02-24 (피드백 7건 반영)
> **v1.2 개정: 2026-02-24 (마감 이슈 5건 반영 — rdb_sql 통일, KG 모델링 확정, TTV 정의, fallback 규격, Job 운영)**

---

## 1. North Star + Scope

### North Star (한 문장)
> **"고객사 DDL 파일 하나를 업로드하면, 10분 안에 Knowledge Graph가 생성되고, 자연어로 관계 추론 질문에 근거 경로와 함께 답변하는 B2B SaaS."**

### 운영 모드 분리 (v1.1 추가)

> **TTV "10분" KPI와 "60분 Human 검토"는 서로 다른 모드의 지표입니다.**

| 모드 | 용도 | 플로 | TTV 목표 |
|------|------|------|----------|
| **Auto Mode** (데모용) | DDL → KG → Q&A를 빠르게 체험 | DDL 파싱 → FK 규칙 온톨로지 자동 생성 → **자동 승인** → KG 빌드 → Q&A | **≤ 10분** |
| **Review Mode** (제품 메시지) | 고객이 온톨로지를 통제할 수 있음을 보여줌 | DDL 파싱 → FK+LLM 온톨로지 생성 → **Human 검토/수정/승인** → KG 빌드 → Q&A | 검토 시간 별도 (≤ 60분) |

**데모 전략**: Auto Mode로 10분 TTV를 시연한 뒤, 같은 화면에서 "Review Mode로 전환하면 관계를 직접 통제할 수 있다"를 보여줌 → 속도와 신뢰 두 메시지 동시 전달.

### TTV 10분 측정 정의 (v1.2 추가)

> **PoC에서 "10분 TTV"는 데모 재현 가능한 방식으로 정의합니다.**

| 구간 | 동작 | 목표 시간 | 비고 |
|------|------|----------|------|
| T0 → T1 | DDL 업로드 → ERDSchema 파싱 완료 | < 5초 | 결정적, 변동 없음 |
| T1 → T2 | FK 규칙 온톨로지 생성 + (옵션) LLM 보강 | < 30초 | FK 규칙은 즉시, LLM 보강은 추가 ~20초 |
| T2 → T3 | Auto Mode 자동 승인 | < 1초 | 버튼 클릭 또는 자동 |
| T3 → T4 | KG 빌드 (Neo4j 적재) | < 2분 | **데모에서는 샘플 데이터 미리 적재 + Job 상태 표시** |
| T4 → T5 | 첫 Q&A 질문 → 답변 | < 15초 | 템플릿 + Cypher 실행 |
| **전체** | **T0 → T5** | **< 3분 (이상적) ~ 10분 (보수적)** | |

**데모 실전 팁**: KG 빌드(T3→T4)는 가장 변동이 큰 구간. 데모에서는 "미리 적재된 KG"를 사용하되, Job 상태 UI로 "실제로 빌드가 진행됨"을 보여주는 연출 권장. TTV 10분은 KG 빌드까지 포함한 보수적 수치.

### In Scope (PoC 8주)
| 구분 | 항목 |
|------|------|
| 데이터 입력 | DDL(.sql) 파일 업로드 파싱 |
| 온톨로지 | **FK 규칙 기반 베이스라인** + LLM 보강 (명명/설명/조인테이블) → Human-in-the-loop 검토/수정 UI |
| 온톨로지 모드 | Auto Mode (자동 승인, 데모용) + Review Mode (Human 검토, 제품용) |
| KG 생성 | 승인된 온톨로지 + 샘플 CSV 데이터 → Neo4j 적재 (**비동기 Job 모델**) |
| 검색 | Query Router (**규칙 우선 + LLM fallback** 하이브리드, 4분기) → **모두 Neo4j Cypher로 실행** (PostgreSQL 원본 미사용) |
| Q&A (A안) | **Cypher 템플릿 라이브러리(10~15개) + 슬롯 채우기** — 집계(COUNT/AVG)도 Neo4j Cypher로 통일 |
| 응답 | 답변 + 근거(경로/출처) 동시 출력 |
| 데모 | 이커머스 ERD 기반 3분 데모 시나리오 |
| 통합 경로 | A안(Neo4j Cypher 직접, **P0**) + B안(GraphRAG Local only, **P1**) |

### Out of Scope (PoC에서 하지 않음)
| 구분 | 사유 |
|------|------|
| 실시간 CDC | DB 직접 연결 불필요, DDL 업로드 우선 |
| 멀티테넌트 | 단일 테넌트로 PoC 검증 |
| 엔터프라이즈 권한/감사 | MVP1에서 최소 거버넌스로 |
| 대용량 최적화 | 500 rows/테이블 기준 |
| Track B (온보딩 챗봇) | 순수 RAG는 별도 트랙 |
| DB 직접 연결 | MVP1 로드맵 |
| GraphRAG Global 상시 실행 | 비용 문제, 제한적 사용만 |

---

## 2. Architecture v0

### 2.1 시스템 다이어그램 (텍스트)

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│  ┌──────────┐  ┌───────────────┐  ┌──────────┐  ┌───────────┐  │
│  │DDL Upload│  │Ontology Review│  │  Q&A Chat │  │ Dashboard │  │
│  │  Page    │  │  Editor       │  │ Interface │  │ (결과확인)│  │
│  └────┬─────┘  └──────┬────────┘  └─────┬────┘  └─────┬─────┘  │
└───────┼───────────────┼────────────────┼──────────────┼─────────┘
        │               │                │              │
        ▼               ▼                ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (FastAPI)                         │
│                     /api/v1/*                                   │
└───────┬───────────────┬────────────────┬──────────────┬─────────┘
        │               │                │              │
        ▼               ▼                ▼              ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────┐ ┌────────────┐
│  DDL Parser  │ │  Ontology   │ │ Query Router │ │  Session   │
│  Module      │ │  Service    │ │  (4-way)     │ │  Manager   │
│              │ │             │ │              │ │            │
│ .sql → AST  │ │ ERD→Claude  │ │ NL→분류      │ │ 상태/이력  │
│ → ERD JSON  │ │ →제안→검토  │ │ →실행→응답   │ │ 관리       │
└──────┬───────┘ └──────┬──────┘ └──────┬───────┘ └────────────┘
       │                │               │
       │                ▼               │
       │         ┌─────────────┐        │
       │         │  Claude API │        │
       │         │  (Anthropic)│        │
       │         │             │        │
       │         │ - 온톨로지  │        │
       │         │   생성      │        │
       │         │ - 쿼리 분류 │        │
       │         │ - 답변 생성 │        │
       │         └─────────────┘        │
       │                                │
       ▼                                ▼
┌──────────────────────────────────────────────────────────────┐
│                     DATA LAYER                                │
│                                                              │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Neo4j    │  │PostgreSQL │  │ Redis    │  │ File Store │  │
│  │ (KG)     │  │(Metadata) │  │(Cache)   │  │ (DDL/CSV)  │  │
│  │          │  │           │  │          │  │            │  │
│  │ 노드     │  │ 온톨로지  │  │ 쿼리캐시 │  │ 업로드     │  │
│  │ 관계     │  │ 버전이력  │  │ 세션     │  │ 원본보관   │  │
│  │ 속성     │  │ 평가결과  │  │          │  │            │  │
│  └──────────┘  └───────────┘  └──────────┘  └────────────┘  │
└──────────────────────────────────────────────────────────────┘

Query Router 4분기 상세 (v1.2: 규칙+LLM 하이브리드, 전부 Neo4j):
┌─────────────┐
│ 사용자 질문 │
└──────┬──────┘
       ▼
┌──────────────────┐    YES   ┌──────────────────────────────────┐
│ Stage 1: 규칙    │────────▶│ cypher_agg 확정                   │
│ 키워드/정규식    │         │ (COUNT/SUM/AVG/Top N 매칭)        │
│ (비용 0, <1ms)   │         │ → Cypher 집계 템플릿으로 실행      │
└───────┬──────────┘         └──────────────────────────────────┘
        │ NO (규칙 미매칭)
        ▼
┌──────────────────┐    ┌─────────────────────────────────────────┐
│ Stage 2: LLM     │───▶│ 1. cypher_agg: 집계 (규칙 미감지분)     │
│ Claude Haiku     │    │ 2. rag_doc: 문서 검색 (PoC stub)        │
│ (intent + entity │    │ 3. cypher_traverse: 관계 추론 (1~3홉)   │
│  extraction)     │    │ 4. graphrag_local: 서브그래프 요약 (B안) │
└──────────────────┘    └─────────────────────────────────────────┘

** v1.2 변경: "rdb_sql" → "cypher_agg" (Neo4j 통일) **
PoC에서는 PostgreSQL에 데이터를 적재하지 않으므로,
집계 질문도 Neo4j Cypher로 실행합니다.
별도 DB 연결/동기화 불필요 → 구현·데모 모두 단순화.
```

### 2.2 컴포넌트 책임/입출력

| 컴포넌트 | 책임 | 입력 | 출력 |
|----------|------|------|------|
| **DDL Parser** | SQL DDL 파싱 → 구조화된 ERD 정보 추출 | `.sql` 파일 | `ERDSchema JSON` (테이블, 컬럼, PK, FK, 인덱스) |
| **Ontology Service** | **FK 규칙 기반 베이스라인 생성 + LLM 보강**(명명/설명/조인테이블 전략) + 버전 관리 | ERDSchema JSON + (옵션)샘플 rows | `OntologySpec JSON` (노드타입, 관계타입, 매핑룰, derivation 태그) |
| **Ontology Review UI** | Human-in-the-loop 검토/수정 인터페이스 | OntologySpec JSON | 승인된 OntologySpec (v_approved) |
| **KG Builder** | 승인된 온톨로지 기반 Neo4j 그래프 구축 **(비동기 Job 모델)** | OntologySpec + CSV 데이터 | `{build_job_id, status: queued→running→succeeded\|failed}` → Neo4j 그래프 |
| **Query Router** | **규칙 우선 + LLM fallback** 하이브리드 라우팅 | 자연어 질문 | `{route, entities, intent, confidence, matched_by: "rule"\|"llm"}` |
| **Cypher Executor (A안)** | **Cypher 템플릿 라이브러리(10~15개) + 슬롯 채우기** → 실행 | 라우팅 결과 + 추출된 엔티티 | `{answer, cypher_query, template_id, paths[]}` |
| **GraphRAG Engine (B안)** | Community 기반 local/global 검색 | 라우팅 결과 + 질문 | `{answer, communities[], sources[]}` |
| **Answer Generator** | 실행 결과 → 자연어 답변 + 근거 조합 | 실행기 결과 | `{answer, evidence, confidence}` |
| **Session Manager** | 대화 이력/상태 관리 | API 요청 | 세션 컨텍스트 |

### 2.3 기술 스택 확정

| 레이어 | 기술 | 버전(가정) | 선택 근거 |
|--------|------|-----------|----------|
| Frontend | React + TypeScript + Tailwind | 18+ / 5+ / 3+ | 빠른 UI 구축, 1인 생산성 |
| Backend | FastAPI (Python) | 0.110+ | 비동기, 타입힌트, LLM 생태계 |
| Graph DB | Neo4j Community | 5.x | Cypher 표준, APOC, 무료 |
| Metadata DB | PostgreSQL | 16+ | 온톨로지 버전/평가 결과 저장 |
| Cache | Redis | 7+ | 쿼리 캐시, 세션 (PoC에서는 선택) |
| LLM | Claude API (Anthropic) | claude-sonnet-4-5 기본 | 긴 컨텍스트, 구조화 출력 |
| Embedding | Voyage AI 또는 Claude embed | - | 벡터 검색용 (B안 사용 시) |
| 컨테이너 | Docker Compose | - | 로컬 개발 환경 통일 |

---

## 3. 데이터 모델

### 3.1 Ontology JSON 스키마

```jsonc
{
  "$schema": "ontology-spec-v1",
  "metadata": {
    "id": "uuid-v4",
    "version": "1.0.0",                    // SemVer
    "domain": "ecommerce",
    "source_ddl": "ecommerce_schema.sql",
    "created_at": "ISO8601",
    "created_by": "llm|human",
    "status": "draft|review|approved|archived",
    "parent_version": "null|uuid",          // 이전 버전 참조
    "approval": {
      "approved_by": "string|null",
      "approved_at": "ISO8601|null",
      "review_duration_minutes": "number|null"
    }
  },

  "node_types": [
    {
      "name": "Customer",                   // PascalCase
      "description": "이커머스 고객",
      "source_table": "customers",          // 원본 RDB 테이블
      "properties": [
        {
          "name": "customer_id",
          "type": "string|integer|float|boolean|datetime",
          "source_column": "id",
          "is_key": true,                   // Neo4j 노드 식별자
          "indexed": true
        },
        {
          "name": "name",
          "type": "string",
          "source_column": "customer_name",
          "is_key": false,
          "indexed": false
        }
      ],
      "constraints": ["UNIQUE(customer_id)"]
    }
  ],

  "relationship_types": [
    {
      "name": "PLACED",                     // UPPER_SNAKE_CASE
      "description": "고객이 주문을 생성함",
      "source_node": "Customer",
      "target_node": "Order",
      "direction": "OUTGOING",              // OUTGOING | INCOMING | BIDIRECTIONAL
      "cardinality": "ONE_TO_MANY",         // ONE_TO_ONE | ONE_TO_MANY | MANY_TO_MANY
      "source_fk": {
        "table": "orders",
        "column": "customer_id",
        "references_table": "customers",
        "references_column": "id"
      },
      "properties": [
        {
          "name": "placed_at",
          "type": "datetime",
          "source_column": "orders.created_at"
        }
      ],
      "confidence": 0.95,                   // LLM 제안 신뢰도 (0~1)
      "derivation": "fk_direct|fk_inferred|llm_suggested"
    }
  ],

  "mapping_rules": {
    "join_tables": [
      {
        "table": "order_items",
        "strategy": "relationship",         // "relationship" | "node"
        "creates_relationship": "CONTAINS",
        "from_node": "Order",
        "to_node": "Product",
        "properties_from_columns": ["quantity", "unit_price"]
      }
    ],
    "enum_handling": {
      "order_status": {
        "strategy": "property",             // "property" | "separate_node"
        "values": ["pending", "shipped", "delivered", "cancelled"]
      }
    },
    "ignored_tables": ["schema_migrations", "sessions"],
    "ignored_columns": ["updated_at", "deleted_at"]
  },

  "validation": {
    "total_node_types": 9,
    "total_relationship_types": 12,
    "total_properties": 45,
    "unmapped_tables": [],
    "unmapped_fks": [],
    "warnings": [
      "order_items를 관계로 매핑: quantity/unit_price를 관계 속성으로 이동"
    ]
  }
}
```

### 3.2 버전 관리 전략

```
┌─────────────────────────────────────────────────────┐
│              Ontology Version Chain                  │
│                                                     │
│  v1.0.0 (draft)                                     │
│    ↓ LLM 제안                                       │
│  v1.0.0 (review)                                    │
│    ↓ Human 수정 (관계 방향 2개 변경)                  │
│  v1.1.0 (review)                                    │
│    ↓ Human 승인                                     │
│  v1.1.0 (approved) ← KG 빌드 트리거                  │
│    ↓ 데이터 변경으로 재생성 요청                       │
│  v2.0.0 (draft)  [parent: v1.1.0]                   │
│    ↓ diff 표시 → Human 검토                          │
│  v2.0.0 (approved)                                  │
└─────────────────────────────────────────────────────┘
```

**PostgreSQL 저장 구조:**

| 테이블 | 역할 |
|--------|------|
| `ontology_versions` | id, version, status, domain, spec_json, parent_id, created_at, approved_at |
| `ontology_changes` | id, version_id, change_type, path, old_value, new_value, changed_by |
| `kg_builds` | id, ontology_version_id, neo4j_db, node_count, rel_count, build_duration, status |
| `evaluation_results` | id, kg_build_id, question_id, expected, actual, is_correct, evaluated_at |

**버전 규칙:**
- `PATCH` (1.0.x): 속성 추가/설명 변경 (KG 재빌드 불필요)
- `MINOR` (1.x.0): 관계 속성/방향 변경 (KG 증분 업데이트)
- `MAJOR` (x.0.0): 노드/관계 타입 추가/삭제 (KG 전체 재빌드)

### 3.3 PoC KG 모델링 고정 규칙 (v1.2 추가)

> **아래 2개 결정은 PoC 기간 동안 변경 금지. 템플릿·근거 경로·평가 데이터가 이 결정에 의존합니다.**

#### 결정 1: `order_items` → 관계(CONTAINS)로 매핑

```
(Order)-[CONTAINS {quantity, unit_price}]->(Product)

▪ order_items 테이블은 별도 노드로 만들지 않음
▪ quantity, unit_price는 CONTAINS 관계의 속성(property)으로 이동
▪ 근거: order_items는 순수 M:N 조인 테이블이며,
  독립적 비즈니스 의미가 없음 (조회 대상이 아니라 연결 수단)
▪ 템플릿 영향: two_hop 템플릿에서 Customer→Order→Product 경로가 깔끔해짐
▪ 평가 영향: 골든 데이터에서 "주문 상품 조회" = Customer→PLACED→Order→CONTAINS→Product
```

#### 결정 2: `payments` → 별도 노드(Payment)로 유지

```
(Order)-[PAID_BY]->(Payment)

▪ payments 테이블은 별도 노드로 유지 (관계 속성으로 축소하지 않음)
▪ 근거: payments는 method(카드/계좌/포인트), status(성공/실패/환불),
  paid_at 등 독립적 속성이 4개 이상이고, 데모 질문에서
  "결제 수단별 분석" 가능성이 있음
▪ 노드 타입: Payment (PascalCase)
▪ 관계: Order -[PAID_BY]→ Payment
▪ 템플릿 영향: one_hop_out(Order→Payment)로 조회
```

#### 결정 3: `shipping` → 관계(SHIPPED_TO)로 매핑

```
(Order)-[SHIPPED_TO {carrier, tracking_no, status}]->(Address)

▪ shipping 테이블은 Order→Address 연결 + 속성으로 매핑
▪ 근거: 배송은 조인 성격이 강하고, PoC 데모 질문에서 배송 엔티티 자체를
  독립 조회할 시나리오가 없음
```

**고정 규칙 요약 (PoC):**

| 테이블 | 매핑 전략 | 근거 |
|--------|----------|------|
| `order_items` | **관계** (CONTAINS) | 순수 M:N 조인, 독립 의미 없음 |
| `payments` | **노드** (Payment) | 독립 속성 4+개, 분석 가능성 |
| `shipping` | **관계** (SHIPPED_TO) | 조인 성격, 독립 조회 시나리오 없음 |
| `wishlists` | **관계** (WISHLISTED) | 순수 M:N 조인, 독립 의미 없음 |

**숫자 정의 (발표/평가 시 혼동 방지):**

| 지표 | 값 | 정의 |
|------|---|------|
| **FK edges (raw)** | **13** | DDL에서 추출된 FK 제약조건 수 (파서 출력) |
| **KG node types (mapped)** | **9** | 조인/규칙 적용 후 최종 Neo4j 노드 타입 수 |
| **KG relationship types (mapped)** | **12** | 조인/규칙 적용 후 최종 Neo4j 관계 타입 수 |

> 13 FK → 12 관계: wishlists 테이블의 FK 2개(customer_id, product_id)가 단일 관계(WISHLISTED)로 매핑되어 1 감소.
> 노드 9 < 테이블 12: order_items, wishlists, shipping이 관계로 매핑되어 3 감소.

**결과 노드 타입 (9개 확정):** Customer, Address, Category, Supplier, Product, Order, Payment, Review, Coupon

**결과 관계 타입 (12개 확정):**
1. Customer -[PLACED]→ Order
2. Customer -[LIVES_AT]→ Address
3. Customer -[WROTE]→ Review
4. Customer -[WISHLISTED]→ Product *(via wishlists)*
5. Order -[CONTAINS {quantity, unit_price}]→ Product *(via order_items)*
6. Order -[PAID_BY]→ Payment
7. Order -[SHIPPED_TO {carrier, tracking_no, status}]→ Address *(via shipping)*
8. Order -[USED_COUPON]→ Coupon
9. Product -[BELONGS_TO]→ Category
10. Product -[SUPPLIED_BY]→ Supplier
11. **Review -[REVIEWS]→ Product** *(v1.2.1 추가)*
12. Category -[PARENT_OF]→ Category *(self-referential)*

> **v1.2.1 — Review ↔ Product 관계 추가 근거:**
> Review는 `product_id` FK를 가지고 있으므로 FK 규칙 엔진이 `Review -[REVIEWS]→ Product`를 결정적으로 생성.
> 이 관계가 없으면 Q2("같은 카테고리에서 리뷰 평점 Top 3") 데모 질문의 근거를
> 그래프 경로(paths[])로 출력할 수 없음(속성 조인이 되어 경로가 끊김).
> 관계가 있으면:
> `Customer→PLACED→Order→CONTAINS→Product→BELONGS_TO→Category←BELONGS_TO←Product←REVIEWS←Review`
> 이 경로가 paths[]에 그대로 출력 → 근거가 완전해짐.

### 3.4 Q&A 실패/미지원 응답 규격 (v1.2 추가)

> **템플릿 커버리지 밖, 엔티티 미검출, 타임아웃 등 실패 시에도 "제품 같은" 응답을 반환합니다.**

**정상 응답 — cypher_traverse (경로 기반):**
```json
{
  "status": "success",
  "answer": "고객 김민수가 주문한 상품은 맥북 프로, 에어팟 프로, 갤럭시 탭입니다.",
  "evidence": {
    "type": "graph_path",
    "paths": [
      "Customer(김민수) → PLACED → Order(#1024) → CONTAINS → Product(맥북 프로)"
    ],
    "cypher_query": "MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product) WHERE c.name='김민수' RETURN p",
    "template_id": "two_hop"
  },
  "metadata": {
    "route": "cypher_traverse",
    "matched_by": "llm",
    "response_time_ms": 1240,
    "llm_calls": 2
  }
}
```

**정상 응답 — cypher_agg (집계 기반, v1.2.1 추가):**
```json
{
  "status": "success",
  "answer": "가장 많이 팔린 카테고리 Top 3: 1위 전자기기(142건), 2위 의류(98건), 3위 식품(76건)",
  "evidence": {
    "type": "aggregation",
    "cypher_query": "MATCH (o:Order)-[:CONTAINS]->(p:Product)-[:BELONGS_TO]->(c:Category) RETURN c.name, count(o) AS cnt ORDER BY cnt DESC LIMIT 3",
    "template_id": "agg_with_rel",
    "sample_paths": [
      "Order(#1024) → CONTAINS → Product(맥북 프로) → BELONGS_TO → Category(전자기기)",
      "Order(#1087) → CONTAINS → Product(에어팟) → BELONGS_TO → Category(전자기기)"
    ],
    "aggregation_result": [
      {"category": "전자기기", "order_count": 142},
      {"category": "의류", "order_count": 98},
      {"category": "식품", "order_count": 76}
    ]
  },
  "metadata": {
    "route": "cypher_agg",
    "matched_by": "rule",
    "response_time_ms": 890,
    "llm_calls": 1
  }
}
```

> **집계 응답 evidence 규칙**: 집계 결과(`aggregation_result`)를 항상 포함하고,
> **대표 샘플 경로 1~3개**(`sample_paths`)를 함께 출력하여 "이 숫자가 어떤 관계에서 나왔는지" 근거를 보여줌.
> 이렇게 하면 집계 질문에서도 "경로 근거"가 존재하여 DoD의 "답변 + 근거 동시 충족" 조건을 만족.

**실패 응답 (4가지 유형):**
```json
// 1. 템플릿 미매칭 (error_code: TEMPLATE_NOT_FOUND)
{
  "status": "partial",
  "answer": "이 유형의 질문은 아직 지원 준비 중입니다.",
  "error_code": "TEMPLATE_NOT_FOUND",
  "suggestion": "다음과 같이 바꿔서 질문해 보세요: '고객 X가 주문한 상품은?'",
  "supported_patterns": ["1홉 조회", "2홉 체인", "Top N 집계", "조건 필터"],
  "metadata": { "route": "cypher_traverse", "matched_by": "llm" }
}

// 2. 엔티티 미검출 (error_code: ENTITY_NOT_FOUND)
{
  "status": "partial",
  "answer": "'홍길동'이라는 고객을 찾을 수 없습니다.",
  "error_code": "ENTITY_NOT_FOUND",
  "suggestion": "고객 이름을 정확히 입력해 주세요. 예: '김민수'",
  "metadata": { "route": "cypher_traverse", "entity_searched": "홍길동" }
}

// 3. Cypher 실행 에러 (error_code: QUERY_EXECUTION_ERROR)
{
  "status": "error",
  "answer": "질문을 처리하는 중 오류가 발생했습니다. 다시 시도해 주세요.",
  "error_code": "QUERY_EXECUTION_ERROR",
  "metadata": { "route": "cypher_traverse", "template_id": "two_hop", "neo4j_error": "..." }
}

// 4. 타임아웃 (error_code: TIMEOUT)
{
  "status": "error",
  "answer": "응답 시간이 초과되었습니다. 더 구체적인 질문으로 다시 시도해 주세요.",
  "error_code": "TIMEOUT",
  "timeout_ms": 15000,
  "suggestion": "예: '고객 김민수의 최근 주문'처럼 범위를 좁혀 주세요."
}
```

**데모 중 fallback 전략:**
- 캐시에 golden answer가 있으면 → 캐시 응답 반환 (status: "success", cached: true)
- 캐시 미스 + 실패 → 위 규격 응답 반환 (데모에서 "에러도 우아하게 처리" 보여줌)

---

## 4. PoC 8주 WBS

> **전제**: 1인 풀스택, 주 40~50시간, DDL 업로드 방식, 이커머스 도메인

### Week 1: 프로젝트 부트스트랩 + DDL 파서

| 항목 | 내용 |
|------|------|
| **목표** | 프로젝트 구조 확립, DDL 파서 완성, Neo4j/PostgreSQL 로컬 환경 |
| **작업** | 1) 모노레포 구조 세팅 (backend/frontend/shared) |
| | 2) Docker Compose: Neo4j + PostgreSQL + Redis |
| | 3) FastAPI 기본 구조 (라우터, 미들웨어, 에러핸들링) |
| | 4) DDL 파서 구현 (sqlglot 또는 sqlparse 활용) |
| | 5) 이커머스 데모 DDL 작성 (12 테이블) |
| | 6) 파서 단위 테스트 (10개 케이스) |
| **산출물** | `POST /api/v1/ddl/upload` → ERDSchema JSON 반환 |
| **DoD** | 12테이블 DDL 업로드 시 모든 테이블/컬럼/FK 100% 파싱 |
| **검증 체크리스트** | |
| | [ ] Docker Compose `up` 후 Neo4j/PG 접속 확인 |
| | [ ] DDL 파일 업로드 API 정상 응답 (200) |
| | [ ] FK 관계 10개 이상 정확 추출 |
| | [ ] 파서 테스트 10/10 통과 |
| | [ ] ERDSchema JSON 스키마 검증 통과 |
| **리스크** | DDL 방언 차이 (MySQL vs PostgreSQL) → PoC는 PostgreSQL만 지원, MySQL은 MVP1 |
| **완료 기준** | 파서 테스트 전체 통과 + API 응답 확인 스크린샷 |

---

### Week 2: FK 규칙 온톨로지 + LLM 보강 + 평가 자동화

| 항목 | 내용 |
|------|------|
| **목표** | **FK 기반 규칙으로 온톨로지 베이스라인 생성** → LLM은 보강 역할로 제한 → 평가 리포트 자동화 |
| **작업** | 1) **FK 규칙 엔진 구현**: ERDSchema → 자동 온톨로지 생성 |
| |    - FK 1개 = 관계 1개 (방향: FK 보유 테이블 → 참조 테이블) |
| |    - 테이블 = 노드 타입 (PascalCase 자동 변환) |
| |    - FK가 2개인 테이블 = 조인 테이블 후보 → 관계로 변환 |
| | 2) Anthropic Claude SDK 통합 |
| | 3) **LLM 보강 범위 제한**: 명명 개선, description 생성, 조인테이블 전략 제안, enum 처리 제안 |
| | 4) derivation 태그: `fk_direct` / `fk_inferred` / `llm_suggested` |
| | 5) 온톨로지 JSON 스키마 검증 (Pydantic 모델) |
| | 6) PostgreSQL에 온톨로지 버전 저장 |
| | 7) **평가 자동 리포트 v1**: 골든 데이터 대비 치명 오류율 자동 산출 |
| **산출물** | `POST /api/v1/ontology/generate` → OntologySpec JSON + **eval_report.json** |
| **DoD** | FK 규칙 베이스라인의 치명 오류율 ≤ 5% (LLM 의존 없이) |
| **검증 체크리스트** | |
| | [ ] FK 규칙 엔진: 12테이블 → 노드 9개 + FK 직접 관계 13개 자동 생성 |
| | [ ] FK 직접 관계 13개 방향 정확도 100% (규칙 기반이므로) |
| | [ ] LLM 보강: 명명 개선 + description 추가 확인 |
| | [ ] derivation 태그 정확 분류 (fk_direct vs llm_suggested) |
| | [ ] OntologySpec JSON 스키마 검증 통과 |
| | [ ] Claude API 호출 성공 (보강 응답 < 30초) |
| | [ ] **평가 리포트 자동 생성**: 치명 오류율/관계 커버리지/방향 정확도 1장 출력 |
| | [ ] 온톨로지 버전 DB 저장 확인 |
| **리스크** | LLM 보강이 FK 규칙 결과를 오히려 훼손 → 보강 결과를 별도 레이어로 분리, 항상 diff 표시 |
| **완료 기준** | FK 규칙 온톨로지 + LLM 보강 결과 + 평가 리포트 e2e |

**온톨로지 생성 2단계 파이프라인 (v1.1 변경):**
```
Stage 1: FK 규칙 엔진 (결정적, LLM 호출 없음)
──────────────────────────────────────────────
 ERDSchema JSON
   → 각 테이블 → NodeType (PascalCase 변환)
   → 각 FK → RelationshipType (방향: FK 소유 → 참조)
   → FK 2개 테이블 → 조인 테이블 후보 탐지
   → derivation: "fk_direct" 태그
   → 결과: 베이스라인 OntologySpec (치명 오류율 ~0%)

Stage 2: LLM 보강 (Claude, 비결정적)
──────────────────────────────────────────────
 베이스라인 OntologySpec + ERDSchema + (옵션)샘플 rows
   → 관계 명명 개선 (e.g., "customers_orders" → "PLACED")
   → description 생성 (한국어/영어)
   → 조인 테이블 전략 제안 (관계 vs 노드)
   → enum 컬럼 처리 제안 (속성 vs 별도 노드)
   → derivation: "llm_suggested" 태그
   → 결과: 보강된 OntologySpec (변경점 diff 포함)
```

**프롬프트 구조 (Core/Domain 분리):**
```
[Core Template]  ← 도메인 무관, 재사용
- 시스템 역할: "FK 규칙으로 생성된 베이스라인을 보강하라"
- 출력 JSON 스키마 명시
- 노드/관계 명명 규칙
- 변경 시 반드시 derivation: "llm_suggested" 태그
- 조인 테이블 처리 전략

[Domain Template: ecommerce]  ← 도메인별 교체
- 이커머스 도메인 용어집
- 일반적 관계 패턴 예시 (PLACED, CONTAINS 등)
- 도메인 특화 힌트
```

**평가 리포트 자동화 (Week 2부터 매주 실행):**
```
┌─────────────────────────────────────────────┐
│         Eval Report (1장)  2026-W10         │
│                                             │
│  온톨로지 치명 오류율:  2/50 = 4.0% ✅ (≤10%) │
│  FK 관계 커버리지:     13/13 = 100%          │
│  LLM 보강 채택률:      8/12 = 66.7%          │
│  라우터 분류 정확도:    - (Week 5~)          │
│  Cypher 템플릿 성공률:  - (Week 5~)          │
│  평균 응답 시간:        - (Week 5~)          │
│  API 누적 비용:        $3.20                 │
│                                             │
│  변경 이력: W9 대비 오류율 -2%p 개선         │
└─────────────────────────────────────────────┘
```

---

### Week 3: 온톨로지 리뷰 UI (Human-in-the-loop) + Auto/Review 모드

| 항목 | 내용 |
|------|------|
| **목표** | 온톨로지 검토/수정 UI + Auto/Review 모드 전환, 60분 내 검토 완료 가능 |
| **작업** | 1) React 프로젝트 세팅 (Vite + TypeScript + Tailwind) |
| | 2) **테이블 뷰 기반 온톨로지 리뷰 (기본)**: 노드/관계 목록 + derivation 태그 표시 |
| | 3) 그래프 시각화 (react-force-graph) — **옵션, 시간 여유 시** |
| | 4) 노드/관계 편집 패널 (CRUD) + 관계 방향 원클릭 반전 |
| | 5) `fk_direct` vs `llm_suggested` 시각 구분 (색상/태그) |
| | 6) 변경 사항 diff 표시 |
| | 7) **Auto Mode / Review Mode 토글**: Auto 선택 시 자동 승인 → KG 빌드 트리거 |
| | 8) 승인/반려 워크플로 (Review Mode 시) |
| | 9) DDL 업로드 페이지 → 온톨로지 생성 → 모드 선택 → 리뷰/자동승인 전체 플로 |
| **산출물** | 웹 UI에서 Auto/Review 모드 선택 + 온톨로지 수정/승인 가능 |
| **DoD** | Auto Mode: 업로드~KG빌드 트리거 ≤ 2분 / Review Mode: 60분 내 검토/수정/승인 |
| **검증 체크리스트** | |
| | [ ] 테이블 뷰: 노드/관계 목록 렌더링 + derivation 태그 표시 |
| | [ ] 노드 타입 추가/삭제/수정 |
| | [ ] 관계 타입 추가/삭제/수정 (방향 포함) |
| | [ ] 관계 방향 원클릭 반전 |
| | [ ] `fk_direct`(파란) vs `llm_suggested`(주황) 시각 구분 |
| | [ ] 변경 전/후 diff 표시 |
| | [ ] **Auto Mode**: 버튼 클릭 → 자동 승인 → KG 빌드 API 호출 |
| | [ ] **Review Mode**: 승인 버튼 → status: approved 저장 |
| | [ ] 전체 플로 (업로드→생성→모드선택→승인) 완주 |
| | [ ] (옵션) 그래프 시각화 렌더링 |
| **리스크** | 1인 개발에서 UI 시간 초과 → 그래프 시각화를 과감히 Week 7로 미루고 테이블 뷰로 집중 |
| **완료 기준** | Auto Mode + Review Mode 전체 플로 스크린 레코딩 |

---

### Week 4: KG Builder (Job 모델) + FK 무결성 보장 샘플 데이터

| 항목 | 내용 |
|------|------|
| **목표** | 비동기 Job 모델로 KG 빌드 + FK 참조 무결성이 보장된 샘플 데이터 생성 |
| **작업** | 1) **샘플 데이터 생성기 (의존성 순서 보장)**: |
| |    - 생성 순서 고정 (GENERATION_ORDER 코드 참조): Layer 0: customers, categories, suppliers, coupons → Layer 1: addresses, products → Layer 2: orders → Layer 3: order_items, payments, shipping → Layer 4: reviews, wishlists |
| |    - 각 테이블 FK는 **이미 생성된 PK 풀에서만** random.choice |
| |    - FK 무결성 검증 스크립트: 모든 FK 참조가 유효한지 assert |
| |    - Faker 활용, 12테이블 × 200~500 rows |
| | 2) **KG Build Job 모델 구현**: |
| |    - `POST /api/v1/kg/build` → `{build_job_id}` 즉시 반환 (202 Accepted) |
| |    - `GET /api/v1/kg/build/{job_id}` → `{status: queued\|running\|succeeded\|failed, progress, error}` |
| |    - **PoC 운영 형태: FastAPI `BackgroundTasks`** (별도 큐/워커 불필요) |
| |    - 실패 시 자동 정리 (partial graph 삭제) + 에러 상세 기록 |
| |    - MVP1에서 Celery/Redis 큐로 전환 가능하도록 인터페이스 분리 |
| | 3) CSV → Neo4j 노드/관계 벌크 임포트 (neo4j Python driver) |
| | 4) Neo4j 인덱스/제약조건 자동 생성 |
| | 5) 적재 결과 검증 (노드/관계 카운트 매칭) |
| | 6) `kg_builds` 테이블에 빌드 결과 기록 |
| **산출물** | 비동기 `POST /api/v1/kg/build` + 상태 폴링 API + FK 무결 샘플 데이터 |
| **DoD** | 12테이블 데이터 → Neo4j 적재 완료, 노드/관계 수 일치, **FK 참조 위반 0건** |
| **검증 체크리스트** | |
| | [ ] **FK 무결성 검증 통과**: 12테이블 전체 FK 참조 유효 (assert 스크립트) |
| | [ ] 샘플 CSV 12개 파일 생성 (의존성 순서대로) |
| | [ ] Neo4j 노드: 9개 타입 (섹션 3.3 확정 목록 대조) |
| | [ ] Neo4j 관계: 12개 타입 (섹션 3.3 확정 목록 대조) |
| | [ ] 노드 총 수 ≥ 2,000 |
| | [ ] 관계 총 수 ≥ 3,000 |
| | [ ] **Job 모델**: POST 202 반환 → 폴링으로 succeeded 확인 |
| | [ ] **Job 실패 시**: failed 상태 + error 메시지 + partial graph 정리 |
| | [ ] Neo4j Browser에서 그래프 탐색 확인 |
| | [ ] 빌드 소요 시간 < 2분 (500 rows/table 기준) |
| | [ ] 빌드 결과 PostgreSQL 기록 확인 |
| **리스크** | 조인 테이블(order_items) 매핑 복잡도 → **섹션 3.3 고정 규칙으로 해결** |
| **완료 기준** | FK 무결성 assert 통과 + Job 모델 동작 스크린샷 + Neo4j 카운트 출력 |

**KG Build Job API 응답 예시 (v1.2 추가):**
```json
// POST /api/v1/kg/build  → 202 Accepted
{
  "build_job_id": "build_20260310_001",
  "status": "queued",
  "ontology_version": "1.1.0",
  "created_at": "2026-03-10T14:30:00Z"
}

// GET /api/v1/kg/build/build_20260310_001  → 성공
{
  "build_job_id": "build_20260310_001",
  "status": "succeeded",
  "progress": {"nodes_created": 2150, "relationships_created": 3420, "duration_seconds": 45},
  "ontology_version": "1.1.0",
  "started_at": "2026-03-10T14:30:01Z",
  "completed_at": "2026-03-10T14:30:46Z"
}

// GET /api/v1/kg/build/build_20260310_002  → 실패
{
  "build_job_id": "build_20260310_002",
  "status": "failed",
  "progress": {"nodes_created": 800, "relationships_created": 0, "duration_seconds": 12},
  "error": {
    "stage": "relationship_import",
    "message": "FK reference not found: order_items.product_id=9999",
    "detail": "Product node with id=9999 does not exist"
  },
  "cleanup": "partial_graph_deleted",
  "started_at": "2026-03-10T15:00:01Z",
  "failed_at": "2026-03-10T15:00:13Z"
}
```

**샘플 데이터 생성 순서 (v1.1 추가):**
```python
# data_generator.py — 의존성 DAG 순서
GENERATION_ORDER = [
    # Layer 0: FK 없는 독립 테이블
    ("customers",   300, []),
    ("categories",  20,  [("parent_id", "categories", "id", nullable=True)]),  # self-ref
    ("suppliers",   15,  []),
    ("coupons",     10,  []),

    # Layer 1: Layer 0 참조
    ("addresses",   400, [("customer_id", "customers", "id")]),
    ("products",    100, [("category_id", "categories", "id"),
                          ("supplier_id", "suppliers", "id")]),

    # Layer 2: Layer 0~1 참조
    ("orders",      500, [("customer_id", "customers", "id"),
                          ("coupon_id", "coupons", "id", nullable=True)]),

    # Layer 3: Layer 2 참조
    ("order_items", 800, [("order_id", "orders", "id"),
                          ("product_id", "products", "id")]),
    ("payments",    480, [("order_id", "orders", "id")]),
    ("shipping",    450, [("order_id", "orders", "id"),
                          ("address_id", "addresses", "id")]),

    # Layer 4: Layer 0~1 참조 (독립)
    ("reviews",     200, [("product_id", "products", "id"),
                          ("customer_id", "customers", "id")]),
    ("wishlists",   150, [("customer_id", "customers", "id"),
                          ("product_id", "products", "id")]),
]

def generate_all():
    pk_pools = {}  # {"customers": [1, 2, 3, ...], ...}
    for table, count, fks in GENERATION_ORDER:
        rows = []
        for i in range(count):
            row = generate_row(table, i, pk_pools, fks)
            rows.append(row)
        pk_pools[table] = [r["id"] for r in rows]
        save_csv(table, rows)
    validate_fk_integrity(pk_pools)  # 전체 FK 참조 assert
```

**이커머스 데모 ERD (12 테이블):**
```
customers ──1:N──▶ orders ──1:N──▶ order_items ◀──N:1── products
    │                │                                      │
    │                ▼                                      │
    │            payments                                   │
    │                                                       │
    ▼                                                       ▼
addresses ◀──N:1── shipping ──N:1──▶ orders          categories
                                                          │
                                              (self-ref: parent)

products ──1:N──▶ reviews ◀──N:1── customers
products ──N:1──▶ suppliers
orders ──N:1──▶ coupons
customers ──N:M──▶ wishlists ◀──N:M── products
```

---

### Week 5: 하이브리드 라우터 + Cypher 템플릿 라이브러리 (A안)

| 항목 | 내용 |
|------|------|
| **목표** | 규칙+LLM 하이브리드 라우터 + **Cypher 템플릿 10~15개 + 슬롯 채우기** → 답변+근거 |
| **작업** | 1) **Query Router Stage 1 (규칙)**: 키워드/정규식으로 `cypher_agg` 먼저 감지 |
| |    - 패턴: `총|합계|평균|COUNT|SUM|AVG|몇 개|몇 명` → `cypher_agg` |
| |    - 패턴: `Top N|가장 많이|순위|랭킹` → `cypher_agg` |
| | 2) **Query Router Stage 2 (LLM)**: 규칙 미매칭 → Claude Haiku 분류 + entity extraction |
| | 3) **Cypher 템플릿 라이브러리 구축** (자유 생성 아님): |
| |    - LLM은 "어떤 템플릿 + 어떤 엔티티 값"만 결정 |
| |    - 템플릿에 슬롯 채우기 → 유효한 Cypher 보장 |
| | 4) Cypher 실행 + 결과 파싱 |
| | 5) 근거 경로 추출 (MATCH path 활용) |
| | 6) Answer Generator: 결과 → 자연어 답변 + 근거 조합 |
| | 7) Q&A API 엔드포인트 + 기본 채팅 UI |
| | 8) **평가 리포트 확장**: 라우터 정확도 + 템플릿 매칭률 + 응답시간 추가 |
| **산출물** | `POST /api/v1/query` → 답변 + 근거 경로 + template_id JSON |
| **DoD** | 데모 질문 5개 중 3개 이상 정확 답변 + 근거 출력, **Cypher 실행 에러율 ≤ 5%** |
| **검증 체크리스트** | |
| | [ ] 라우터 Stage 1 (규칙): 집계 키워드 10개 → `cypher_agg` 매칭 확인 |
| | [ ] 라우터 Stage 2 (LLM): 테스트 20개 중 16개+ 정확 |
| | [ ] **Cypher 템플릿 10개+** 구현 완료 |
| | [ ] 템플릿 슬롯 채우기: 유효 Cypher 생성률 **95%+** |
| | [ ] 관계 추론 질문: 2~3홉 경로 탐색 성공 |
| | [ ] 근거 경로: 노드→관계→노드 체인 출력 |
| | [ ] 채팅 UI에서 질문→답변 표시 |
| | [ ] 평가 리포트에 라우터/템플릿 지표 추가 |
| **리스크** | 템플릿 커버리지 부족 (예상 외 질문) → "이 질문 유형은 아직 지원하지 않습니다" fallback + 로그 |
| **완료 기준** | 데모 질문 5개 실행 결과 + 근거 경로 출력 + 평가 리포트 |

**Cypher 템플릿 라이브러리 (v1.1 핵심 변경):**

| # | 패턴 | 템플릿 ID | Cypher 템플릿 | 슬롯 |
|---|------|-----------|-------------|------|
| 1 | 1홉 조회 | `one_hop_out` | `MATCH (a:{NodeA})-[r:{Rel}]->(b:{NodeB}) WHERE a.{key}=$val RETURN b` | NodeA, Rel, NodeB, key, val |
| 2 | 1홉 역조회 | `one_hop_in` | `MATCH (a:{NodeA})<-[r:{Rel}]-(b:{NodeB}) WHERE a.{key}=$val RETURN b` | NodeA, Rel, NodeB, key, val |
| 3 | 2홉 체인 | `two_hop` | `MATCH (a:{N1})-[:{R1}]->(b:{N2})-[:{R2}]->(c:{N3}) WHERE a.{key}=$val RETURN c` | N1~N3, R1~R2, key, val |
| 4 | 3홉 체인 | `three_hop` | (2홉 확장) | N1~N4, R1~R3, key, val |
| 5 | Top N 집계 | `top_n` | `MATCH (a:{Node})-[r:{Rel}]->(b) RETURN a, count(b) AS cnt ORDER BY cnt DESC LIMIT $n` | Node, Rel, n |
| 6 | 조건 필터 | `filtered` | `MATCH (a:{Node}) WHERE a.{prop} {op} $val RETURN a` | Node, prop, op, val |
| 7 | 공통 이웃 | `common_neighbor` | `MATCH (a:{N1})-[:{R}]->(c:{N2})<-[:{R}]-(b:{N1}) WHERE a.{key}=$v1 AND b.{key}=$v2 RETURN c` | N1, N2, R, v1, v2 |
| 8 | 경로 탐색 | `shortest_path` | `MATCH p=shortestPath((a:{N1})-[*..3]-(b:{N2})) WHERE a.{k1}=$v1 AND b.{k2}=$v2 RETURN p` | N1, N2, k1, k2, v1, v2 |
| 9 | 집계+조인 | `agg_with_rel` | `MATCH (a:{N1})-[:{R}]->(b:{N2}) RETURN b.{prop}, count(a), avg(a.{metric})` | N1, N2, R, prop, metric |
| 10 | 상태 필터 조회 | `status_filter` | `MATCH (a:{N1})-[:{R}]->(b:{N2}) WHERE b.status=$status RETURN a, b` | N1, N2, R, status |

**LLM 역할 (축소됨):**
```
입력: 사용자 질문 + 사용 가능한 템플릿 목록 + KG 스키마
출력: {
  "template_id": "two_hop",
  "slots": {"N1": "Customer", "R1": "PLACED", "N2": "Order", "R2": "CONTAINS", "N3": "Product", "key": "name", "val": "김민수"}
}
→ 이후 코드가 슬롯을 채워 유효한 Cypher를 100% 보장
```

**Query Router 하이브리드 분류 기준 (v1.2: rdb_sql → cypher_agg 통일):**

| Route | Stage 1 (규칙) | Stage 2 (LLM) | 실행기 | 예시 |
|-------|---------------|---------------|--------|------|
| `cypher_agg` | `총\|합계\|평균\|COUNT\|몇 개\|Top` | 집계 의도 감지 | Cypher 집계 템플릿 (Neo4j) | "총 주문 수는?", "Top 3 카테고리" |
| `rag_doc` | - | 문서/정책 참조 감지 | PoC stub (미구현) | "반품 정책은?" |
| `cypher_traverse` | - | 관계 추론 (1~3홉) 감지 | Cypher 탐색 템플릿 (Neo4j) | "고객 A가 산 상품의 카테고리는?" |
| `graphrag_local` | - | 전체 구조/요약 감지 | B안 서브그래프 요약 | "이 쇼핑몰의 전체 상품 구조는?" |

> **v1.2 핵심 변경**: `rdb_sql`이라는 라우트를 삭제하고 `cypher_agg` + `cypher_traverse`로 통일.
> PoC에서는 PostgreSQL에 데이터를 넣지 않으므로, 집계도 Neo4j Cypher로 실행.
> 이로써 "데이터 소스 = Neo4j 단일"이 되어 구현/데모/테스트가 단순해짐.

**데모 질문 → 템플릿 역방향 매핑 (v1.2 추가):**

| 데모 질문 | 라우트 | 필요 템플릿 | 슬롯 |
|-----------|--------|-----------|------|
| Q1. 김민수가 주문한 상품 목록 | cypher_traverse | `two_hop` | Customer→PLACED→Order→CONTAINS→Product |
| Q2. 같은 카테고리 리뷰 Top 3 | cypher_traverse + cypher_agg | `three_hop` + `top_n` | Product→BELONGS_TO→Category→Product→Review |
| Q3. Top 3 카테고리 + 대표 상품 | cypher_agg | `agg_with_rel` + `top_n` | Order→CONTAINS→Product→BELONGS_TO→Category |
| Q4. 취소 3회+ 고객 공통 상품 | cypher_traverse | `status_filter` + `common_neighbor` | Order(status=cancelled)→Customer, 교집합 |
| Q5. 쿠폰 사용/미사용 금액 비교 | cypher_agg | `agg_with_rel` | Order→USED_COUPON→Coupon, AVG(total_amount) |

> **부족 템플릿 확인**: Q4의 "교집합" 패턴이 `common_neighbor`로 커버되는지 검증 필요. 안 되면 Week 5에 `intersection` 템플릿 추가.

---

### Week 6: GraphRAG Local (B안, P1) + 종합 평가

| 항목 | 내용 |
|------|------|
| **목표** | B안은 **Local only**(1~3홉 서브그래프 요약)로 가볍게 + A안 위주 종합 평가 |
| **작업** | 1) **B안 Local only** 구현 (Global은 PoC에서 제외): |
| |    - 옵션 1: Microsoft GraphRAG BYOG Local search |
| |    - 옵션 2: 자체 구현 — Neo4j에서 서브그래프 추출 → Claude 요약 |
| | 2) B안 Local search: 질문 엔티티 기준 1~3홉 서브그래프 → Claude 요약 답변 |
| | 3) A안 vs B안 Local 비교 (5개 데모 질문 기준) |
| | 4) **종합 평가 실행**: 50개 QA 쌍 전체 돌리기 |
| | 5) 평가 리포트 최종본: 온톨로지 + 라우터 + 템플릿 + 답변 정확도 |
| | 6) 데모용 최종 경로 결정 (A/B 또는 하이브리드) |
| **산출물** | B안 Local 동작 확인 + A/B 비교표 + 종합 평가 리포트 |
| **DoD** | A안: 데모 질문 5개 중 4개+ 성공 / B안 Local: 3개+ 성공 |
| **검증 체크리스트** | |
| | [ ] B안 Local search 동작 확인 (서브그래프 → 요약 답변) |
| | [ ] A안 vs B안 비교표 (정확도, 응답시간, 비용, 근거 품질) |
| | [ ] **종합 평가 50개 QA 실행** → 전체 리포트 |
| | [ ] 치명 오류율 최종 확인 (≤ 10%) |
| | [ ] 데모용 최종 경로 결정 + 근거 문서화 |
| **리스크** | B안 통합 시간 초과 → A안만으로 데모 진행 (B안은 "향후 지원" 슬라이드) |
| **완료 기준** | A/B 비교표 + 종합 평가 리포트 + 데모 경로 결정 문서 |

**A안 vs B안 비교 축:**

| 비교 항목 | A안 (Cypher 직접) | B안 (GraphRAG BYOG) |
|-----------|-------------------|---------------------|
| 구현 복잡도 | 낮음 | 중간~높음 |
| 응답 시간 | 빠름 (Cypher 직접) | 느림 (LLM 요약 필요) |
| 근거 출력 | 명확 (경로 직접) | 간접 (community 기반) |
| 비용 (LLM) | 낮음 | 높음 (특히 Global) |
| 복잡한 추론 | 제한적 (패턴 필요) | 유연함 |
| 멀티도메인 확장 | 도메인별 튜닝 필요 | 도메인 무관 |

---

### Week 7: End-to-End 통합 + 데모 시나리오

| 항목 | 내용 |
|------|------|
| **목표** | 전체 파이프라인 통합, 3분 데모 시나리오 완성 |
| **작업** | 1) 전체 플로 통합 테스트 (업로드→온톨로지→검토→KG→Q&A) |
| | 2) 데모 시나리오 스크립트 작성 (3분, 타이밍 포함) |
| | 3) 데모 UI 폴리시 (로딩 상태, 에러 표시, 결과 포맷) |
| | 4) TTV 측정: DDL 업로드 → 첫 답변 10분 내 |
| | 5) 데모 질문 5개 세트 확정 + 기대 답변 작성 |
| | 6) 장애 시나리오 대비 (fallback 응답) |
| | 7) 데모 데이터 고정 (seed 데이터) |
| **산출물** | 3분 데모 스크립트 + 실행 가능한 데모 환경 |
| **DoD** | 3분 데모 3회 연속 성공 재현 |
| **검증 체크리스트** | |
| | [ ] TTV ≤ 10분: Auto Mode 기준 (섹션 1 TTV 정의 참조) |
| | [ ] Human 검토 ≤ 60분: Review Mode 기준 |
| | [ ] 데모 질문 5개 중 4개+ 성공 (답변 + 근거) |
| | [ ] 3분 데모 타이밍 맞춤 (±15초) |
| | [ ] **데모 재현성 코드 체크리스트** (v1.2): |
| | [ ]   - seed 데이터 고정 (JSON/CSV 버전 관리) |
| | [ ]   - Claude API `temperature=0` 전역 설정 |
| | [ ]   - 데모 질문 5개 golden answer 캐시 저장 |
| | [ ]   - 캐시 hit 시 cached=true 표시 |
| | [ ]   - fallback 응답: 4가지 유형 모두 UI 렌더링 확인 (섹션 3.4) |
| | [ ] 데모 3회 연속 재현 성공 (fallback 포함) |
| | [ ] 미지원 질문 1개 의도적 시연 → 우아한 fallback 확인 |
| **리스크** | LLM 응답 지연/변동 → 캐싱 + 타임아웃 15초 + golden answer fallback |
| **완료 기준** | 데모 3회 재현 영상 + fallback 시연 포함 + DoD 전체 충족 |

**3분 데모 시나리오 (v1.1: Auto/Review 모드 포함):**

```
[0:00~0:15] 인트로: "RDB를 건드리지 않고, DDL 하나로 관계 추론 Q&A"

[0:15~0:45] [Auto Mode 시연] — TTV 10분 KPI
  DDL 업로드 → FK 규칙 온톨로지 자동 생성 (5초) → Auto 승인 → KG 빌드 시작
  "DDL 하나로 10분 안에 첫 질문 답변이 가능합니다"

[0:45~1:15] [Review Mode 전환] — 통제 메시지
  같은 화면에서 "Review Mode" 토글 → 온톨로지 테이블 뷰
  fk_direct(파란) vs llm_suggested(주황) 태그 시각 확인
  관계 방향 1개 원클릭 반전 → 승인
  "자동 생성된 결과를 고객이 직접 검토/수정할 수 있습니다"

[1:15~1:30] KG 빌드 완료 (샘플 데이터 미리 적재, Job 상태 표시)

[1:30~2:40] Q&A 데모 (3개 질문, 각 ~20초)
  - Q1: "고객 김민수가 주문한 상품 목록" → 답변 + Customer→Order→Product 경로
  - Q2: "김민수가 산 상품과 같은 카테고리의 리뷰 평점 Top 3" → 2홉 추론 + 경로
  - Q3: "취소 주문 3회 이상 고객의 공통 구매 상품" → 패턴 발견 + 근거

[2:40~3:00] 정리: KPI 수치(TTV, 오류율) + "DB 직접 연결은 MVP1" 로드맵
```

---

### Week 8: 테스트 · 평가 · 문서화 · 최종 리허설

| 항목 | 내용 |
|------|------|
| **목표** | 정량 KPI 최종 측정, 버그 수정, 문서화, 최종 데모 리허설 |
| **작업** | 1) 치명 오류율 측정 (관계 방향/타입 오류 50개 기준) |
| | 2) 데모 질문 5개 최종 평가 + 근거 검증 |
| | 3) 회귀 테스트 실행 (변경 후 기존 기능 검증) |
| | 4) 성능 측정 (TTV, 응답 시간, 빌드 시간) |
| | 5) 비용 측정 (Claude API 호출당 비용 기록) |
| | 6) 최종 버그 수정 (P0만) |
| | 7) 기술 문서 (아키텍처, API 명세, 배포 가이드) |
| | 8) 데모 최종 리허설 3회 |
| **산출물** | KPI 리포트 + 데모 최종본 + 기술 문서 |
| **DoD** | 모든 PoC 성공 기준 충족 |
| **검증 체크리스트** | |
| | [ ] TTV ≤ 10분 (측정값 기록) |
| | [ ] Human 검토 ≤ 60분 (측정값 기록) |
| | [ ] 치명 오류율 ≤ 10% (측정: N/50) |
| | [ ] 데모 질문 5/5 중 4+ 성공 (각 질문별 결과 기록) |
| | [ ] 3분 데모 3회 재현 성공 |
| | [ ] 회귀 테스트 전체 통과 |
| | [ ] API 비용 리포트 (1회 데모 실행 비용) |
| | [ ] 기술 문서 완성 |
| **리스크** | 마지막 주 치명 버그 발견 → Week 7에서 데모 freeze |
| **완료 기준** | PoC DoD 전체 충족 + 데모 최종 리허설 영상 |

---

## 5. 백로그 (Top 20)

| # | 항목 | P | 난이도 | 의존성 | 비고 |
|---|------|---|--------|--------|------|
| 1 | DDL 파서 (PostgreSQL) | P0 | M | - | Week 1 핵심 |
| 2 | 이커머스 데모 DDL 작성 | P0 | S | - | Week 1 |
| 3 | **FK 규칙 온톨로지 엔진** | P0 | M | #1 | Week 2 핵심, LLM 호출 없음 |
| 4 | Claude API 통합 + **LLM 보강** (명명/설명) | P0 | M | #3 | Week 2, 역할 축소 |
| 5 | Ontology JSON 스키마 + Pydantic 모델 | P0 | M | #3 | Week 2 |
| 6 | 온톨로지 버전 관리 (PostgreSQL) | P0 | M | #5 | Week 2 |
| 7 | **평가 자동 리포트** (치명오류율/커버리지) | P0 | M | #5 | Week 2부터 매주 |
| 8 | 온톨로지 리뷰 UI (**테이블 뷰 기본**) | P0 | M | #5 | Week 3, 그래프 뷰는 옵션 |
| 9 | **Auto/Review 모드 토글** | P0 | S | #8 | Week 3 |
| 10 | 온톨로지 편집 UI (CRUD + 방향 반전) | P0 | M | #8 | Week 3 |
| 11 | **FK 무결성 보장 샘플 데이터 생성기** | P0 | M | #2 | Week 4, 의존성 순서 |
| 12 | **KG Builder Job 모델** (비동기) | P0 | L | #6, #10 | Week 4 핵심 |
| 13 | CSV 벌크 임포트 + 검증 | P0 | M | #12 | Week 4 |
| 14 | **하이브리드 Query Router** (규칙+LLM) | P0 | M | #12 | Week 5 핵심 |
| 15 | **Cypher 템플릿 라이브러리** (10~15개) | P0 | L | #14 | Week 5 핵심, 자유 생성 아님 |
| 16 | 근거 경로 추출 + 포맷팅 | P0 | M | #15 | Week 5 |
| 17 | Q&A 채팅 UI | P0 | M | #16 | Week 5 |
| 18 | **GraphRAG B안 Local only** | P1 | L | #12 | Week 6, Global 제외 |
| 19 | 데모 시나리오 스크립트 | P0 | S | #17 | Week 7 |
| 20 | E2E 통합 테스트 + 회귀 테스트 | P0 | M | #17 | Week 7~8 |

**우선순위 기준:**
- **P0**: PoC DoD 충족에 필수 (없으면 데모 불가)
- **P1**: PoC 품질 향상에 중요 (없어도 데모 가능)
- **P2**: MVP1 이후 (PoC에서 하지 않음)

---

## 6. 테스트/평가 계획

### 6.1 관계 평가 데이터셋 (50~100개) 정의 방식

**구성:**

| 카테고리 | 수량 | 예시 |
|----------|------|------|
| FK 직접 관계 | 15개 | Customer → Order (PLACED) |
| FK 역방향 검증 | 10개 | Order → Customer (방향 검증) |
| 조인 테이블 관계 | 10개 | Order → Product via order_items |
| LLM 추론 관계 | 10개 | Customer → Category (구매 패턴 기반) |
| 부정 케이스 (관계 없음) | 5개 | Customer ↛ Supplier (직접 관계 없음) |
| **합계** | **50개** | |

**평가 JSON 형식:**
```json
{
  "eval_id": "rel_001",
  "category": "fk_direct",
  "source_node": "Customer",
  "target_node": "Order",
  "expected_relationship": "PLACED",
  "expected_direction": "Customer → Order",
  "expected_cardinality": "ONE_TO_MANY",
  "is_negative": false,
  "difficulty": "easy|medium|hard"
}
```

**측정 방법:**
1. 온톨로지 생성 후 자동 비교: `generated vs expected`
2. 치명 오류 정의: 관계 방향 반대 OR 존재해야 할 관계 누락 OR 타입 완전 오류
3. 치명 오류율 = (치명 오류 수) / (전체 평가 수) × 100
4. 목표: ≤ 10% (50개 중 5개 이하)

**실행 자동화:**
```python
# evaluate_ontology.py
def evaluate(generated: OntologySpec, golden: List[EvalCase]) -> EvalReport:
    results = []
    for case in golden:
        match = find_relationship(generated, case.source, case.target)
        results.append({
            "eval_id": case.eval_id,
            "found": match is not None,
            "direction_correct": check_direction(match, case),
            "type_correct": check_type(match, case),
            "is_critical_error": is_critical(match, case)
        })
    return EvalReport(
        total=len(golden),
        critical_errors=sum(1 for r in results if r["is_critical_error"]),
        critical_error_rate=...,
        details=results
    )
```

### 6.2 데모 질문 5개 세트

| # | 질문 | 라우트 | 기대 답변 (요약) | 기대 근거 |
|---|------|--------|-----------------|----------|
| Q1 | "고객 '김민수'가 주문한 모든 상품 목록을 보여줘" | `cypher_traverse` | 상품 목록 (이름, 가격, 수량) | Customer→PLACED→Order→CONTAINS→Product 경로 |
| Q2 | "고객 '김민수'가 구매한 상품과 같은 카테고리에서 리뷰 평점이 가장 높은 상품 3개는?" | `cypher_traverse` | 상품 3개 + 평점 | Customer→Order→Product→BELONGS_TO→Category→Product→Review 경로 |
| Q3 | "가장 많이 팔린 카테고리 Top 3와 각 카테고리의 대표 상품은?" | `cypher_agg` | 카테고리 3개 + 대표 상품 | Cypher 집계(주문 수) + Category→Product 경로 |
| Q4 | "취소 주문이 3회 이상인 고객 목록과, 해당 고객들이 공통으로 구매한 상품은?" | `cypher_traverse` | 고객 목록 + 공통 상품 | Customer→Order(status=cancelled)→Product 교집합 |
| Q5 | "쿠폰 'SUMMER2026'을 사용한 주문의 평균 금액과, 미사용 주문 대비 차이는?" | `cypher_agg` | 금액 비교 수치 | Cypher 집계 결과 (Neo4j) |

**성공 기준 (각 질문별):**
- [ ] 답변이 사실적으로 정확 (샘플 데이터 기준)
- [ ] 근거(경로 또는 출처)가 함께 출력됨
- [ ] 응답 시간 ≤ 15초

**전체 성공 기준:** 5개 중 4개 이상 "답변 + 근거" 동시 충족

### 6.3 회귀 테스트 전략

| 테스트 계층 | 범위 | 도구 | 트리거 |
|-------------|------|------|--------|
| Unit Test | DDL 파서, JSON 스키마 검증, 매핑 룰 | pytest | PR/commit |
| Integration Test | API 엔드포인트 (업로드→생성→빌드) | pytest + httpx | PR/commit |
| E2E Test | 전체 플로 (DDL→Q&A) | playwright + pytest | 주 1회 |
| Eval Test | 데모 질문 5개 + 관계 평가 50개 | 커스텀 eval runner | 주 1회 |

**회귀 방지 원칙:**
1. 프롬프트 변경 시 → 반드시 eval 50개 재실행, 이전 점수 이하 금지
2. KG 스키마 변경 시 → 데모 질문 5개 재실행
3. 온톨로지 JSON 스키마 변경 시 → 모든 Pydantic 모델 테스트 재실행

---

## 7. 리스크 레지스터

| # | 리스크 | 발생확률 | 영향 | 조기 신호 | 완화책 | 플랜 B |
|---|--------|----------|------|----------|--------|--------|
| R1 | **LLM 보강이 FK 베이스라인을 훼손** — LLM이 올바른 FK 관계를 잘못 수정 | 낮(15%) ↓v1.1 | 중 | Week 2 LLM 보강 후 치명 오류율 상승 | LLM 보강을 별도 레이어로 분리, derivation 태그로 추적, diff 필수 표시 | LLM 보강 비활성화, FK 규칙 베이스라인만 사용 (명명만 수동) |
| R2 | **Cypher 템플릿 커버리지 부족** — 데모 질문이 10~15개 템플릿에 안 맞음 | 중(30%) ↓v1.1 | 중 | Week 5 데모 질문 5개 중 2개 이상 매칭 실패 | 데모 질문 기준 역방향 설계(질문→필요 템플릿 역산), 템플릿 추가 | 매칭 실패 시 "이 유형은 곧 지원 예정" fallback + 가장 유사 템플릿으로 best-effort |
| R3 | **1인 개발 일정 지연** — 특정 주차 작업량 초과 | 높(70%) | 중 | 주간 체크포인트 미달성 (2주 연속) | Week별 버퍼 4시간, 리뷰 UI=테이블 뷰 기본, B안은 P1 | 데모 스코프 축소: Q&A 질문 5→3개, B안 포기, UI 최소화 |
| R4 | **GraphRAG 라이브러리 통합 실패** — 버전 호환성, BYOG 미지원 | 중(40%) | 낮↓v1.1 | Week 6 초반 통합 시도 실패 | 자체 서브그래프 추출 + Claude 요약으로 대체 (Local only) | B안 포기, A안(Cypher 템플릿)만으로 데모 |
| R5 | **Claude API 비용 예산 초과** | 낮(20%) ↓v1.1 | 중 | Week 4까지 누적 비용 > 예산 50% | 규칙 우선 라우터로 LLM 호출 감소, 응답 캐싱, Haiku 활용 | 온톨로지 LLM 보강만 Sonnet, 나머지 전부 Haiku |
| R6 | **DDL 파싱 실패** — 비표준 DDL 문법 | 낮(20%) | 높 | Week 1 테스트에서 파싱 에러 | sqlglot + 커스텀 전처리기, PostgreSQL DDL만 지원 명시 | 수동 ERD JSON 입력 fallback UI |
| R7 | **데모 재현 불가** — LLM 비결정성으로 데모마다 다른 답변 | 낮(25%) ↓v1.1 | 높 | Week 7 리허설에서 답변 품질 불일치 | **LLM 의존 구간 3개→1.5개로 축소**(온톨로지=규칙 기본, 라우터=규칙 우선, Cypher=템플릿), temperature=0, 데이터 고정(seed) | 데모 질문별 golden answer 캐싱, LLM 실패 시 캐시 답변 표시 |
| R8 | **Neo4j 성능 이슈** — 복잡한 다단계 쿼리 타임아웃 | 낮(15%) | 중 | 3홉 이상 쿼리 >10초 | 인덱스 최적화, 쿼리 depth 제한(3홉), 템플릿이 depth 강제 | 쿼리 타임아웃 5초 + "더 단순한 질문으로 다시 시도" 안내 |
| **R9** | **샘플 CSV FK 참조 깨짐** — Faker 생성 시 없는 PK 참조 | 중(40%) ↑신규 | 높 | Week 4 KG 적재 시 누락 노드/관계 발견 | **의존성 순서 생성 + PK 풀 제한 + assert 스크립트**(v1.1 추가) | 수동 seed 데이터(소량 50 rows/table) fallback |

**v1.1 리스크 변화 요약:**
| 변경 | 이유 |
|------|------|
| R1 확률 40%→15% | FK 규칙 베이스라인으로 LLM 의존도 감소 |
| R2 확률 60%→30% | 자유 Cypher 생성 → 템플릿 + 슬롯 채우기로 전환 |
| R5 확률 30%→20% | 규칙 우선 라우터로 LLM API 호출 횟수 감소 |
| R7 확률 50%→25% | 핵심 경로의 LLM 의존 구간 3개→1.5개로 축소 |
| R9 신규 추가 | 샘플 데이터 FK 무결성 리스크 명시적 관리 |

**비용 추정 (가정 기반, 측정 필요):**

| 항목 | 가정 단가 | PoC 8주 예상 | 측정 방법 |
|------|----------|-------------|----------|
| Claude Sonnet (온톨로지 생성) | ~$3/M input tokens | $15~30 | API 대시보드 누적 |
| Claude Sonnet (Q&A 답변) | ~$3/M input tokens | $20~50 | API 대시보드 누적 |
| Claude Haiku (라우터) | ~$0.25/M input tokens | $3~8 | API 대시보드 누적 |
| Neo4j Community | 무료 | $0 | - |
| 서버 (로컬 개발) | - | $0 | 로컬 Docker |
| **합계(가정)** | | **$40~90** | **실측 후 업데이트** |

> **주의**: 위 비용은 가정값입니다. Week 2부터 API 호출당 토큰 수를 기록하여 실측합니다.

---

## 8. MVP1 확장 로드맵 (4개월, PoC 이후)

### 8.1 전체 타임라인

```
PoC (8주) ────▶ MVP1 (16주)

MVP1 Phase 1: Month 1~2          MVP1 Phase 2: Month 3~4
┌────────────────────────┐        ┌────────────────────────┐
│ DB 직접 연결            │        │ 셀프 온보딩 UI         │
│ 배치 증분 반영          │        │ 멀티도메인 2nd 도메인   │
│ 최소 거버넌스 (로그)    │        │ 최소 권한 (팀 격리)    │
│ DDL + DML 파서 확장     │        │ 대시보드 (KPI 시각화)  │
└────────────────────────┘        └────────────────────────┘
```

### 8.2 상세 항목

| 월 | 항목 | 설명 | 의존성 |
|----|------|------|--------|
| **M1** | DB 직접 연결 | PostgreSQL/MySQL connection string → 자동 DDL 추출 + 샘플 row 추출 | PoC DDL 파서 |
| **M1** | 배치 증분 반영 v1 | 스케줄(1일 1회) DDL diff → 온톨로지 변경 감지 → Human 알림 | DB 연결 |
| **M1** | 로그/감사 기초 | 모든 API 호출 로그, 온톨로지 변경 이력, KG 빌드 이력 | - |
| **M2** | DDL 파서 확장 | MySQL, SQL Server 방언 지원 | PoC 파서 |
| **M2** | 배치 증분 반영 v2 | 데이터 변경(row 추가/수정) → KG 증분 업데이트 (전체 재빌드 방지) | 증분 v1 |
| **M2** | 최소 거버넌스 | 온톨로지 변경 승인 워크플로, 변경 알림, 롤백 | 로그 |
| **M3** | 셀프 온보딩 | 가입 → DDL 업로드 → 온톨로지 검토 → KG 생성 가이드 위자드 | 전체 |
| **M3** | 멀티도메인 2nd | 보안(ISMS) 또는 HR 도메인 템플릿 추가, Core 분리 검증 | PoC 도메인 분리 |
| **M3** | Track B 통합 | 내부 온보딩 챗봇 (순수 RAG) 최소 구현 | - |
| **M4** | 팀 격리 (멀티테넌트 기초) | 테넌트별 Neo4j DB 격리, API 키 관리 | - |
| **M4** | 대시보드 | KG 통계, 질문 분석, 비용 추적, 온톨로지 커버리지 | 로그 |
| **M4** | GraphRAG Global 최적화 | Community 사전 계산, 캐싱, 비용 제어 | PoC B안 |

### 8.3 MVP1 성공 기준

| KPI | 목표 | 측정 방법 |
|-----|------|----------|
| DB 연결 → 첫 답변 TTV | ≤ 15분 | 타이머 측정 |
| 지원 DB 종류 | PostgreSQL + MySQL | 테스트 매트릭스 |
| 증분 반영 정확도 | DDL 변경 95% 감지 | 자동 테스트 |
| 셀프 온보딩 완주율 | ≥ 80% (테스터 기준) | 사용자 테스트 |
| 2nd 도메인 적용 | Core 코드 변경 0, 템플릿만 추가 | 코드 diff 검증 |

---

## 9. 이번 주 바로 시작할 10개 액션 아이템

> Week 1 시작 기준

- [ ] **모노레포 프로젝트 초기화** — `backend/` (FastAPI) + `frontend/` (React) + `shared/` (스키마) 디렉토리 생성, Git 초기화, .gitignore 설정
- [ ] **Docker Compose 작성** — Neo4j 5.x + PostgreSQL 16 (메타데이터용) 컨테이너, `docker compose up` 동작 확인
- [ ] **이커머스 데모 DDL 작성** — 12테이블 PostgreSQL DDL (`demo_ecommerce.sql`), FK 13개, **섹션 3.3 고정 규칙(order_items=관계, payments=노드, shipping=관계) 반영**
- [ ] **DDL 파서 기술 선택 + PoC** — `sqlglot` vs `sqlparse` 비교: FK 추출 정확도, 30분 타임박스
- [ ] **FastAPI 프로젝트 스켈레톤** — 라우터 구조, Pydantic 모델(ERDSchema), 에러 핸들링, CORS, `/api/v1/ddl/upload` stub
- [ ] **FK 규칙 온톨로지 엔진 설계** — ERDSchema → 노드/관계 자동 매핑 규칙 정의, **조인 테이블 탐지 조건(FK 2개 = 관계 후보)** 인터페이스 설계
- [ ] **Ontology JSON 스키마 + 실패 응답 규격** — Pydantic 모델 구현, derivation 태그, **Q&A 응답 규격 4유형(섹션 3.4)** Pydantic 모델 포함
- [ ] **데모 질문 5개 → 필요 템플릿 역산** — 섹션 6.2 기준 어떤 템플릿이 필요한지 목록화, 부족 템플릿 식별
- [ ] **샘플 데이터 생성기 설계** — 12테이블 의존성 DAG + 생성 순서 + FK PK풀 참조 전략 + **assert 스크립트 뼈대**
- [ ] **개발 환경 문서화** — README.md에 로컬 실행, 환경 변수, 의존성, **"PoC에서 모든 데이터는 Neo4j에 적재 (PG는 메타데이터만)"** 명시

---

## 부록 A: 이커머스 데모 ERD 상세

### 테이블 목록 (12개)

| # | 테이블 | 주요 컬럼 | PK | FK |
|---|--------|----------|----|----|
| 1 | `customers` | id, name, email, tier(VIP/일반), created_at | id | - |
| 2 | `addresses` | id, customer_id, city, zipcode, is_default | id | customer_id→customers |
| 3 | `categories` | id, name, parent_id | id | parent_id→categories (self) |
| 4 | `suppliers` | id, name, contact_email, country | id | - |
| 5 | `products` | id, name, price, category_id, supplier_id, stock | id | category_id→categories, supplier_id→suppliers |
| 6 | `orders` | id, customer_id, status, total_amount, coupon_id, created_at | id | customer_id→customers, coupon_id→coupons |
| 7 | `order_items` | id, order_id, product_id, quantity, unit_price | id | order_id→orders, product_id→products |
| 8 | `payments` | id, order_id, method, amount, status, paid_at | id | order_id→orders |
| 9 | `reviews` | id, product_id, customer_id, rating, comment, created_at | id | product_id→products, customer_id→customers |
| 10 | `coupons` | id, code, discount_pct, valid_from, valid_to | id | - |
| 11 | `wishlists` | id, customer_id, product_id, added_at | id | customer_id→customers, product_id→products |
| 12 | `shipping` | id, order_id, address_id, carrier, tracking_no, status | id | order_id→orders, address_id→addresses |

### 확정 KG 노드/관계 (v1.2.1 — 섹션 3.3 고정 규칙 + Review-Product 관계 반영)

**노드 타입 (9개):** Customer, Address, Category, Supplier, Product, Order, Payment, Review, Coupon

**관계 타입 (12개, 확정):**
1. Customer -[PLACED]→ Order
2. Customer -[LIVES_AT]→ Address
3. Customer -[WROTE]→ Review
4. Customer -[WISHLISTED]→ Product *(wishlists 테이블 → 관계)*
5. Order -[CONTAINS {quantity, unit_price}]→ Product *(order_items → 관계, 고정 규칙)*
6. Order -[PAID_BY]→ Payment *(payments → 노드 유지, 고정 규칙)*
7. Order -[SHIPPED_TO {carrier, tracking_no, status}]→ Address *(shipping → 관계, 고정 규칙)*
8. Order -[USED_COUPON]→ Coupon
9. Product -[BELONGS_TO]→ Category
10. Product -[SUPPLIED_BY]→ Supplier
11. **Review -[REVIEWS]→ Product** *(FK: reviews.product_id, 근거 경로용)*
12. Category -[PARENT_OF]→ Category *(self-referential)*

---

## 부록 B: Core/Domain 템플릿 분리 가이드

```
templates/
├── core/
│   ├── ontology_system_prompt.txt      # 도메인 무관 지시사항
│   ├── output_schema.json              # 출력 JSON 스키마
│   ├── naming_conventions.txt          # PascalCase 노드, UPPER_SNAKE 관계
│   └── relationship_rules.txt          # 방향/카디널리티 결정 규칙
│
├── domains/
│   ├── ecommerce/
│   │   ├── glossary.txt                # 이커머스 용어집
│   │   ├── common_patterns.txt         # 주문-고객-상품 패턴
│   │   ├── example_ontology.json       # few-shot 예시
│   │   └── eval_golden.json            # 평가 골든 데이터
│   │
│   ├── security/                       # MVP1에서 추가
│   │   ├── glossary.txt
│   │   ├── common_patterns.txt
│   │   ├── example_ontology.json
│   │   └── eval_golden.json
│   │
│   └── _template/                      # 새 도메인 추가용 템플릿
│       ├── glossary.txt.template
│       ├── common_patterns.txt.template
│       ├── example_ontology.json.template
│       └── eval_golden.json.template
```

**멀티도메인 확장 절차:**
1. `_template/` 복사 → 새 도메인 폴더 생성
2. 도메인 전문가와 glossary + common_patterns 작성 (2~4시간)
3. 기존 Core 코드 변경 없이 도메인 폴더만 추가
4. 평가 골든 데이터 50개 작성
5. 기존 eval 프레임워크로 검증

---

## 부록 C: 의사결정 로그

| 날짜 | 결정 | 근거 | 대안 | 상태 |
|------|------|------|------|------|
| 2026-02-24 | PoC 도메인: 이커머스 | ERD 관계 풍부, 데모 시나리오 직관적, 샘플 데이터 생성 용이 | 보안(ISMS): B2B 소구력 높지만 도메인 지식 비용 | 확정 |
| 2026-02-24 | LLM: Claude (Anthropic) | 긴 컨텍스트, 구조화 출력 강점, DDL+스키마 이해도 | OpenAI: Function calling 성숙 | 확정 |
| 2026-02-24 | A안 우선 구현 | 1인 팀으로 확실한 동작 우선, 근거 경로 명확 | B안 먼저: 유연하지만 통합 리스크 | 확정 |
| **2026-02-24** | **온톨로지: FK 규칙 기본 + LLM 보강** | LLM 의존도 낮춰 치명 오류율 ↓, 재현성 ↑ | LLM 메인: 유연하지만 재현성 리스크 | **확정 (v1.1)** |
| **2026-02-24** | **Text-to-Cypher: 템플릿+슬롯 채우기** | Cypher 유효성 100% 보장, 데모 재현성 ↑↑ | 자유 생성: 유연하지만 에러율 60% | **확정 (v1.1)** |
| **2026-02-24** | **Query Router: 규칙+LLM 하이브리드** | 비용↓, 지연↓, 집계 오분류↓ | LLM 단독: 단순하지만 비용/지연↑ | **확정 (v1.1)** |
| **2026-02-24** | **KG Build: 비동기 Job 모델** | UI/데모 안정성, 실패 처리 용이 | 동기 응답: 단순하지만 타임아웃 리스크 | **확정 (v1.1)** |
| **2026-02-24** | **Auto/Review 모드 분리** | TTV 10분 vs 검토 60분 충돌 해결 | 단일 모드: TTV KPI 불만족 | **확정 (v1.1)** |
| **2026-02-24** | **리뷰 UI: 테이블 뷰 기본** | 1인 개발 시간 절약, 그래프 뷰는 옵션 | 그래프 뷰 기본: 시각적이지만 구현 비용↑ | **확정 (v1.1)** |
| **2026-02-24** | **B안: Local only (Global 제외)** | 비용 제한, 1인 스코프 관리 | Global 포함: 데모 임팩트↑이지만 비용/복잡도↑ | **확정 (v1.1)** |
| **2026-02-24** | **rdb_sql → cypher_agg 통일** | PoC에서 PG에 데이터 미적재, DB 연결/동기화 제거 | PG 집계: 추가 구현 필요 | **확정 (v1.2)** |
| **2026-02-24** | **order_items=관계, payments=노드, shipping=관계** | 템플릿/근거 경로 안정성, PoC 기간 변경 금지 | order_items=노드: 복잡도↑ | **확정 (v1.2)** |
| **2026-02-24** | **KG Build: FastAPI BackgroundTasks** | PoC 최소 구현, Celery 불필요 | Celery: 안정적이지만 과도 | **확정 (v1.2)** |
| **2026-02-24** | **실패 응답 규격 4유형 고정** | 데모에서도 제품처럼 보이는 에러 처리 | 자유 형식: 일관성 없음 | **확정 (v1.2)** |
| **2026-02-24** | **TTV 측정 정의: T0→T5 구간 분리** | 데모 재현 가능한 측정, 변동 구간 명시 | 단순 타이머: 변동 원인 파악 불가 | **확정 (v1.2)** |
| TBD | 최종 데모 경로 (A/B) | Week 6 비교 결과 기반 | - | 대기 |
| TBD | DDL 파서 라이브러리 | Week 1 비교 테스트 기반 | - | 대기 |
