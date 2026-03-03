# Week 5 개발 보고서 — 하이브리드 Query Router + Cypher 템플릿 라이브러리 + Q&A 채팅 UI
> 작성일: 2026-02-26 | 목적: 하이브리드 라우터(규칙+LLM) + Cypher 템플릿 13개 + 슬롯 채우기 + Q&A 채팅 UI

---

## 1. 요약

**자연어 질문을 Cypher 쿼리로 변환하는 하이브리드 라우터(규칙 Stage 1 + LLM Stage 2)**와 **13개 Cypher 템플릿 레지스트리**, **Q&A 채팅 UI**를 구현했습니다. 핵심 원칙: LLM은 "어떤 템플릿 + 어떤 슬롯 값"만 결정하고, 코드가 슬롯을 채워 **유효한 Cypher 100% 보장**합니다. 데모 질문 4/5는 규칙 라우터로 처리되어 **API 키 없이도 동작**합니다.

| 지표 | 목표 | 실제 | 상태 |
|------|------|------|------|
| 템플릿 레지스트리 13개 등록 | 13 | 13 | PASS |
| 슬롯 채우기 → 유효한 Cypher | Cypher 검증 | PASS | PASS |
| Injection 방지 (특수문자 거부) | QueryRoutingError | QueryRoutingError | PASS |
| 규칙 라우터: Q1(two_hop) 매칭 | rule | rule | PASS |
| 규칙 라우터: Q3(agg_with_rel) 매칭 | rule | rule | PASS |
| 규칙 미매칭 → LLM fallback | llm | llm | PASS |
| API 키 없음 + 규칙 미매칭 → unsupported | unsupported | unsupported | PASS |
| POST /query → 200 + answer | 200 | 200 | PASS |
| 미지원 질문 → 200 + error 필드 | 200 | 200 | PASS |
| Neo4j 실패 → 502 | 502 | 502 | PASS |
| Query 테스트 | 15/15 | 15/15 | PASS |
| 전체 백엔드 테스트 | 76+ | 95 | PASS |
| 프론트엔드 빌드 (`npm run build`) | 에러 0 | 에러 0 | PASS |

> 테스트 95건 = 기존 76건 + 신규 query 19건 (11 sync + 4 anyio × 2 backends)

---

## 2. 구현 범위

### 백엔드 신규 파일 (7개 + 테스트 1개)

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `app/query/template_registry.py` | 285 | 13개 Cypher 템플릿 레지스트리 (TemplateSpec dataclass) |
| `app/query/slot_filler.py` | 88 | 슬롯 검증 (injection 방지) + Cypher 렌더링 |
| `app/query/router_rules.py` | 112 | Stage 1 규칙 라우터 (regex 패턴 매칭) |
| `app/query/router_llm.py` | 165 | Stage 2 LLM 라우터 (Claude Haiku, non-fatal) |
| `app/query/router.py` | 37 | 하이브리드 라우터 오케스트레이터 |
| `app/query/pipeline.py` | 230 | Q&A 파이프라인 (라우팅→슬롯→실행→답변) |
| `app/routers/query.py` | 20 | POST /api/v1/query 엔드포인트 |
| `tests/test_query.py` | 258 | Query 파이프라인 테스트 15개 |
| **소계** | **1,195** | |

### 백엔드 수정 파일 (3개)

| 파일 | 변경 내용 |
|------|----------|
| `app/models/schemas.py` | `QueryRequest`, `QueryResponse` 2개 모델 추가 (+16행) |
| `app/exceptions.py` | `QueryRoutingError`(422), `CypherExecutionError`(502) + 핸들러 2개 (+27행) |
| `app/main.py` | `query` 라우터 등록, 예외 핸들러 2개 등록, 버전 0.5.0 (+6행) |
| `app/config.py` | `anthropic_router_model` 설정 추가 (+1행) |

### 프론트엔드 신규 파일 (1개)

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `src/pages/QueryPage.tsx` | 217 | Q&A 채팅 UI (데모 질문 버튼 + 채팅 + Cypher/Path 접이식) |

### 프론트엔드 수정 파일 (4개)

| 파일 | 변경 내용 |
|------|----------|
| `src/types/ontology.ts` | `QueryResponse`, `ChatMessage` TS 타입 2개 추가 (+18행) |
| `src/api/client.ts` | `sendQuery()` 함수 추가 (+9행) |
| `src/App.tsx` | `'query'` 페이지 상태 + QueryPage 렌더링 (+11행) |
| `src/pages/ReviewPage.tsx` | `onGoToQuery` prop + "Q&A" 버튼 (build succeeded 시, +11행) |

---

## 3. 아키텍처 — 하이브리드 Query Router

```
┌────────────────────────────────────────────────────────────┐
│  Frontend (localhost:3000)                                   │
│                                                              │
│  QueryPage                                                   │
│  ┌────────────────────────────────────────────────┐         │
│  │ [데모 질문 5개 버튼] 또는 직접 입력               │         │
│  │    ↓                                            │         │
│  │ POST /api/v1/query                              │         │
│  │    ↓                                            │         │
│  │ 채팅 버블: 답변 + [▶ Cypher] + [▶ Paths]        │         │
│  │ 배지: template_id | route | matched_by          │         │
│  └────────────────────────────────────────────────┘         │
└──────────────┬───────────────────────────────────────────────┘
               │  Vite 프록시 (/api → :8000)
┌──────────────▼───────────────────────────────────────────────┐
│  Backend (localhost:8000)                                      │
│                                                                │
│  POST /api/v1/query ← QueryRequest { question }               │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                  Hybrid Router                           │  │
│  │                                                         │  │
│  │  ① Rule Router (regex)                                  │  │
│  │     Q1: "X가 주문한 상품" → two_hop                      │  │
│  │     Q2: "X 카테고리 리뷰 Top N" → custom_q2             │  │
│  │     Q3: "많이 팔린 카테고리 Top N" → agg_with_rel        │  │
│  │     Q5: "쿠폰 사용/미사용 비교" → custom_q5              │  │
│  │         ↓ (매칭 시 바로 반환, LLM 미호출)                 │  │
│  │                                                         │  │
│  │  ② LLM Router (Claude Haiku) — API 키 있을 때만          │  │
│  │     system prompt: KG 스키마 + 템플릿 13개 목록           │  │
│  │     few-shot 3개 → JSON { template_id, slots, params }  │  │
│  │         ↓ (매칭 시 반환)                                  │  │
│  │                                                         │  │
│  │  ③ Unsupported → 200 + error 필드                        │  │
│  └──────────┬──────────────────────────────────────────────┘  │
│             │                                                  │
│  ┌──────────▼──────────────────────────────────────────────┐  │
│  │              Slot Filler                                 │  │
│  │  - 노드 라벨: [A-Za-z_]+ 검증                            │  │
│  │  - 관계 타입: [A-Z_]+ 검증                               │  │
│  │  - 연산자: whitelist (=, <>, >, CONTAINS 등)             │  │
│  │  → template.format(**slots)                             │  │
│  └──────────┬──────────────────────────────────────────────┘  │
│             │                                                  │
│  ┌──────────▼──────────┐                                      │
│  │  Neo4j Executor     │ ← cypher + $params                  │
│  │  → list[dict]       │                                      │
│  └──────────┬──────────┘                                      │
│             │                                                  │
│  ┌──────────▼──────────────────────────────────────────────┐  │
│  │  Answer Generator (규칙 기반, LLM 미사용)                │  │
│  │  - 템플릿별 한국어 포맷터                                 │  │
│  │  - Evidence Path 생성                                    │  │
│  │  → QueryResponse { answer, cypher, paths, ... }         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │           Template Registry (13개)                       │  │
│  │  Generic (10): one_hop_out, one_hop_in, two_hop,        │  │
│  │    three_hop, top_n, filtered, common_neighbor,         │  │
│  │    shortest_path, agg_with_rel, status_filter           │  │
│  │  Custom (3): custom_q2, custom_q4, custom_q5            │  │
│  └─────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### 핵심 설계 원칙

| # | 원칙 | 구현 |
|---|------|------|
| 1 | **코드가 Cypher 생성** | LLM은 템플릿+슬롯만 결정. 슬롯 검증 후 코드가 `.format()` → 유효한 Cypher 100% |
| 2 | **규칙 우선, LLM fallback** | 4/5 데모 질문은 regex로 처리 → API 키 없이도 데모 동작 |
| 3 | **Injection 방지** | 노드 라벨·관계 타입·연산자 whitelist 검증. 특수문자 → 422 |
| 4 | **LLM 라우터 non-fatal** | API 키 없거나 호출 실패 시 `None` 반환 → unsupported로 graceful degradation |
| 5 | **unsupported = 200 + error** | 미지원 질문도 HTTP 200 반환 (4xx 아님). 프론트엔드 에러 핸들링 단순화 |
| 6 | **기존 코드 미변경** | `templates.py`, `executor.py` 수정 없음. `demo.py` 하위 호환 유지 |
| 7 | **답변 생성은 규칙 기반** | 템플릿별 한국어 포맷터. LLM 불필요 → 비용 0, 지연 0 |

---

## 4. 템플릿 레지스트리 (13개)

### Generic 템플릿 (10개)

| # | template_id | 카테고리 | 설명 | Cypher 패턴 |
|---|------------|---------|------|------------|
| 1 | `one_hop_out` | traverse | 1홉 정방향 | `(a:X)-[:R]->(b:Y) RETURN b.prop` |
| 2 | `one_hop_in` | traverse | 1홉 역방향 | `(a:Y)-[:R]->(b:X) RETURN a.prop` |
| 3 | `two_hop` | traverse | 2홉 체인 | `(a:X)-[:R1]->(b:M)-[:R2]->(c:Y)` |
| 4 | `three_hop` | traverse | 3홉 체인 | `(a:X)-[:R1]->(b)-[:R2]->(c)-[:R3]->(d:Y)` |
| 5 | `top_n` | aggregate | Top N 집계 | `(a:X)-[:R]->(b:Y) RETURN b.prop, count() LIMIT $limit` |
| 6 | `filtered` | traverse | 조건 필터 | `(a:X {prop: $val})-[:R]->(b:Y)` |
| 7 | `common_neighbor` | traverse | 공통 이웃 | `(a:X)-[:R]->(c:M)<-[:R]-(b:X)` |
| 8 | `shortest_path` | traverse | 최단 경로 | `shortestPath((a:X)-[*..N]-(b:Y))` |
| 9 | `agg_with_rel` | aggregate | 관계 통한 집계 | `(a)-[:R1]->(b)-[:R2]->(c) RETURN c.prop, count()` |
| 10 | `status_filter` | traverse | 상태 필터 | `(a:X)-[:R]->(b:Y) WHERE a.status {op} $val` |

### Custom 템플릿 (3개)

| # | template_id | 용도 | 비고 |
|---|------------|------|------|
| 11 | `custom_q2` | Q2: 카테고리 내 리뷰 평점 Top N | 4홉 + 집계, 범용 불가 |
| 12 | `custom_q4` | Q4: 공통 구매 상품 (EXISTS) | EXISTS 서브쿼리 필요 |
| 13 | `custom_q5` | Q5: 쿠폰 사용/미사용 비교 | OPTIONAL MATCH + CASE |

### TemplateSpec 구조

```python
@dataclass
class TemplateSpec:
    template_id: str          # 고유 ID
    category: str             # traverse | aggregate
    description: str          # 설명
    cypher: str               # Cypher 템플릿 (slots={...}, params=$...)
    slots: list[str]          # 라벨/관계 슬롯 목록 (str.format용)
    params: list[str]         # Neo4j $파라미터 목록
    example_question: str     # 예시 질문 (LLM 프롬프트용)
```

---

## 5. 하이브리드 라우터 상세

### Stage 1: 규칙 라우터 (`router_rules.py`)

| 패턴 | 매칭 예시 | template_id | route |
|------|----------|------------|-------|
| `(?:고객\s*)?X(?:가\|이)\s*주문한\s*상품` | "김민수가 주문한 상품은?" | `two_hop` | cypher_traverse |
| `X 카테고리.*리뷰.*Top\s*N` | "리뷰 평점 Top 3 상품은?" | `custom_q2` | cypher_agg |
| `많이\s*팔린\s*카테고리.*Top\s*N` | "많이 팔린 카테고리 Top 3는?" | `agg_with_rel` | cypher_agg |
| `쿠폰.*사용.*미사용` | "쿠폰 사용/미사용 비교" | `custom_q5` | cypher_agg |

> Q2는 Q1보다 먼저 검사 (Q2 패턴이 Q1의 상위 집합)

### Stage 2: LLM 라우터 (`router_llm.py`)

- **모델**: `claude-haiku-4-5-20251001` (config에서 변경 가능)
- **System prompt**: KG 스키마 (9 노드, 10 관계) + 템플릿 13개 목록
- **Few-shot**: 3개 (traverse, aggregate, unsupported)
- **출력**: `{ "template_id", "route", "slots", "params" }` JSON
- **Non-fatal**: API 키 없음 / 호출 실패 / JSON 파싱 실패 → `None` 반환 (warning 로그)

### 라우팅 우선순위

```
질문 입력
    │
    ▼
① 규칙 라우터 (regex)
    ├── 매칭 ──→ (template_id, route, slots, params, "rule") ✓
    │
    ▼ (미매칭)
② API 키 있는가?
    ├── No ──→ ("", "unsupported", {}, {}, "none") ✓
    │
    ▼ (Yes)
③ LLM 라우터 (Haiku)
    ├── 매칭 ──→ (template_id, route, slots, params, "llm") ✓
    │
    ▼ (미매칭/실패)
④ Unsupported ──→ ("", "unsupported", {}, {}, "none") ✓
```

---

## 6. 슬롯 검증 (Injection 방지)

| 슬롯 종류 | 검증 규칙 | 예시 거부 |
|----------|----------|----------|
| 노드 라벨 (`start_label` 등) | `[A-Za-z_][A-Za-z0-9_]*` | `"Customer; DROP"` → 422 |
| 관계 타입 (`rel1` 등) | `[A-Z_][A-Z0-9_]*` | `"PLACED})]"` → 422 |
| 속성명 (`return_prop` 등) | `[A-Za-z_][A-Za-z0-9_]*` | `"name' OR 1=1"` → 422 |
| 연산자 (`op`) | whitelist: `=`, `<>`, `>`, `<`, `>=`, `<=`, `CONTAINS`, `STARTS WITH`, `ENDS WITH` | `"= 1 OR 1=1"` → 422 |
| 깊이 (`max_depth`) | 숫자 1~10 | `"999"` → 422 |

---

## 7. API 엔드포인트 (신규 1개)

### `POST /api/v1/query` → 200

**Request:**
```json
{ "question": "김민수가 주문한 상품은?" }
```

**Response (200 — success):**
```json
{
  "question": "김민수가 주문한 상품은?",
  "answer": "김민수 고객이 주문한 상품: 맥북프로, 에어팟프로, 갤럭시탭",
  "cypher": "MATCH (a:Customer {name: $val})\n      -[:PLACED]->(b:Order)\n      -[:CONTAINS]->(c:Product)\nRETURN DISTINCT c.name AS result",
  "paths": [
    "Customer(김민수) -> PLACED -> Order -> CONTAINS -> Product(맥북프로)",
    "Customer(김민수) -> PLACED -> Order -> CONTAINS -> Product(에어팟프로)",
    "Customer(김민수) -> PLACED -> Order -> CONTAINS -> Product(갤럭시탭)"
  ],
  "template_id": "two_hop",
  "route": "cypher_traverse",
  "matched_by": "rule",
  "error": null
}
```

**Response (200 — unsupported):**
```json
{
  "question": "반품 정책은?",
  "answer": "이 질문 유형은 아직 지원하지 않습니다.",
  "cypher": "",
  "paths": [],
  "template_id": "",
  "route": "unsupported",
  "matched_by": "none",
  "error": "No matching template found"
}
```

| 상태 코드 | 조건 |
|-----------|------|
| 200 | 질문 처리 성공 (매칭/미매칭 모두 200) |
| 422 | 빈 질문 또는 슬롯 검증 실패 |
| 502 | Neo4j 실행 실패 |

---

## 8. Q&A 파이프라인 흐름

```
run_query(question)
│
├── 1. route_question(question)
│       → (template_id, route, slots, params, matched_by)
│       → unsupported이면 즉시 반환 (error 필드 포함)
│
├── 2. fill_template(template_id, slots, params)
│       → 슬롯 검증 + Cypher 렌더링
│       → (cypher_string, neo4j_params)
│
├── 3. _execute_cypher(cypher, neo4j_params)
│       → Neo4j 드라이버 실행
│       → list[dict] (레코드 목록)
│       → 실패 시 CypherExecutionError(502)
│
├── 4. _extract_paths(records, template_id, slots, params)
│       → 템플릿별 evidence path 포맷
│       → ["Customer(김민수) -> PLACED -> Order -> ...", ...]
│
├── 5. _generate_answer(question, records, template_id, slots, params)
│       → 템플릿별 한국어 답변 포맷
│       → "김민수 고객이 주문한 상품: 맥북프로, 에어팟프로, 갤럭시탭"
│
└── 6. return QueryResponse(question, answer, cypher, paths, ...)
```

---

## 9. 프론트엔드 — Q&A 채팅 UI

### 페이지 플로우

```
UploadPage → ReviewPage → [Build KG 성공] → [Q&A 버튼] → QueryPage
                                                              │
                                                    [← Back to Review]
```

### QueryPage 구성

| 영역 | 설명 |
|------|------|
| **데모 질문 버튼 (상단)** | 5개 데모 질문을 그리드로 배치. 클릭 시 즉시 전송 |
| **채팅 메시지 (중앙)** | user(오른쪽, primary 색상) / assistant(왼쪽, muted 색상) 버블 |
| **Assistant 상세** | 배지: `template_id` + `route` + `matched_by` |
| | 접이식 **Cypher**: `▶ Cypher` 클릭 시 코드 블록 표시 |
| | 접이식 **Evidence Paths**: `▶ Evidence Paths (N)` 클릭 시 경로 목록 |
| | error 있으면 빨간색 텍스트 표시 |
| **입력 (하단)** | Textarea + Send 버튼. Enter 전송, Shift+Enter 줄바꿈 |
| **로딩** | "답변 생성 중..." pulse 애니메이션 |

### 데모 질문 5개

| # | 질문 | 라우터 | 템플릿 |
|---|------|--------|--------|
| Q1 | 고객 김민수가 주문한 상품은? | rule | two_hop |
| Q2 | 김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은? | rule | custom_q2 |
| Q3 | 가장 많이 팔린 카테고리 Top 3는? | rule | agg_with_rel |
| Q4 | 김민수와 이영희가 공통으로 구매한 상품은? | llm | custom_q4 |
| Q5 | 쿠폰 사용 주문과 미사용 주문의 평균 금액 비교 | rule | custom_q5 |

> Q4만 LLM 라우터 필요 (API 키 없으면 unsupported)

### ReviewPage 변경

- `onGoToQuery` prop 추가 (optional)
- Build KG succeeded 시 Auto/Review 모드 모두에 **"Q&A" 버튼** 표시
- 클릭 시 `App.tsx`의 `setPage('query')` 호출

### API 클라이언트 추가 (1개)

| 함수 | HTTP | 엔드포인트 |
|------|------|-----------|
| `sendQuery(question)` | POST | `/api/v1/query` |

---

## 10. 테스트 결과 상세

### Query 테스트 (15개)

| # | 테스트명 | 검증 내용 | 결과 |
|---|---------|----------|------|
| 1 | `test_registry_has_13_templates` | 레지스트리 13개 엔트리 | PASS |
| 2 | `test_render_two_hop` | 슬롯 채우기 → 유효한 Cypher (Customer, PLACED, CONTAINS 포함) | PASS |
| 3 | `test_render_agg_with_rel` | 집계 슬롯 채우기 → count(DISTINCT a), $limit 포함 | PASS |
| 4 | `test_slot_validation_rejects_injection` | 노드 라벨에 `"Customer; DROP"` → QueryRoutingError | PASS |
| 5 | `test_rules_match_top_n` | "가장 많이 팔린 카테고리 Top 3는?" → agg_with_rel, limit=3 | PASS |
| 6 | `test_rules_match_average` | "평균 금액" → AGG_KEYWORDS 매칭 | PASS |
| 7 | `test_rules_match_q1_pattern` | "고객 김민수가 주문한 상품은?" → two_hop, val="김민수" | PASS |
| 8 | `test_rules_no_match` | "오늘 날씨가 어때?" → None | PASS |
| 9 | `test_hybrid_rules_priority` | 규칙 매칭 시 LLM 미호출 (mock.assert_not_called) | PASS |
| 10 | `test_hybrid_llm_fallback` | 규칙 미매칭 + API 키 → LLM 호출 (mock 검증) | PASS |
| 11 | `test_hybrid_no_key_unsupported` | API 키 없음 + 규칙 미매칭 → unsupported | PASS |
| 12 | `test_query_api_success` | POST /query → 200, matched_by=rule, answer에 "맥북프로" 포함 | PASS |
| 13 | `test_query_api_unsupported` | 미지원 질문 → 200 + error 필드 + cypher="" | PASS |
| 14 | `test_query_api_neo4j_failure` | Neo4j 실패 mock → 502 + "Connection refused" | PASS |
| 15 | `test_pipeline_paths_included` | 응답에 paths 2개 + "Customer(김민수)" + "Product(맥북프로)" 포함 | PASS |

### 전체 테스트 실행

```
====================== 95 passed, 122 warnings in 5.81s =======================
```

| 테스트 파일 | 고유 테스트 수 | 실행 수 | 결과 |
|------------|-------------|--------|------|
| `test_ddl_parser.py` | 10 | 10 | 10 PASS |
| `test_api_ddl.py` | 3 | 6 (×2 backend) | 6 PASS |
| `test_ontology.py` | 16 | 20 (4 API ×2) | 20 PASS |
| `test_ontology_versions.py` | 10 | 20 (×2) | 20 PASS |
| `test_kg_build.py` | 10 | 20 (×2) | 20 PASS |
| `test_query.py` | 15 | 19 (11 sync + 4 API ×2) | 19 PASS |
| **합계** | **64** | **95** | **95 PASS** |

---

## 11. DoD 체크리스트

| # | 검증 항목 | 명령어 | 결과 |
|---|----------|--------|------|
| 1 | 백엔드 테스트 | `cd backend && pytest tests/ -v` | 95 passed |
| 2 | 프론트엔드 빌드 | `cd frontend && npm run build` | 에러 없이 빌드 성공 |
| 3 | 레지스트리 13개 템플릿 | `test_registry_has_13_templates` | PASS |
| 4 | 슬롯 채우기 → 유효한 Cypher | `test_render_two_hop` | PASS |
| 5 | Injection 거부 | `test_slot_validation_rejects_injection` | PASS |
| 6 | 규칙 라우터: Q1 매칭 | `test_rules_match_q1_pattern` | PASS |
| 7 | 규칙 라우터: Q3 매칭 | `test_rules_match_top_n` | PASS |
| 8 | 하이브리드: 규칙 우선 | `test_hybrid_rules_priority` | PASS |
| 9 | 하이브리드: LLM fallback | `test_hybrid_llm_fallback` | PASS |
| 10 | POST /query → 200 + answer | `test_query_api_success` | PASS |
| 11 | 미지원 질문 → 200 + error | `test_query_api_unsupported` | PASS |
| 12 | Neo4j 실패 → 502 | `test_query_api_neo4j_failure` | PASS |
| 13 | Evidence paths 포함 | `test_pipeline_paths_included` | PASS |

---

## 12. 파일 구조 (Week 5 후)

```
GraphRAG/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py                      ← [MOD] +anthropic_router_model
│   │   ├── exceptions.py                  ← [MOD] +QueryRoutingError, +CypherExecutionError
│   │   ├── main.py                        ← [MOD] +query 라우터, v0.5.0
│   │   ├── models/
│   │   │   └── schemas.py                 ← [MOD] +QueryRequest, +QueryResponse
│   │   ├── routers/
│   │   │   ├── health.py
│   │   │   ├── ddl.py
│   │   │   ├── ontology.py
│   │   │   ├── ontology_versions.py
│   │   │   ├── kg_build.py
│   │   │   └── query.py                  ← [NEW] POST /api/v1/query
│   │   ├── ddl_parser/
│   │   │   └── parser.py
│   │   ├── ontology/
│   │   │   ├── fk_rule_engine.py
│   │   │   ├── pipeline.py
│   │   │   ├── llm_enricher.py
│   │   │   └── prompts.py
│   │   ├── evaluation/
│   │   │   ├── evaluator.py
│   │   │   └── golden_ecommerce.py
│   │   ├── db/
│   │   │   ├── pg_client.py
│   │   │   ├── migrations.py
│   │   │   └── kg_build_store.py
│   │   ├── data_generator/
│   │   │   └── generator.py
│   │   ├── kg_builder/
│   │   │   ├── loader.py
│   │   │   └── service.py
│   │   └── query/
│   │       ├── templates.py                (v0 demo, 변경 없음)
│   │       ├── executor.py                 (v0 demo, 변경 없음)
│   │       ├── template_registry.py       ← [NEW] 13개 Cypher 템플릿 레지스트리
│   │       ├── slot_filler.py             ← [NEW] 슬롯 검증 + Cypher 렌더링
│   │       ├── router_rules.py            ← [NEW] Stage 1 규칙 라우터
│   │       ├── router_llm.py              ← [NEW] Stage 2 LLM 라우터
│   │       ├── router.py                  ← [NEW] 하이브리드 라우터 오케스트레이터
│   │       └── pipeline.py                ← [NEW] Q&A 파이프라인
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_ddl_parser.py              (10 tests)
│   │   ├── test_api_ddl.py                 (3 tests ×2)
│   │   ├── test_ontology.py                (16 tests, 4 API ×2)
│   │   ├── test_ontology_versions.py       (10 tests ×2)
│   │   ├── test_kg_build.py                (10 tests ×2)
│   │   └── test_query.py                 ← [NEW] 15 tests (11 sync + 4 API ×2)
│   ├── demo.py                             (변경 없음)
│   └── demo_ecommerce.sql
├── frontend/
│   ├── src/
│   │   ├── types/
│   │   │   └── ontology.ts               ← [MOD] +QueryResponse, +ChatMessage
│   │   ├── api/
│   │   │   └── client.ts                 ← [MOD] +sendQuery()
│   │   ├── pages/
│   │   │   ├── UploadPage.tsx
│   │   │   ├── ReviewPage.tsx             ← [MOD] +onGoToQuery prop, +Q&A 버튼
│   │   │   └── QueryPage.tsx             ← [NEW] Q&A 채팅 UI
│   │   ├── App.tsx                        ← [MOD] +'query' 페이지 상태
│   │   └── ...
│   └── ...
├── docker-compose.yml
├── requirements.txt
├── PLAN.md
├── DEV_REPORT_v0.md
├── DEV_REPORT_w1.md
├── DEV_REPORT_w2.md
├── DEV_REPORT_w3.md
├── DEV_REPORT_w4.md
└── DEV_REPORT_w5.md                      ← [NEW] 본 보고서
```

---

## 13. 코드 규모 누적

| 구분 | Demo v0 | Week 1 | Week 2 | Week 3 | Week 4 | Week 5 | 합계 |
|------|---------|--------|--------|--------|--------|--------|------|
| 백엔드 애플리케이션 | 1,132 | 214 | 547 | 118 | 399 | 987 | 3,397 |
| 백엔드 테스트 | 0 | 185 | 230 | 215 | 274 | 258 | 1,162 |
| 프론트엔드 코드 | 0 | 0 | 0 | 1,438 | 149 | 266 | 1,853 |
| 인프라 설정 | 31 | 30 | 29 | 0 | 0 | 0 | 90 |
| **총합** | **1,163** | **429** | **806** | **1,771** | **822** | **1,511** | **6,502** |

> Week 5 백엔드: template_registry(285) + slot_filler(88) + router_rules(112) + router_llm(165) + router(37) + pipeline(230) + query router(20) + schemas/exceptions/main/config 변경(50) = 987행
> Week 5 프론트엔드: QueryPage(217) + types(18) + client(9) + App(11) + ReviewPage(11) = 266행
> Week 5 테스트: test_query(258)

---

## 14. 다음 단계 (Week 6)

| Week 6 작업 | 설명 |
|-------------|------|
| CSV 벌크 임포트 | 대용량 데이터 CSV 업로드 + FK 무결성 검증 |
| 근거 경로 시각화 | Evidence path를 그래프 시각화로 표시 |
| LLM 답변 생성 | Neo4j 결과를 LLM으로 자연어 답변 생성 |
| 다국어 지원 | 영어/한국어 질문 양방향 지원 |

---

*Week 5 — 하이브리드 Query Router + Cypher 템플릿 라이브러리 + Q&A 채팅 UI 완성*
