# DIKW Wisdom Layer + TTV 최적화 개발보고서

> **작성일**: 2026-03-06
> **버전**: v1.0.0
> **범위**: DIKW Wisdom 계층 구현 + KG 빌드 TTV 최적화 + Auto Demo UX

---

## 1. DIKW 피라미드란?

### 1.1 개념

DIKW는 **Data → Information → Knowledge → Wisdom** 의 4계층 지식 피라미드이다.
1947년 T.S. Eliot의 시에서 영감을 받아 Russell Ackoff(1989)가 체계화한 프레임워크로,
데이터가 의사결정에 이르기까지의 단계적 가치 변환 과정을 설명한다.

```
    /\
   /  \      Wisdom    "무엇을 해야 하는가?" — 판단, 의사결정
  /----\
 / Know \    Knowledge "왜 그런가?" — 패턴, 인과관계, 연결
/--------\
/  Info   \  Information "무엇이 일어났는가?" — 정리, 구조화, 관계
/----------\
/   Data    \ Data "원시 사실" — 테이블, 레코드, 수치
/____________\
```

| 계층 | 핵심 질문 | 예시 (E-commerce) |
|------|-----------|-------------------|
| **Data** | 무엇이 있는가? | 주문 3,247건, 고객 523명, 리뷰 891개 |
| **Information** | 무엇이 일어났는가? | 김민수가 전자기기 카테고리에서 5회 주문, 총 700만원 |
| **Knowledge** | 왜 그런가? | 리뷰 평점 4.5+ 상품은 주문량이 2.3배 높다 |
| **Wisdom** | 무엇을 해야 하는가? | 김민수에게 고평점 가전 신규 입고 알림 발송 권장 |

### 1.2 왜 GraphRAG에 DIKW가 필요한가?

기존 GraphRAG 시스템의 A/B 모드는 Data~Knowledge 수준의 답변만 가능했다.

| 기존 모드 | 커버 범위 | 한계 |
|-----------|-----------|------|
| **A (템플릿)** | Data → Information | 정해진 패턴만 응답, 인사이트 없음 |
| **B (로컬서치)** | Data → Knowledge | 서브그래프 요약, 패턴 발견 가능하나 행동 제안 없음 |

고객이 우리 서비스를 도입했을 때 **"그래서 뭘 해야 하는데?"** 라는 질문에 답하려면,
그래프 데이터에서 의사결정까지 연결하는 Wisdom 계층이 필수적이다.

---

## 2. 구현 내용

### 2.1 아키텍처 개요

```
사용자 질문
    │
    ▼
┌──────────────────┐
│ Wisdom Router    │  regex 기반 의도 분류
│ (intent 분류)    │  W1~W5 + Lookup fallback
└────────┬─────────┘
         ▼
┌──────────────────┐
│ Entity Extractor │  고객/공급사 이름 추출
│ (룰 기반)        │  {"김민수","이영희",...}
└────────┬─────────┘
         ▼
┌──────────────────────────────┐
│ Multi-Query Collector        │  Intent별 Cypher 쿼리 세트 실행
│ 글로벌 7개 + 엔티티별 6개     │  → 다관점 데이터 수집
└────────┬─────────────────────┘
         ▼
┌──────────────────┐
│ Wisdom Engine    │  수집된 데이터 + 질문 → LLM (GPT-4o)
│ (LLM 분석)       │  → 구조화된 DIKW JSON 응답
└────────┬─────────┘
         ▼
┌──────────────────┐
│ DIKW Response    │  4계층 분석 + 근거 + 행동제안 + 연관질문
└──────────────────┘
```

### 2.2 Wisdom 의도 분류 (5가지 질문 유형)

`backend/app/query/wisdom_router.py`

| 의도 | 키워드 | 데모 질문 | 수집 쿼리 |
|------|--------|-----------|-----------|
| **W1 Pattern** | 패턴, 트렌드, 분석 | "고객 구매 패턴에서 어떤 트렌드가 보이나요?" | 세그먼트 + 카테고리 + 동시구매 + 공급사 + 리뷰 |
| **W2 Causal** | 왜, 원인, 상관관계 | "리뷰 평점이 높은 상품이 더 많이 팔리나요?" | 리뷰 + 쿠폰 + 카테고리 + 세그먼트 |
| **W3 Recommend** | 추천, 제안, 개선 | "김민수에게 어떤 상품을 추천하면 좋을까요?" | 세그먼트 + 동시구매 + 리뷰 + 협업필터링 |
| **W4 What-If** | 만약, 중단, 영향 | "애플코리아 공급이 중단되면 어떤 영향?" | 공급사의존 + 카테고리 + 세그먼트 + 영향분석 |
| **W5 DIKW Trace** | DIKW, 종합분석 | "김민수에 대한 DIKW 종합 분석을 해줘" | 전체 7개 글로벌 + 고객별 3개 |

우선순위: `DIKW Trace > What-If > Recommendation > Causal > Pattern > Lookup`

### 2.3 Multi-Query Collector

`backend/app/query/wisdom_collector.py`

기존 A/B 모드가 **단일 Cypher 쿼리**를 실행하는 것과 달리,
Wisdom 모드는 **다중 Cypher 쿼리**를 조합 실행하여 여러 관점의 데이터를 수집한다.

**글로벌 쿼리 (7개)** — 전체 그래프 집계:

| 쿼리 키 | 설명 |
|---------|------|
| `customer_segments` | 고객 세그먼트 (VIP/Regular/Light) |
| `category_distribution` | 카테고리별 주문/상품 분포 |
| `co_purchase` | 동시구매 패턴 Top 10 |
| `supplier_dependency` | 공급사별 의존도 (상품수, 주문수, 매출) |
| `review_quality` | 상품별 평균 평점 vs 주문량 |
| `coupon_impact` | 쿠폰 사용/미사용 주문 비교 |
| `payment_methods` | 결제 수단별 통계 |

**엔티티 쿼리 (6개)** — 특정 고객/공급사 포커스:

| 쿼리 키 | 설명 |
|---------|------|
| `customer_orders` | 대상 고객의 주문 + 상품 + 카테고리 |
| `customer_reviews` | 대상 고객이 작성한 리뷰 |
| `customer_graph_2hop` | 대상 고객 중심 2홉 서브그래프 |
| `supplier_impact` | 공급사 제거 시 영향 범위 정량화 |
| `supplier_alternatives` | 대체 공급사/상품 탐색 |
| `recommendation_collab` | 협업 필터링 기반 상품 추천 |

### 2.4 Wisdom Engine (DIKW 분석)

`backend/app/query/wisdom_engine.py`

수집된 멀티 쿼리 데이터를 직렬화하여 LLM에 전달하고,
**구조화된 DIKW JSON** 응답을 파싱한다.

```
run_wisdom_query(question)
  ├── classify_wisdom_intent(question)  → WisdomIntent
  ├── _extract_entity(question)         → "김민수" | None
  ├── collect_data(intent, entity)      → {query_key: records}
  ├── serialize_collected_data(data)    → 구조화된 텍스트
  ├── _generate_wisdom(question, intent, text)
  │     └── OpenAI GPT-4o (temperature=0)
  └── _parse_wisdom_response(raw_json)
        ├── JSON 파싱 (정상)
        ├── Markdown 코드블록 추출 (```json...```)
        └── Fallback (비JSON → wisdom 레이어에 원문 삽입)
```

**LLM 응답 형식** (`wisdom_prompts.py` 시스템 프롬프트):

```json
{
  "layers": [
    {"level": "data",        "title": "...", "content": "...", "evidence": [...]},
    {"level": "information", "title": "...", "content": "...", "evidence": [...]},
    {"level": "knowledge",   "title": "...", "content": "...", "evidence": [...]},
    {"level": "wisdom",      "title": "...", "content": "...", "evidence": [...]}
  ],
  "summary": "핵심 한 줄 요약",
  "confidence": "high | medium | low",
  "action_items": ["행동 제안 1", "행동 제안 2"],
  "related_queries": ["추가 탐색 질문 1", "추가 탐색 질문 2"]
}
```

### 2.5 API 엔드포인트

`backend/app/routers/wisdom.py`

```
POST /api/v1/wisdom/query
Body: { "question": "..." }
Response: WisdomResponse (dikw_layers, summary, confidence, action_items, ...)
```

### 2.6 프론트엔드: DIKW Timeline UI

`frontend/src/components/wisdom/DIKWTimeline.tsx`

Q&A 페이지에 **W 모드** 추가 (기존 A/B 모드와 동급):

- **A/B/W 토글**: 파란(A 템플릿) / 주황(B 로컬) / 앰버(W 위즈덤) 3모드
- **D→I→K→W 타임라인**: 수직 그라데이션 라인 + 계층별 컬러 도트
  - Data(slate) → Information(blue) → Knowledge(purple) → Wisdom(amber)
- **계층별 카드**: 클릭으로 확장/축소, 근거(evidence) 목록 표시
- **행동 제안**: 앰버 카드로 강조된 권장 행동 목록
- **연관 질문**: 클릭하면 해당 질문으로 바로 Wisdom 분석 실행
- **메타데이터**: latency(ms), token 사용량, confidence 배지, 사용된 쿼리 목록

`frontend/src/pages/QueryPage.tsx`:

- `Mode = 'a' | 'b' | 'w'` 타입 확장
- W 모드 전용 데모 질문 5개 (`WISDOM_DEMO_QUESTIONS`)
- Wisdom 응답은 `DIKWTimeline` 컴포넌트로 렌더링
- 연관 질문 클릭 시 자동 재질문 (`onRelatedQuery`)

---

## 3. TTV 최적화

### 3.1 문제 진단

**TTV (Time To Value)**: DDL 업로드부터 첫 인사이트 답변까지의 소요 시간.

KG 빌드 단계에서 `_ensure_name()` 함수가 **노드 타입마다 LLM API를 직렬 호출**하여
8~27초가 추가 소요되는 병목이 발생했다.

```
빌드 시간 분해:
  데이터 생성:  ~0.5초
  FK 검증:     ~0.1초
  Neo4j 적재:  ~1.0초
  LLM 호출:    ~8-27초  ← 병목 (노드 9개 × 1-3초/호출)
```

### 3.2 해결: 5단계 워터폴

`backend/app/kg_builder/loader.py`

LLM 호출을 마지막 수단으로 밀어내는 **5단계 워터폴**을 구현했다.

```
_ensure_name(label, rows, prop_names)
  ├── 1. 하드코딩 템플릿 (_KNOWN_NAME_TEMPLATES)     ← 즉시
  ├── 2. 인메모리 캐시  (_name_template_cache)        ← 즉시
  ├── 3. 규칙 추론     (_infer_name_template)         ← 즉시
  ├── 4. LLM 호출     (_ask_llm_name_template)       ← 1-3초/호출
  └── 5. 폴백         (label + " #{id}")             ← 즉시
```

**하드코딩 템플릿** (E-commerce 도메인):

```python
_KNOWN_NAME_TEMPLATES = {
    "Order":    "주문 #{id} ({status})",
    "Payment":  "결제 #{id} ({method})",
    "Review":   "리뷰 #{id} ({rating}점)",
    "Address":  "{city} {district}",
    "Shipping": "배송 #{id} ({status})",
    "Coupon":   "{code} ({discount_pct}%)",
}
```

**규칙 추론** (범용):

```python
def _infer_name_template(label, prop_names):
    # name/title/code 프로퍼티가 있으면 그것만 사용
    # id + status/type/method/category → "Label #{id} ({extra})"
    # id만 있으면 → "Label #{id}"
```

### 3.3 결과

| 지표 | 최적화 전 | 최적화 후 | 개선 |
|------|-----------|-----------|------|
| KG 빌드 LLM 호출 | 5-6회 | **0회** | 100% 제거 |
| KG 빌드 시간 | 10-30초 | **~2초** | 80-93% 단축 |
| TTV (수동 플로우) | 40-60초 | **~10초** | 75-83% 단축 |
| TTV (Auto Demo) | N/A | **~5초** | 1-Click 신규 |

- E-commerce 도메인: 9개 노드 타입 전부 1-3단계에서 해소 → **LLM 호출 0회**
- 미지의 도메인: 4단계(LLM)까지 가되, 캐시로 2회차부터는 즉시
- `neo4j_connect_timeout`: 90초 → 10초 (연결 실패 시 빠른 피드백)

### 3.4 Auto Demo (1-Click)

`frontend/src/pages/UploadPage.tsx`

기존에 사용자가 5단계를 수동으로 클릭해야 했던 플로우를:

```
기존: 파일선택 → 업로드 → 생성 → (Review) 승인 → Build KG → Q&A
      클릭 5회, 대기 3회, 페이지 전환 2회
```

**Auto Demo (1-Click)** 버튼 하나로 통합:

```
Auto Demo: 파일선택 → [Auto Demo] 클릭 1회
  ├── DDL 파싱 중...
  ├── 온톨로지 생성 중... (skip_llm=true)
  ├── 자동 승인 중...
  ├── KG 빌드 시작...
  ├── 데이터 생성 중... → FK 검증 중... → Neo4j 적재 중...
  └── Q&A 페이지로 이동
```

- 프로그레스 바 + 단계별 메시지로 진행 상황 표시
- 완료 시 Review 페이지를 건너뛰고 Q&A 페이지로 직접 이동

---

## 4. 변경 파일 요약

### 4.1 백엔드 (신규)

| # | 파일 | 설명 | 라인 |
|---|------|------|------|
| 1 | `app/query/wisdom_router.py` | 의도 분류 (regex, 5 intent + lookup) | 62 |
| 2 | `app/query/wisdom_collector.py` | Multi-Query Cypher 수집기 (7+6 쿼리) | 207 |
| 3 | `app/query/wisdom_prompts.py` | 시스템 프롬프트 + 데이터 직렬화 | 126 |
| 4 | `app/query/wisdom_engine.py` | Wisdom 오케스트레이터 (classify→collect→LLM→parse) | 179 |
| 5 | `app/routers/wisdom.py` | POST /api/v1/wisdom/query 엔드포인트 | 17 |
| 6 | `tests/test_wisdom.py` | Wisdom 계층 테스트 25개 | 207 |

### 4.2 백엔드 (수정)

| # | 파일 | 변경 내용 |
|---|------|-----------|
| 7 | `app/models/schemas.py` | DIKWLayer, WisdomRequest, WisdomResponse 모델 추가 |
| 8 | `app/main.py` | wisdom 라우터 등록, 버전 1.0.0 |
| 9 | `app/config.py` | wisdom_model, wisdom_max_tokens, neo4j_connect_timeout(10) |
| 10 | `app/kg_builder/loader.py` | _ensure_name 5단계 워터폴 + 하드코딩 + 규칙추론 + 캐시 |

### 4.3 프론트엔드 (신규)

| # | 파일 | 설명 |
|---|------|------|
| 11 | `src/components/wisdom/DIKWTimeline.tsx` | D→I→K→W 타임라인 시각화 (163줄) |

### 4.4 프론트엔드 (수정)

| # | 파일 | 변경 내용 |
|---|------|-----------|
| 12 | `src/pages/QueryPage.tsx` | A/B/W 3모드 토글, Wisdom 응답 렌더링 |
| 13 | `src/pages/UploadPage.tsx` | Auto Demo 버튼 + handleAutoDemo 파이프라인 |
| 14 | `src/App.tsx` | onAutoComplete 라우팅 (Auto Demo → Q&A 직행) |
| 15 | `src/api/client.ts` | sendWisdomQuery() API 함수 |
| 16 | `src/types/ontology.ts` | DIKWLayer, WisdomResponse TS 타입 |
| 17 | `src/constants.ts` | WISDOM_DEMO_QUESTIONS (W1-W5) |

**총 17개 파일** 변경 (신규 7개, 수정 10개)

---

## 5. 테스트 현황

### 5.1 Wisdom 테스트 (25개)

| 클래스 | 테스트 수 | 범위 |
|--------|-----------|------|
| TestWisdomRouter | 12 | 6개 의도 × 2 패턴 |
| TestWisdomPrompts | 2 | 직렬화 + 메시지 빌드 |
| TestWisdomCollector | 2 | 쿼리맵 무결성 + 엔티티 쿼리 |
| TestWisdomEngine | 6 | 엔티티 추출 3 + JSON 파싱 3 |
| TestWisdomModels | 2 | Pydantic 모델 검증 |
| TestWisdomAPI | 1 | 엔드포인트 등록 확인 |

### 5.2 전체 테스트 스위트

```
211 passed in 330.73s
```

전체 기존 테스트 회귀 없음 확인 완료.

---

## 6. 무엇이 나아졌는가

### 6.1 기능 관점

| 항목 | Before | After |
|------|--------|-------|
| 질문 모드 | A/B 2종 | **A/B/W 3종** |
| 답변 수준 | Data~Knowledge | **Data~Wisdom** |
| 쿼리 전략 | 단일 Cypher | 단일 + **멀티 Cypher** |
| 행동 제안 | 없음 | **구체적 action_items** |
| 연관 탐색 | 없음 | **클릭형 related_queries** |
| 신뢰도 표시 | 없음 | **high/medium/low** |
| 데모 온보딩 | 5단계 수동 클릭 | **1-Click Auto Demo** |

### 6.2 성능 관점

| 지표 | Before | After |
|------|--------|-------|
| KG 빌드 시간 | 10-30초 | **~2초** |
| TTV (데모) | 40-60초 | **~5초 (Auto)** |
| LLM 호출 (빌드) | 5-6회 | **0회** |
| Neo4j 타임아웃 | 90초 | **10초** |

### 6.3 고객 가치 관점

**Before**: "우리 데이터로 뭘 할 수 있는지 보여주세요" → 수동 조작 5회 + 30초 대기 후 단순 조회만 가능

**After**: "우리 데이터로 뭘 할 수 있는지 보여주세요" → 1-Click 5초 후 DIKW 분석까지 시연 가능

- 고객이 **"그래서 뭘 해야 하는데?"** 라는 질문에 답변 가능
- 데모 시 **첫 인상**: DDL 파일 하나로 5초 만에 인사이트까지 도달
- **DIKW 시각화**: D→I→K→W 계층이 눈에 보이므로 "단순 DB 조회"와 차별화

---

## 7. 앞으로 할 수 있는 것

### 7.1 단기 (1-2주)

| 항목 | 설명 | 기대 효과 |
|------|------|-----------|
| **Wisdom 캐시** | 동일 질문 → 캐시 응답 (demo_cache처럼) | W 모드 응답 2-5초 → 즉시 |
| **스트리밍 응답** | SSE로 DIKW 계층을 순차 스트리밍 | 체감 대기시간 감소 |
| **커스텀 도메인 템플릿** | DDL 업로드 시 도메인 자동 감지 → 맞춤 Cypher | E-commerce 외 도메인 확장 |

### 7.2 중기 (3-4주)

| 항목 | 설명 | 기대 효과 |
|------|------|-----------|
| **What-If 시뮬레이션 엔진** | 실제 그래프에서 노드 제거 후 영향 계산 | LLM 추정 → 그래프 기반 정량 분석 |
| **DIKW 대시보드** | Wisdom 분석 결과를 차트/그래프로 시각화 | 경영진 프레젠테이션용 |
| **멀티턴 Wisdom 대화** | 이전 분석 컨텍스트를 유지한 후속 질문 | "좀 더 자세히" → 드릴다운 |
| **Wisdom → 그래프 연동** | Wisdom 분석의 관련 노드를 ExplorePage에서 하이라이트 | 인사이트의 근거를 시각적으로 확인 |

### 7.3 장기 (1-2개월)

| 항목 | 설명 | 기대 효과 |
|------|------|-----------|
| **도메인 무관 Wisdom** | DDL 구조에서 자동으로 Cypher 쿼리 생성 | E-commerce 외 모든 도메인 즉시 지원 |
| **예측/경고 시스템** | 주기적 Wisdom 분석 → 이상 감지 시 알림 | 사전 대응형 인사이트 |
| **Wisdom Report 내보내기** | PDF/Notion/Slack으로 분석 결과 공유 | 팀 전체 인사이트 공유 |
| **A/B/W 자동 비교** | 같은 질문에 대해 3모드 동시 실행 → 비교 | 모드별 장단점 시각적 확인 |

---

## 8. 시스템 구성도 (현재 v1.0.0)

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)               │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐              │
│  │ Upload   │→ │ Review    │→ │ Query    │              │
│  │ Page     │  │ Page      │  │ Page     │              │
│  │          │  │           │  │ A│B│W 모드│              │
│  │ [Auto    │  │ Ontology  │  │          │              │
│  │  Demo]   │  │ Edit/KG   │  │ DIKW     │              │
│  └──────────┘  └───────────┘  │ Timeline │              │
│       │                       └──────────┘              │
│       │ 1-Click                     │                    │
│       └─────────────────────────────┘                    │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API
┌──────────────────────┴──────────────────────────────────┐
│                    Backend (FastAPI)                      │
│                                                          │
│  DDL Parser → FK Rules → Ontology → KG Builder           │
│                                                          │
│  Query Pipeline:                                         │
│    A: Rule Router → Template → Cypher → Neo4j            │
│    B: Entity Extract → Subgraph → LLM (Sonnet)          │
│    W: Intent Classify → Multi-Query → LLM (GPT-4o)      │
│       → DIKW Structured Response                         │
│                                                          │
│  TTV Waterfall: Hardcode→Cache→Rules→LLM→Fallback       │
└──────────────────────┬──────────────────────────────────┘
                       │
            ┌──────────┴──────────┐
            │     Neo4j           │
            │  Knowledge Graph    │
            │  9 nodes, 12 rels   │
            └─────────────────────┘
```

---

## 부록: Pydantic 모델 (Wisdom 관련)

```python
class DIKWLayer(BaseModel):
    level: str       # "data" | "information" | "knowledge" | "wisdom"
    title: str
    content: str
    evidence: list[str] = []

class WisdomRequest(BaseModel):
    question: str

class WisdomResponse(BaseModel):
    question: str
    intent: str                          # pattern | causal | recommendation | what_if | dikw_trace
    dikw_layers: list[DIKWLayer]
    summary: str
    confidence: str                      # high | medium | low
    action_items: list[str] = []
    related_queries: list[str] = []
    cypher_queries_used: list[str] = []
    latency_ms: int = 0
    llm_tokens_used: int = 0
```
