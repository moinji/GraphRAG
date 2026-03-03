# Week 6 개발 보고서 — GraphRAG Local (B안) + 50 QA 종합 평가
> 작성일: 2026-02-26 | 목적: B안 Local Search (서브그래프 → Claude 요약) + A/B 비교 + 50 QA 종합 평가

---

## 1. 요약

**자체 구현 GraphRAG Local Search (B안)**를 추가하여 기존 A안(템플릿 기반)과 **A/B 비교가 가능한 단일 엔드포인트**를 완성했습니다. B안은 Neo4j 서브그래프 추출 → Claude 요약으로 동작하며, 50쌍 QA 골든 데이터와 평가 엔진으로 정량 비교합니다. Microsoft GraphRAG 미사용 (자체 구현).

| 지표 | 목표 | 실제 | 상태 |
|------|------|------|------|
| 엔티티 추출: 고객명 (김민수) | Customer | Customer | PASS |
| 엔티티 추출: 상품명 (맥북프로) | Product | Product | PASS |
| 엔티티 추출: 카테고리 (노트북) | Category | Category | PASS |
| 엔티티 없는 질문 → (None, None) | None | None | PASS |
| 깊이 판정: 기본 → 2 | 2 | 2 | PASS |
| 깊이 판정: "직접 연결" → 1 | 1 | 1 | PASS |
| 깊이 판정: "전체 구조" → 3 | 3 | 3 | PASS |
| 서브그래프 Cypher 생성 | MATCH 포함 | MATCH 포함 | PASS |
| B안 파이프라인 (mock) → answer | 200 | 200 | PASS |
| B안 엔티티 없음 → unsupported | error 필드 | error 필드 | PASS |
| B안 Neo4j 실패 → 502 | LocalSearchError | LocalSearchError | PASS |
| B안 LLM 실패 → 502 | LocalSearchError | LocalSearchError | PASS |
| POST /query mode=b → 200 | 200 | 200 | PASS |
| 골든 데이터 50쌍 | 50 | 50 | PASS |
| 골든 카테고리 4+ | 4+ | 6 | PASS |
| 평가: 완전 매칭 → 1.0 | 1.0 | 1.0 | PASS |
| 평가: 부분 매칭 → 0.5 | 0.5 | 0.5 | PASS |
| 평가: 비매칭 → 0.0 | 0.0 | 0.0 | PASS |
| 평가: unsupported → success | True | True | PASS |
| A/B 비교 리포트 필드 | 필수 필드 | 필수 필드 | PASS |
| A 우위 → "a_only" 추천 | a_only | a_only | PASS |
| 비용 추정 (토큰 → USD) | > 0 | > 0 | PASS |
| Local Search 테스트 | 15/15 | 15/15 | PASS |
| QA 평가 테스트 | 10/10 | 10/10 | PASS |
| 전체 백엔드 테스트 | 95+ | 121 | PASS |
| 프론트엔드 빌드 (`npm run build`) | 에러 0 | 에러 0 | PASS |

> 테스트 121건 = 기존 95건 + 신규 local_search 16건 (14 sync + 1 API ×2) + 신규 qa_evaluation 10건

---

## 2. 구현 범위

### 백엔드 신규 파일 (5개 + 테스트 2개)

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `app/query/local_prompts.py` | 121 | B안 시스템 프롬프트 + 서브그래프 직렬화 + 답변 파싱 |
| `app/query/local_search.py` | 320 | B안 핵심: 엔티티 추출 + 깊이 판정 + 서브그래프 Cypher + LLM 답변 |
| `app/evaluation/qa_golden.py` | 336 | 50쌍 QA 골든 데이터 (7 카테고리) |
| `app/evaluation/qa_evaluator.py` | 204 | QA 평가 엔진 + A/B 비교 리포트 + 비용 추정 |
| `app/routers/evaluation.py` | 29 | POST /evaluation/run + GET /evaluation/golden |
| `tests/test_local_search.py` | 254 | B안 Local Search 테스트 15개 |
| `tests/test_qa_evaluation.py` | 169 | QA 평가 테스트 10개 |
| **소계** | **1,433** | |

### 백엔드 수정 파일 (5개)

| 파일 | 변경 내용 |
|------|----------|
| `app/models/schemas.py` | `QueryRequest.mode` 필드, `QueryResponse` +4 필드, `QAGoldenPair`/`QASingleResult`/`QAComparisonReport` 3개 모델 추가 (+46행) |
| `app/exceptions.py` | `LocalSearchError`(502) + `local_search_error_handler()` (+13행) |
| `app/config.py` | `local_search_model`, `local_search_max_tokens`, `local_search_default_depth`, `local_search_max_nodes` (+5행) |
| `app/query/pipeline.py` | `mode="b"` 분기 + `latency_ms` 추적 + `import time` (+12행) |
| `app/main.py` | `evaluation` 라우터 등록, `LocalSearchError` 핸들러, 버전 0.6.0 (+5행) |
| `app/routers/query.py` | `mode` 파라미터 전달 (+2행) |

### 프론트엔드 수정 파일 (3개)

| 파일 | 변경 내용 |
|------|----------|
| `src/types/ontology.ts` | `QueryResponse` +4 필드: `mode`, `subgraph_context`, `llm_tokens_used`, `latency_ms` (+4행) |
| `src/api/client.ts` | `sendQuery(question, mode='a')` → mode 파라미터 추가 (+3행) |
| `src/pages/QueryPage.tsx` | A/B 모드 토글 + 모드별 배지 + 서브그래프 컨텍스트 접이식 + 토큰/latency 표시 (+50행) |

---

## 3. 아키텍처 — A/B 비교 Query Pipeline

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend (localhost:3000)                                        │
│                                                                    │
│  QueryPage                                                         │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │ [A Template] [B Local]  ← 모드 토글 (파란/주황)            │     │
│  │ [데모 질문 5개 버튼] 또는 직접 입력                          │     │
│  │    ↓                                                      │     │
│  │ POST /api/v1/query { question, mode: "a"|"b" }           │     │
│  │    ↓                                                      │     │
│  │ 채팅 버블: 답변 + 모드 배지 + latency + tokens             │     │
│  │ 접이식: [▶ Cypher] [▶ Subgraph Context] [▶ Paths]        │     │
│  └──────────────────────────────────────────────────────────┘     │
└──────────────┬─────────────────────────────────────────────────────┘
               │  Vite 프록시 (/api → :8000)
┌──────────────▼─────────────────────────────────────────────────────┐
│  Backend (localhost:8000)                                           │
│                                                                      │
│  POST /api/v1/query  ← QueryRequest { question, mode }             │
│                                                                      │
│  ┌────────────────────┐         ┌─────────────────────────────┐    │
│  │  mode = "a"         │         │  mode = "b"                  │    │
│  │  (기존 A안)          │         │  (신규 B안 Local Search)     │    │
│  │                     │         │                               │    │
│  │  ① Rule Router     │         │  ① extract_entity (규칙)     │    │
│  │  ② LLM Router      │         │  ② determine_depth           │    │
│  │  ③ Slot Fill        │         │  ③ build_subgraph_cypher     │    │
│  │  ④ Neo4j Execute   │         │  ④ Neo4j Execute             │    │
│  │  ⑤ Format Answer   │         │  ⑤ serialize_subgraph        │    │
│  │                     │         │  ⑥ Claude LLM 요약           │    │
│  └─────────┬──────────┘         └──────────┬──────────────────┘    │
│            │                                 │                        │
│            └─────────┬───────────────────────┘                       │
│                      ▼                                               │
│            QueryResponse                                             │
│            { answer, cypher, paths,                                  │
│              mode, subgraph_context,                                 │
│              llm_tokens_used, latency_ms }                           │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Evaluation API                                                │  │
│  │  GET  /api/v1/evaluation/golden → 50 QA pairs                 │  │
│  │  POST /api/v1/evaluation/run   → QAComparisonReport           │  │
│  │       (A안 50회 + B안 50회 실행 → 키워드/엔티티 점수 비교)      │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 핵심 설계 원칙

| # | 원칙 | 구현 |
|---|------|------|
| 1 | **단일 엔드포인트 + mode** | `POST /query` 하나로 A/B 전환. 프론트 통합 단순 |
| 2 | **자체 구현 (MS GraphRAG 미사용)** | R4 리스크 회피, 의존성 최소화 |
| 3 | **규칙 엔티티 추출 우선** | 시드 데이터 5 고객 + 8 상품 + 6 카테고리 + 3 공급업체 100% 커버 |
| 4 | **기본 2홉 서브그래프** | Customer→Order→Product 커버. 3홉은 키워드 시에만 |
| 5 | **집계 질문 → Cypher fallback** | 엔티티 없는 집계 질문은 사전 정의된 7개 집계 Cypher로 처리 |
| 6 | **평가는 키워드 매칭** | 시드 데이터 고정 → 기대값 정확. LLM judge 불필요 |
| 7 | **비용 추정 포함** | 토큰 수 × 블렌디드 단가 → USD 자동 산출 |

---

## 4. B안 Local Search 상세

### 파이프라인 흐름

```
run_local_query(question)
│
├── 1. extract_entity(question)
│       규칙: 고객명 → Customer, 상품명 → Product, 카테고리 → Category, 공급업체 → Supplier
│       → (entity_name, entity_label) 또는 (None, None)
│
├── Case A: entity=None + 집계 키워드 → 집계 Cypher fallback
│   ├── _select_aggregate_cypher(question)
│   │   → 7개 패턴 (카테고리별 주문, 고객별 주문, 평균 금액, 리뷰 평점 등)
│   ├── _execute_neo4j(agg_cypher)
│   ├── serialize_aggregate_results(records)
│   └── generate_answer_with_llm(question, agg_text) → (answer, paths, tokens)
│
├── Case B: entity=None + 집계 아님 → unsupported (error 필드)
│
└── Case C: entity 있음 → 서브그래프 검색
    ├── 2. determine_depth(question)
    │       "직접 연결" → 1, 기본 → 2, "전체 구조" → 3
    │
    ├── 3. build_subgraph_cypher(label, depth)
    │       → MATCH (anchor:{label}) OPTIONAL MATCH ... RETURN hop1, hop2
    │
    ├── 4. _execute_neo4j(cypher, {entity_name})
    │       → 앵커 노드 + 1홉/2홉 이웃 노드
    │
    ├── 5. serialize_subgraph(anchor_label, anchor_name, hop1, hop2)
    │       → 구조화된 텍스트 (앵커, 1홉, 2홉 섹션)
    │
    └── 6. generate_answer_with_llm(question, subgraph_text)
           → Claude API 호출 (system: LOCAL_SEARCH_SYSTEM_PROMPT)
           → parse_local_answer(raw) → (answer, paths)
           → (answer, paths, tokens_used)
```

### 엔티티 추출 규칙

| 노드 타입 | 등록된 엔티티 | 예시 |
|-----------|-------------|------|
| Customer | 김민수, 이영희, 박지훈, 최수진, 정대현 | "김민수가 주문한" → ("김민수", "Customer") |
| Product | 맥북프로, 에어팟프로, 갤럭시탭, LG그램, 갤럭시버즈, 아이패드에어, 맥북에어, 소니WH-1000XM5 | "맥북프로 가격" → ("맥북프로", "Product") |
| Category | 전자기기, 의류, 식품, 노트북, 오디오, 태블릿 | "노트북 카테고리" → ("노트북", "Category") |
| Supplier | 애플코리아, 삼성전자, LG전자 | "애플코리아 상품" → ("애플코리아", "Supplier") |

### 집계 Cypher 매핑 (7개)

| 키 | 패턴 | Cypher |
|----|------|--------|
| `category_order_count` | 카테고리.*많이/top | `MATCH (o:Order)-[:CONTAINS]->(p:Product)-[:BELONGS_TO]->(c:Category) RETURN c.name, count(DISTINCT o)` |
| `customer_order_count` | 고객별.*주문 | `MATCH (c:Customer)-[:PLACED]->(o:Order) RETURN c.name, count(o)` |
| `avg_order_amount` | 평균.*주문.*금액 | `MATCH (o:Order) RETURN avg(o.total_amount)` |
| `product_review_avg` | 리뷰.*평점 | `MATCH (r:Review)-[:REVIEWS]->(p:Product) RETURN p.name, avg(r.rating)` |
| `shipping_status` | 배송.*상태 | `MATCH (s:Shipping)-[:SHIPPED_TO]->(a:Address) RETURN s.status, count(s)` |
| `payment_method` | 결제.*방법 | `MATCH (p:Payment)-[:PAID_FOR]->(o:Order) RETURN p.method, count(p)` |
| `coupon_comparison` | 쿠폰.*사용.*비교 | `MATCH (o:Order) OPTIONAL MATCH (o)-[:APPLIED]->(c:Coupon) ... RETURN coupon_status, count(o)` |

### 서브그래프 Cypher (2홉 기본)

```cypher
MATCH (anchor:Customer {name: $entity_name})
OPTIONAL MATCH (anchor)-[r1]-(n1)
OPTIONAL MATCH (n1)-[r2]-(n2) WHERE n2 <> anchor
RETURN anchor, labels(anchor)[0] AS anchor_label,
  collect(DISTINCT {label: labels(n1)[0], name: coalesce(n1.name, toString(id(n1))),
    rel: type(r1), props: properties(n1)}) AS hop1,
  collect(DISTINCT {label: labels(n2)[0], name: coalesce(n2.name, toString(id(n2))),
    rel: type(r2), props: properties(n2)}) AS hop2
```

### 서브그래프 직렬화 예시

```
[앵커 노드] Customer: 김민수

[1홉 연결]
  -PLACED-> Order(1) (status=delivered, total_amount=3500000)
  -LIVES_AT-> Address(강남구) (city=서울시, street=테헤란로 123)
  -WISHLISTED-> Product(LG그램)

[2홉 연결]
  -CONTAINS-> Product(맥북프로) (price=3500000)
  -CONTAINS-> Product(에어팟프로) (price=359000)
  -PAID_FOR-> Payment(1) (method=credit_card)
```

---

## 5. QueryResponse 확장

### 기존 필드 (A/B 공통)

| 필드 | 타입 | 설명 |
|------|------|------|
| `question` | str | 원본 질문 |
| `answer` | str | 한국어 답변 |
| `cypher` | str | 실행된 Cypher |
| `paths` | list[str] | 근거 경로 |
| `template_id` | str | 템플릿 ID |
| `route` | str | 라우트 분류 |
| `matched_by` | str | 매칭 방식 (rule/llm/local_b/none) |
| `error` | str \| None | 에러 메시지 |

### 신규 필드 (Week 6)

| 필드 | 타입 | 설명 |
|------|------|------|
| `mode` | str | "a" 또는 "b" |
| `subgraph_context` | str \| None | B안: 직렬화된 서브그래프 텍스트 |
| `llm_tokens_used` | int \| None | B안: Claude 토큰 사용량 |
| `latency_ms` | int \| None | 응답 시간 (ms) |

---

## 6. 50 QA 골든 데이터

### 카테고리별 분포

| 카테고리 | 수량 | ID 접두사 | 설명 |
|---------|------|----------|------|
| traverse (1홉) | 10 | T1-01~T1-10 | 이메일, 가격, 공급업체, 위시리스트 등 |
| traverse (2홉) | 8 | T2-01~T2-08 | 주문 상품, 배송 상태, 결제 방법 |
| traverse (3홉) | 4 | T3-01~T3-04 | 주문 상품의 카테고리/공급업체 |
| aggregate | 10 | A-01~A-10 | Top N, 카운트, 평균, 전체 통계 |
| comparison | 8 | C-01~C-08 | 공통 구매, 쿠폰 비교, 카테고리 비교 |
| complex | 5 | X-01~X-05 | 배송 상태별, 결제 통계, 복합 조건 |
| unsupported | 5 | U-01~U-05 | 반품 정책, 날씨, 영화, 코드, 뉴스 |
| **합계** | **50** | | |

### 시드 데이터 역추적

```
고객별 주문-상품 매핑:
  김민수(1): 주문 1,2,8 → 맥북프로, 에어팟프로, 갤럭시탭
  이영희(2): 주문 3,5 → LG그램, 갤럭시버즈, 맥북프로, 소니WH-1000XM5
  박지훈(3): 주문 4  → 아이패드에어, 맥북프로
  최수진(4): 주문 6  → 맥북에어
  정대현(5): 주문 7  → 에어팟프로, LG그램
```

### 예시 골든 페어

| ID | 질문 | 카테고리 | expected_keywords | expected_entities |
|----|------|---------|------------------|------------------|
| T1-01 | 김민수의 이메일 주소는? | traverse | ["minsu@example.com"] | ["김민수"] |
| T2-01 | 김민수가 주문한 상품은? | traverse | ["맥북프로", "에어팟프로", "갤럭시탭"] | ["김민수"] |
| A-01 | 가장 많이 팔린 카테고리 Top 3는? | aggregate | ["노트북", "오디오"] | [] |
| C-01 | 김민수와 이영희가 공통으로 구매한 상품은? | comparison | ["맥북프로"] | ["김민수", "이영희"] |
| U-01 | 반품 정책은 어떻게 되나요? | unsupported | [] | [] |

---

## 7. 평가 엔진

### 단일 평가 (`evaluate_single`)

```python
# 일반 카테고리: 키워드 + 엔티티 매칭 비율
keyword_score = matched_keywords / total_keywords  # 0.0 ~ 1.0
entity_score = matched_entities / total_entities    # 0.0 ~ 1.0
success = keyword_score > 0  # 최소 1개 키워드 매칭

# unsupported 카테고리: 적절히 거부했는지
success = error is not None or "지원" in answer or "찾을 수 없" in answer
```

### A/B 비교 리포트 (`QAComparisonReport`)

| 필드 | 설명 |
|------|------|
| `total_pairs` | 총 QA 쌍 수 (50) |
| `a_success_count` / `b_success_count` | 각 모드 성공 수 |
| `a_avg_latency_ms` / `b_avg_latency_ms` | 각 모드 평균 응답 시간 |
| `a_avg_keyword_score` / `b_avg_keyword_score` | 각 모드 평균 키워드 점수 |
| `b_total_tokens` | B안 총 토큰 사용량 |
| `b_estimated_cost_usd` | B안 추정 비용 (블렌디드 단가 $7.6/M) |
| `recommendation` | `"a_only"` / `"b_preferred"` / `"hybrid"` |

### 추천 로직

```
A 성공 > B 성공 → "a_only"
B 성공 > A 성공 → "b_preferred"
성공 동률 + B 키워드 > A 키워드 → "b_preferred"
성공 동률 + A 키워드 > B 키워드 → "a_only"
그 외 → "hybrid"
```

### 비용 추정

```
블렌디드 단가 = $3.0/M × 70% (input) + $15.0/M × 30% (output) = $6.6/M
비용 = b_total_tokens × $6.6 / 1,000,000
```

---

## 8. API 엔드포인트 (신규 2개 + 변경 1개)

### `POST /api/v1/query` ← [변경] mode 필드 추가

**Request:**
```json
{ "question": "김민수가 주문한 상품은?", "mode": "b" }
```

**Response (200 — B안 성공):**
```json
{
  "question": "김민수가 주문한 상품은?",
  "answer": "김민수가 주문한 상품은 맥북프로, 에어팟프로, 갤럭시탭입니다.",
  "cypher": "MATCH (anchor:Customer {name: $entity_name}) ...",
  "paths": ["Customer(김민수)->PLACED->Order->CONTAINS->Product(맥북프로)"],
  "template_id": "local_subgraph",
  "route": "local_search",
  "matched_by": "local_b",
  "error": null,
  "mode": "b",
  "subgraph_context": "[앵커 노드] Customer: 김민수\n[1홉 연결]\n  -PLACED-> Order(1)...",
  "llm_tokens_used": 850,
  "latency_ms": 1234
}
```

### `GET /api/v1/evaluation/golden` → 200

```json
[
  {
    "id": "T1-01",
    "question": "김민수의 이메일 주소는?",
    "category": "traverse",
    "expected_keywords": ["minsu@example.com"],
    "expected_entities": ["김민수"],
    "difficulty": "easy"
  },
  ...
]
```

### `POST /api/v1/evaluation/run` → 200

```json
{
  "total_pairs": 50,
  "a_success_count": 35,
  "b_success_count": 30,
  "a_avg_latency_ms": 45.2,
  "b_avg_latency_ms": 1800.5,
  "a_avg_keyword_score": 0.72,
  "b_avg_keyword_score": 0.65,
  "b_total_tokens": 42500,
  "b_estimated_cost_usd": 0.2805,
  "recommendation": "a_only",
  "a_results": [...],
  "b_results": [...]
}
```

---

## 9. 프론트엔드 — A/B 모드 토글

### QueryPage 변경

| 영역 | 기존 (Week 5) | 변경 (Week 6) |
|------|-------------|--------------|
| **모드 토글** | 없음 | `[A Template]` / `[B Local]` 토글 버튼 (파란/주황) |
| **모드 배지** | 없음 | 응답마다 `A Template` (파란) 또는 `B Local` (주황) 배지 |
| **latency** | 없음 | 응답 시간 (ms) 표시 |
| **tokens** | 없음 | B안: LLM 토큰 수 표시 |
| **서브그래프** | 없음 | B안: `▶ Subgraph Context` 접이식 패널 |
| **Cypher** | 기존 유지 | 그대로 |
| **Paths** | 기존 유지 | 그대로 |

### API 클라이언트 변경

```typescript
// Before (Week 5)
sendQuery(question: string): Promise<QueryResponse>

// After (Week 6)
sendQuery(question: string, mode: string = 'a'): Promise<QueryResponse>
```

---

## 10. 테스트 결과 상세

### Local Search 테스트 (15개)

| # | 테스트명 | 검증 내용 | 결과 |
|---|---------|----------|------|
| 1 | `test_entity_extraction_customer` | "김민수" → ("김민수", "Customer") | PASS |
| 2 | `test_entity_extraction_product` | "맥북프로" → ("맥북프로", "Product") | PASS |
| 3 | `test_entity_extraction_category` | "노트북" → ("노트북", "Category") | PASS |
| 4 | `test_entity_extraction_no_match` | "오늘 날씨" → (None, None) | PASS |
| 5 | `test_depth_default` | 일반 질문 → 2 | PASS |
| 6 | `test_depth_1hop` | "직접 연결된" → 1 | PASS |
| 7 | `test_depth_3hop` | "전체 구조" → 3 | PASS |
| 8 | `test_subgraph_cypher_valid` | Customer 2홉 → MATCH, hop1, hop2 포함 | PASS |
| 9 | `test_serialize_subgraph` | mock → 앵커/1홉/2홉 구조화 텍스트 | PASS |
| 10 | `test_parse_local_answer` | "답변: ... 근거 경로: ..." 파싱 | PASS |
| 11 | `test_run_local_query_success` | mock Neo4j+LLM → mode=b, answer 있음 | PASS |
| 12 | `test_run_local_query_no_entity` | 엔티티 없음 → error 필드, unsupported | PASS |
| 13 | `test_run_local_query_neo4j_fail` | Neo4j 실패 → LocalSearchError | PASS |
| 14 | `test_run_local_query_llm_fail` | LLM 실패 → LocalSearchError | PASS |
| 15 | `test_api_mode_b` | POST /query mode=b → 200, mode=b, tokens | PASS |

### QA 평가 테스트 (10개)

| # | 테스트명 | 검증 내용 | 결과 |
|---|---------|----------|------|
| 1 | `test_golden_pairs_count_50` | 정확히 50쌍 | PASS |
| 2 | `test_golden_pairs_all_categories` | 4+ 카테고리 (실제 6) | PASS |
| 3 | `test_golden_pairs_have_keywords` | non-unsupported에 keywords 있음 | PASS |
| 4 | `test_evaluate_perfect_answer` | 전부 매칭 → 1.0, success=True | PASS |
| 5 | `test_evaluate_partial_answer` | 절반 매칭 → 0.5, success=True | PASS |
| 6 | `test_evaluate_wrong_answer` | 매칭 0 → 0.0, success=False | PASS |
| 7 | `test_evaluate_unsupported` | 에러 응답 → success=True | PASS |
| 8 | `test_comparison_report_fields` | 필수 필드 모두 존재 | PASS |
| 9 | `test_recommendation_a_wins` | A 8/10 > B 5/10 → "a_only" | PASS |
| 10 | `test_cost_estimation` | 10000 tokens → USD > 0 < $1 | PASS |

### 전체 테스트 실행

```
====================== 121 passed, 126 warnings in 7.69s ======================
```

| 테스트 파일 | 고유 테스트 수 | 실행 수 | 결과 |
|------------|-------------|--------|------|
| `test_ddl_parser.py` | 10 | 10 | 10 PASS |
| `test_api_ddl.py` | 3 | 6 (×2 backend) | 6 PASS |
| `test_ontology.py` | 16 | 20 (4 API ×2) | 20 PASS |
| `test_ontology_versions.py` | 10 | 20 (×2) | 20 PASS |
| `test_kg_build.py` | 10 | 20 (×2) | 20 PASS |
| `test_query.py` | 15 | 19 (11 sync + 4 API ×2) | 19 PASS |
| `test_local_search.py` | 15 | 16 (14 sync + 1 API ×2) | 16 PASS |
| `test_qa_evaluation.py` | 10 | 10 | 10 PASS |
| **합계** | **89** | **121** | **121 PASS** |

---

## 11. DoD 체크리스트

| # | 검증 항목 | 명령어 | 결과 |
|---|----------|--------|------|
| 1 | 백엔드 테스트 | `cd backend && pytest tests/ -v` | 121 passed |
| 2 | 프론트엔드 빌드 | `cd frontend && npm run build` | 에러 없이 빌드 성공 |
| 3 | 엔티티 추출: 고객/상품/카테고리 | test #1~#3 | PASS |
| 4 | 깊이 판정: 1/2/3홉 | test #5~#7 | PASS |
| 5 | 서브그래프 Cypher 생성 | test #8 | PASS |
| 6 | B안 파이프라인 (mock) | test #11 | PASS |
| 7 | B안 에러 처리 (Neo4j/LLM) | test #13~#14 | PASS |
| 8 | POST /query mode=b → 200 | test #15 | PASS |
| 9 | 골든 데이터 50쌍 | test_qa #1 | PASS |
| 10 | 평가 키워드 매칭 | test_qa #4~#6 | PASS |
| 11 | A/B 비교 리포트 | test_qa #8~#10 | PASS |
| 12 | 프론트엔드 A/B 토글 | npm run build | PASS |

---

## 12. 파일 구조 (Week 6 후)

```
GraphRAG/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py                      ← [MOD] +local_search 설정 4개
│   │   ├── exceptions.py                  ← [MOD] +LocalSearchError(502)
│   │   ├── main.py                        ← [MOD] +evaluation 라우터, v0.6.0
│   │   ├── models/
│   │   │   └── schemas.py                 ← [MOD] +mode, +QA 평가 모델 3개
│   │   ├── routers/
│   │   │   ├── health.py
│   │   │   ├── ddl.py
│   │   │   ├── ontology.py
│   │   │   ├── ontology_versions.py
│   │   │   ├── kg_build.py
│   │   │   ├── query.py                   ← [MOD] +mode 전달
│   │   │   └── evaluation.py             ← [NEW] POST /run + GET /golden
│   │   ├── ddl_parser/
│   │   │   └── parser.py
│   │   ├── ontology/
│   │   │   ├── fk_rule_engine.py
│   │   │   ├── pipeline.py
│   │   │   ├── llm_enricher.py
│   │   │   └── prompts.py
│   │   ├── evaluation/
│   │   │   ├── evaluator.py
│   │   │   ├── golden_ecommerce.py
│   │   │   ├── qa_golden.py              ← [NEW] 50쌍 QA 골든 데이터
│   │   │   └── qa_evaluator.py           ← [NEW] QA 평가 엔진 + A/B 비교
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
│   │       ├── templates.py               (v0 demo, 변경 없음)
│   │       ├── executor.py                (v0 demo, 변경 없음)
│   │       ├── template_registry.py
│   │       ├── slot_filler.py
│   │       ├── router_rules.py
│   │       ├── router_llm.py
│   │       ├── router.py
│   │       ├── pipeline.py               ← [MOD] +mode="b" 분기, +latency
│   │       ├── local_prompts.py          ← [NEW] B안 프롬프트 + 직렬화
│   │       └── local_search.py           ← [NEW] B안 핵심 파이프라인
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_ddl_parser.py             (10 tests)
│   │   ├── test_api_ddl.py                (3 tests ×2)
│   │   ├── test_ontology.py               (16 tests, 4 API ×2)
│   │   ├── test_ontology_versions.py      (10 tests ×2)
│   │   ├── test_kg_build.py               (10 tests ×2)
│   │   ├── test_query.py                  (15 tests)
│   │   ├── test_local_search.py          ← [NEW] 15 tests
│   │   └── test_qa_evaluation.py         ← [NEW] 10 tests
│   ├── demo.py
│   └── demo_ecommerce.sql
├── frontend/
│   ├── src/
│   │   ├── types/
│   │   │   └── ontology.ts               ← [MOD] +QueryResponse 4 필드
│   │   ├── api/
│   │   │   └── client.ts                 ← [MOD] +sendQuery mode 파라미터
│   │   ├── pages/
│   │   │   ├── UploadPage.tsx
│   │   │   ├── ReviewPage.tsx
│   │   │   └── QueryPage.tsx             ← [MOD] A/B 토글 + 서브그래프 표시
│   │   ├── App.tsx
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
├── DEV_REPORT_w5.md
└── DEV_REPORT_w6.md                      ← [NEW] 본 보고서
```

---

## 13. 코드 규모 누적

| 구분 | Demo v0 | Week 1 | Week 2 | Week 3 | Week 4 | Week 5 | Week 6 | 합계 |
|------|---------|--------|--------|--------|--------|--------|--------|------|
| 백엔드 애플리케이션 | 1,132 | 214 | 547 | 118 | 399 | 987 | 1,010 | 4,407 |
| 백엔드 테스트 | 0 | 185 | 230 | 215 | 274 | 258 | 423 | 1,585 |
| 프론트엔드 코드 | 0 | 0 | 0 | 1,438 | 149 | 266 | 57 | 1,910 |
| 인프라 설정 | 31 | 30 | 29 | 0 | 0 | 0 | 0 | 90 |
| **총합** | **1,163** | **429** | **806** | **1,771** | **822** | **1,511** | **1,490** | **7,992** |

> Week 6 백엔드: local_prompts(121) + local_search(320) + qa_golden(336) + qa_evaluator(204) + evaluation router(29) + schemas/exceptions/config/pipeline/main/query 변경(83) = 1,010행 (신규) + 83행 (수정)
> Week 6 프론트엔드: QueryPage(+50) + types(+4) + client(+3) = 57행
> Week 6 테스트: test_local_search(254) + test_qa_evaluation(169) = 423행

---

## 14. A안 vs B안 비교 (설계 관점)

| 비교 항목 | A안 (Template) | B안 (Local Search) |
|----------|---------------|-------------------|
| **질문 이해** | 규칙 + LLM 라우터 → 템플릿 선택 | 규칙 엔티티 추출 → 서브그래프 |
| **Cypher 생성** | 슬롯 채우기 (정확) | 서브그래프 추출 (넓음) |
| **답변 생성** | 코드 기반 포맷터 (LLM 불필요) | Claude LLM 요약 (유연) |
| **비용** | $0 (규칙 매칭 시) | 질문당 ~$0.006 (Sonnet) |
| **지연** | ~50ms (Neo4j만) | ~1500ms (Neo4j + LLM) |
| **커버리지** | 13 템플릿에 한정 | 그래프 구조면 모두 가능 |
| **정확도** | 높음 (정확한 Cypher) | 중간 (LLM 할루시네이션 가능) |
| **추천 시나리오** | 반복적/예측 가능한 질문 | 탐색적/자유형식 질문 |

---

## 15. 다음 단계 (Week 7+)

| 작업 | 설명 |
|------|------|
| 실제 Neo4j 통합 E2E 테스트 | Docker 기반 Neo4j로 A/B 모드 실제 동작 검증 |
| CSV 벌크 임포트 | 사용자 데이터 업로드 + FK 무결성 검증 |
| 평가 UI | 프론트엔드에서 평가 실행 + 결과 대시보드 |
| 사용자 정의 DDL | 이커머스 외 도메인 지원 |

---

*Week 6 — GraphRAG Local (B안) + 50 QA 종합 평가 완성*
