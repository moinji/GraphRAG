# DIKW 향후 과제 상세 분석

> **작성일**: 2026-03-06
> **현재 버전**: v1.0.0 (211 tests, A/B/W 3모드)
> **컨텍스트**: 1인 풀스택, B2B SaaS 데모 제품

---

## 분석 기준

각 과제를 5가지 축으로 평가한다.

| 축 | 설명 |
|---|------|
| **고객 임팩트** | 데모/영업 시 고객에게 보이는 차별화 정도 |
| **기술 난이도** | 변경 파일 수, 아키텍처 변경 범위, 신규 의존성 |
| **현재 병목** | 지금 시스템에서 가장 아픈 곳을 해결하는가 |
| **확장성** | E-commerce 외 도메인에서도 작동하는가 |
| **구현 시간** | 1인 기준 예상 소요 (단, 추정치는 참고용) |

---

## 단기 과제 (1-2주)

### S1. Wisdom 캐시 (데모 응답 즉시화)

#### 문제

W 모드 질문 1회에 **2-5초** 소요 (Multi-Query 수집 + GPT-4o 호출).
데모에서 W1~W5 질문을 클릭할 때마다 대기가 발생한다.
A 모드는 `demo_cache.py`로 즉시 응답하는데, W 모드에는 이 구조가 없다.

#### 현재 구조

```
A 모드: question → demo_cache.py (hit?) → 즉시 응답
W 모드: question → classify → collect(Neo4j 7쿼리) → GPT-4o → 파싱
```

#### 해결 방안

`wisdom_cache.py` 신규 파일 — A 모드의 `demo_cache.py`와 동일 패턴:

```python
# app/query/wisdom_cache.py
_WISDOM_CACHE: dict[str, WisdomResponse] = {
    "고객 구매 패턴에서 어떤 트렌드가 보이나요?": WisdomResponse(
        question="...",
        intent="pattern",
        dikw_layers=[
            DIKWLayer(level="data", title="원시 데이터",
                      content="고객 5명, 주문 12건, 상품 8개, 리뷰 6개 데이터 분석",
                      evidence=["customers 5건", "orders 12건", "products 8건"]),
            # ... I, K, W 레이어
        ],
        summary="VIP 고객(김민수)이 전체 매출의 40%를 차지하며...",
        confidence="high",
        action_items=["VIP 리텐션 프로그램 도입", "..."],
        ...
    ),
    # W2~W5 캐시 엔트리
}
```

`wisdom_engine.py`에서 캐시 우선 조회:

```python
def run_wisdom_query(question: str) -> WisdomResponse:
    from app.query.wisdom_cache import get_cached_wisdom
    cached = get_cached_wisdom(question)
    if cached:
        return cached
    # 기존 파이프라인...
```

#### 변경 파일

| 파일 | 변경 |
|------|------|
| `app/query/wisdom_cache.py` | **신규** — 5개 골든 응답 하드코딩 |
| `app/query/wisdom_engine.py` | 2줄 추가 (캐시 조회) |
| `tests/test_wisdom.py` | 캐시 hit/miss 테스트 2개 추가 |

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **높음** | 데모 5개 질문 즉시 응답 → 체감 속도 극적 개선 |
| 기술 난이도 | **낮음** | demo_cache.py 패턴 복사, 신규 파일 1개 |
| 현재 병목 | **높음** | W 모드 2-5초 대기가 데모 흐름을 끊는 핵심 병목 |
| 확장성 | **낮음** | E-commerce 시드 데이터 전용 캐시 |
| 구현 시간 | 2-3시간 | 캐시 데이터 작성이 대부분 |

#### 우선순위: **1순위** — ROI 최고 (노력 최소, 효과 최대)

---

### S2. 스트리밍 응답 (SSE)

#### 문제

W 모드에서 LLM 응답을 **전체 완료 후 한 번에** 표시한다.
2-5초 동안 "DIKW 분석 중..." 메시지만 보이고 아무 변화가 없다.
사용자는 시스템이 멈춘 건지, 동작 중인 건지 알 수 없다.

#### 현재 구조

```
Frontend                Backend
  │                       │
  ├─ POST /wisdom/query ─→│
  │                       ├── classify (즉시)
  │                       ├── collect (0.5-1초)
  │   "분석 중..."        ├── LLM 호출 (1-3초)
  │   (변화 없음)         ├── 파싱 (즉시)
  │←─ 전체 JSON 응답 ────┤
  ├─ 한 번에 렌더링       │
```

#### 해결 방안

2단계 구현:

**Phase A: 단계별 프로그레스 (간단)**
— LLM 호출 전에 "수집 완료" 중간 이벤트를 SSE로 전송

```
Frontend                Backend
  │                       │
  ├─ GET /wisdom/stream ─→│  (SSE EventSource)
  │←─ event: collecting ──┤  "7개 쿼리 수집 중..."
  │←─ event: collected ───┤  "수집 완료: 5개 데이터셋"
  │←─ event: analyzing ───┤  "GPT-4o 분석 중..."
  │←─ event: complete ────┤  전체 WisdomResponse JSON
  ├─ D→I→K→W 렌더링      │
```

**Phase B: 토큰 스트리밍 (고급)**
— OpenAI `stream=True`로 토큰을 실시간 전달 → JSON 파싱은 완료 후

```python
# routers/wisdom.py
from fastapi.responses import StreamingResponse

@router.get("/stream")
async def wisdom_stream(question: str):
    async def event_generator():
        yield f"event: collecting\ndata: 쿼리 수집 시작\n\n"
        collected = collect_data(intent, entity)
        yield f"event: collected\ndata: {len(collected)}개 데이터셋\n\n"

        yield f"event: analyzing\ndata: LLM 분석 중\n\n"
        # stream=True로 OpenAI 호출
        for chunk in openai_stream(...):
            yield f"event: token\ndata: {chunk}\n\n"

        yield f"event: complete\ndata: {full_json}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

```typescript
// Frontend: EventSource
const es = new EventSource(`/api/v1/wisdom/stream?question=${encodeURIComponent(q)}`);
es.addEventListener('collecting', () => setStatus('수집 중...'));
es.addEventListener('collected', (e) => setStatus(`수집 완료: ${e.data}`));
es.addEventListener('analyzing', () => setStatus('LLM 분석 중...'));
es.addEventListener('complete', (e) => {
  const data = JSON.parse(e.data);
  setWisdomData(data);
  es.close();
});
```

#### 변경 파일

| 파일 | 변경 |
|------|------|
| `app/routers/wisdom.py` | SSE 스트림 엔드포인트 추가 |
| `app/query/wisdom_engine.py` | `run_wisdom_query_stream()` 제너레이터 |
| `src/pages/QueryPage.tsx` | EventSource 연결 + 단계별 상태 표시 |
| `src/api/client.ts` | `streamWisdomQuery()` SSE 클라이언트 |

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **중간** | 체감 대기 감소, 하지만 S1 캐시가 있으면 데모 질문은 불필요 |
| 기술 난이도 | **중간** | SSE + EventSource, OpenAI streaming, 에러 핸들링 |
| 현재 병목 | **중간** | 캐시 miss 시에만 발동 (S1이 있으면 비데모 질문에서만) |
| 확장성 | **높음** | 모든 도메인에서 유효 |
| 구현 시간 | Phase A 4시간, Phase B 1일 |

#### 우선순위: **3순위** — S1(캐시) 이후에 하면 비데모 질문에서만 필요

---

### S3. 커스텀 도메인 Cypher 자동 생성

#### 문제

현재 Wisdom Collector의 Cypher 쿼리 13개가 전부 **E-commerce 도메인 하드코딩**이다.
`wisdom_collector.py:18-129` — `Customer`, `Order`, `Product`, `Category` 등 레이블이 고정되어 있다.

병원 ERD, 물류 ERD, 교육 ERD를 올리면 W 모드가 아무 데이터도 수집하지 못한다.

#### 현재 구조

```python
# wisdom_collector.py — 하드코딩
WISDOM_QUERIES = {
    "customer_segments": "MATCH (c:Customer)-[:PLACED]->(o:Order) ...",
    "category_distribution": "MATCH (o:Order)-[:CONTAINS]->(p:Product) ...",
    ...
}
```

#### 해결 방안

DDL 업로드 → 온톨로지 생성 시점에 **온톨로지 메타데이터 기반 Cypher 자동 생성**:

```python
# wisdom_collector.py 개선

def generate_wisdom_queries(ontology: OntologySpec) -> dict[str, str]:
    """온톨로지 구조에서 Wisdom 쿼리 자동 생성."""
    queries = {}

    # 1. 모든 노드 타입별 count + 분포
    for nt in ontology.node_types:
        queries[f"{nt.name}_count"] = f"MATCH (n:{nt.name}) RETURN count(n) AS count"

    # 2. 모든 관계별 집계
    for rel in ontology.relationship_types:
        queries[f"{rel.name}_agg"] = (
            f"MATCH (s:{rel.source_node})-[r:{rel.name}]->(t:{rel.target_node}) "
            f"RETURN count(r) AS count, count(DISTINCT s) AS source_count"
        )

    # 3. 2홉 패턴 자동 탐색 (source→mid→target 체인)
    for r1 in ontology.relationship_types:
        for r2 in ontology.relationship_types:
            if r1.target_node == r2.source_node and r1 != r2:
                queries[f"chain_{r1.name}_{r2.name}"] = (
                    f"MATCH (a:{r1.source_node})-[:{r1.name}]->(b:{r1.target_node})"
                    f"-[:{r2.name}]->(c:{r2.target_node}) "
                    f"RETURN count(*) AS chain_count"
                )

    return queries
```

그리고 KG 빌드 완료 시 생성된 쿼리를 인메모리/PG에 저장:

```python
# kg_builder/service.py — 빌드 완료 후
from app.query.wisdom_collector import generate_wisdom_queries, set_domain_queries
queries = generate_wisdom_queries(ontology)
set_domain_queries(queries)
```

#### 변경 파일

| 파일 | 변경 |
|------|------|
| `app/query/wisdom_collector.py` | `generate_wisdom_queries()` + 동적 쿼리 저장소 |
| `app/kg_builder/service.py` | 빌드 완료 시 쿼리 생성 호출 |
| `app/query/wisdom_engine.py` | 동적 쿼리 우선 사용, 폴백으로 하드코딩 |
| `tests/test_wisdom.py` | 동적 생성 테스트 추가 |

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **높음** | "아무 DDL이나 넣으면 DIKW까지 된다" → 핵심 세일즈 포인트 |
| 기술 난이도 | **중-상** | Cypher 자동 생성 품질 보장이 어려움, 엣지케이스 다수 |
| 현재 병목 | **높음** | E-commerce 외 DDL 데모 시 W 모드 완전 무력화 |
| 확장성 | **최고** | 이 기능 자체가 확장성 문제의 해결 |
| 구현 시간 | 2-3일 |

#### 우선순위: **2순위** — B2B 세일즈에서 "아무 DDL" 시연이 핵심 차별화

#### 구현 전략 — 3단계 점진적 접근

**1단계**: 단순 집계 쿼리만 자동 생성 (노드 count, 관계 count)
— 구현 쉬움, 빈 결과 없이 항상 데이터 수집 가능

**2단계**: 2홉 체인 탐색 + 그룹별 분포
— 온톨로지 관계 그래프에서 체인 자동 탐색

**3단계**: LLM 기반 Cypher 생성 (long-term)
— "이 온톨로지에서 의미 있는 비즈니스 쿼리를 생성해줘"

---

## 중기 과제 (3-4주)

### M1. What-If 시뮬레이션 엔진

#### 문제

현재 W4(What-If) 질문은 LLM이 **추정**으로 답변한다.
`supplier_impact` 쿼리로 영향 범위를 수집하지만, 실제 그래프에서 노드를 제거해보는 것이 아니라
LLM이 "이 공급사가 빠지면 이런 영향이 있을 것입니다"라고 추론할 뿐이다.

```
현재: 데이터 수집 → LLM이 "~할 것입니다" 추정
목표: 데이터 수집 → 그래프에서 실제 제거 시뮬레이션 → 정량적 영향 계산 → LLM이 해석
```

#### 해결 방안

Neo4j 트랜잭션을 **롤백 전제로** 실행하여 실제 영향을 계산:

```python
# app/query/whatif_engine.py

def simulate_node_removal(label: str, name: str) -> dict:
    """노드 제거 시뮬레이션 (읽기 전용, 실제 삭제 안 함)."""
    driver = get_driver()
    with driver.session() as session:
        # 1. 제거 대상 노드의 1-2홉 연결 매핑
        impact = session.run("""
            MATCH (target:{label} {name: $name})
            OPTIONAL MATCH (target)<-[r1]-(n1)
            OPTIONAL MATCH (n1)<-[r2]-(n2) WHERE n2 <> target
            RETURN
                count(DISTINCT n1) AS direct_affected,
                count(DISTINCT n2) AS indirect_affected,
                collect(DISTINCT labels(n1)[0]) AS affected_types,
                collect(DISTINCT type(r1)) AS broken_relationships
        """, name=name)

        # 2. 매출 영향 (수치)
        revenue_impact = session.run("""
            MATCH (s:Supplier {name: $name})<-[:SUPPLIED_BY]-(p:Product)
            <-[:CONTAINS]-(o:Order)
            RETURN sum(toFloat(o.total_amount)) AS at_risk_revenue,
                   count(DISTINCT o) AS at_risk_orders,
                   count(DISTINCT p) AS affected_products
        """, name=name)

        # 3. 대체 가능성 체크
        alternatives = session.run("""
            MATCH (s:Supplier {name: $name})<-[:SUPPLIED_BY]-(p:Product)
            -[:BELONGS_TO]->(cat:Category)
            MATCH (alt_p:Product)-[:BELONGS_TO]->(cat)
            MATCH (alt_p)-[:SUPPLIED_BY]->(alt_s:Supplier)
            WHERE alt_s.name <> $name
            RETURN cat.name AS category,
                   count(DISTINCT alt_s) AS alternative_count,
                   collect(DISTINCT alt_s.name) AS alternatives
        """, name=name)

    return {
        "direct_affected": ...,
        "indirect_affected": ...,
        "at_risk_revenue": ...,
        "alternatives": ...,
        "risk_score": ...  # 0.0 ~ 1.0
    }
```

시뮬레이션 결과를 Wisdom 프롬프트에 추가:

```python
# wisdom_prompts.py
def build_whatif_context(simulation: dict) -> str:
    return (
        f"=== 시뮬레이션 결과 ===\n"
        f"직접 영향 노드: {simulation['direct_affected']}개\n"
        f"간접 영향 노드: {simulation['indirect_affected']}개\n"
        f"위험 매출: {simulation['at_risk_revenue']:,.0f}원\n"
        f"대체 공급사: {simulation['alternatives']}\n"
        f"리스크 점수: {simulation['risk_score']:.1%}\n"
    )
```

#### 변경 파일

| 파일 | 변경 |
|------|------|
| `app/query/whatif_engine.py` | **신규** — 시뮬레이션 엔진 |
| `app/query/wisdom_engine.py` | What-If 의도일 때 시뮬레이션 결과 추가 수집 |
| `app/query/wisdom_prompts.py` | 시뮬레이션 컨텍스트 직렬화 함수 |
| `app/models/schemas.py` | SimulationResult 모델 (optional) |
| `tests/test_wisdom.py` | 시뮬레이션 테스트 추가 |

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **최고** | "공급사 빠지면 매출 23% 위험" — 경영진이 즉시 이해하는 수치 |
| 기술 난이도 | **중간** | Cypher 읽기 전용 쿼리만 사용, 실제 변경 없음 |
| 현재 병목 | **중간** | W4 질문의 신뢰도를 "추정"에서 "계산"으로 격상 |
| 확장성 | **중간** | 시뮬레이션 Cypher는 도메인 종속 → S3(자동 생성)과 연동 필요 |
| 구현 시간 | 3-4일 |

#### 우선순위: **4순위** — 데모에서 WOW 효과가 크지만 S1, S3보다 ROI는 낮음

---

### M2. 멀티턴 Wisdom 대화

#### 문제

현재 W 모드는 **매 질문이 독립적**이다. 사용자가 "좀 더 자세히 알려줘"라고 하면
이전 분석 맥락을 모른 채 처음부터 다시 분석한다.

```
현재:
  Q1: "고객 구매 패턴 분석해줘" → DIKW 응답 (5개 쿼리 수집, GPT-4o)
  Q2: "그 중 VIP 고객에 대해 더 알려줘" → 새로 5개 쿼리 (이전 맥락 없음)

목표:
  Q1: "고객 구매 패턴 분석해줘" → DIKW 응답
  Q2: "그 중 VIP 고객에 대해 더 알려줘" → Q1 맥락 유지 + 추가 엔티티 쿼리
```

#### 해결 방안

**세션 기반 컨텍스트 유지**:

```python
# app/query/wisdom_engine.py

_session_history: dict[str, list[dict]] = {}  # session_id → messages

def run_wisdom_query(question: str, session_id: str | None = None) -> WisdomResponse:
    # 1. 이전 맥락 조회
    prev_messages = _session_history.get(session_id, []) if session_id else []

    # 2. 이전 맥락에서 엔티티 추출 보강
    entity = _extract_entity(question)
    if entity is None and prev_messages:
        # 이전 대화에서 엔티티 재사용
        entity = _extract_entity_from_history(prev_messages)

    # 3. LLM 호출 시 이전 맥락 포함
    messages = prev_messages + build_wisdom_messages(question, intent, collected_text)

    # 4. 히스토리 갱신
    if session_id:
        _session_history[session_id] = messages[-6:]  # 최근 3턴 유지
```

프론트엔드:
```typescript
// QueryPage.tsx — session_id 관리
const [wisdomSessionId] = useState(() => crypto.randomUUID());

const wisdomData = await sendWisdomQuery(question, wisdomSessionId);
```

#### 변경 파일

| 파일 | 변경 |
|------|------|
| `app/query/wisdom_engine.py` | 세션 히스토리 관리 + 엔티티 전파 |
| `app/models/schemas.py` | `WisdomRequest.session_id` 추가 |
| `app/routers/wisdom.py` | session_id 파라미터 전달 |
| `src/api/client.ts` | `sendWisdomQuery(q, sessionId)` |
| `src/pages/QueryPage.tsx` | sessionId 상태 관리 |

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **높음** | "더 자세히" → 드릴다운이 자연스러운 대화 경험 |
| 기술 난이도 | **중간** | 세션 관리 + 컨텍스트 윈도우 조절 |
| 현재 병목 | **낮음** | 데모 5개 질문은 독립적이라 멀티턴 불필요 |
| 확장성 | **높음** | 도메인 무관 |
| 구현 시간 | 2-3일 |

#### 우선순위: **5순위** — UX 개선이지만 데모 시나리오에선 영향 적음

---

### M3. Wisdom → 그래프 연동 (인사이트 하이라이트)

#### 문제

기존에 Phase 0.5에서 A 모드 Q&A → ExplorePage 하이라이트 연동을 구현했다
(`QueryResponse.related_node_ids` → `GraphCanvas`에서 violet 보더).

하지만 W 모드 응답에는 이 연동이 없다.
Wisdom 분석에서 "김민수가 VIP이고 전자기기 카테고리에 집중"이라는 인사이트가 나와도,
그래프에서 해당 노드가 어디인지 시각적으로 확인할 수 없다.

#### 해결 방안

`WisdomResponse`에 `related_node_ids` 필드 추가:

```python
# wisdom_engine.py
def _extract_wisdom_node_ids(intent: str, entity_name: str | None, collected: dict) -> list[str]:
    """Wisdom 분석에서 관련 노드 ID 추출."""
    node_ids = []

    if entity_name:
        # 엔티티 노드 자체
        # Neo4j에서 ID 조회
        ...

    # 수집된 데이터에서 등장하는 엔티티 → 노드 ID로 변환
    for key, records in collected.items():
        for rec in records:
            if "customer" in rec:
                node_ids.append(f"Customer_{rec['customer']}")
            if "product" in rec:
                node_ids.append(f"Product_{rec['product']}")

    return node_ids[:20]  # 최대 20개
```

프론트엔드에서 W 모드 응답 후 "그래프에서 보기" 버튼:

```tsx
// DIKWTimeline.tsx
{data.related_node_ids?.length > 0 && (
  <button onClick={() => navigateToExplore(data.related_node_ids)}>
    그래프에서 보기 ({data.related_node_ids.length}개 노드)
  </button>
)}
```

#### 변경 파일

| 파일 | 변경 |
|------|------|
| `app/models/schemas.py` | `WisdomResponse.related_node_ids` 추가 |
| `app/query/wisdom_engine.py` | 노드 ID 추출 로직 |
| `src/types/ontology.ts` | `WisdomResponse.related_node_ids` 추가 |
| `src/components/wisdom/DIKWTimeline.tsx` | "그래프에서 보기" 버튼 |
| `src/App.tsx` | W 모드 → ExplorePage 네비게이션 + 하이라이트 전달 |

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **높음** | "인사이트의 근거가 그래프에서 보인다" → 신뢰도 상승 |
| 기술 난이도 | **중간** | Phase 0.5 구조를 W 모드에도 확장, 페이지 간 상태 전달 |
| 현재 병목 | **낮음** | 기능 부재이지 시스템 병목은 아님 |
| 확장성 | **높음** | 도메인 무관 (그래프 기반) |
| 구현 시간 | 2일 |

#### 우선순위: **6순위** — 좋은 UX지만 핵심 기능은 아님

---

### M4. DIKW 대시보드

#### 문제

현재 DIKW 분석 결과는 **채팅 버블 안의 타임라인**으로만 표시된다.
경영진이 보고서로 활용하거나, 여러 분석을 비교하기에 적합하지 않다.

#### 해결 방안

새 페이지 `DashboardPage.tsx`:

```
┌─────────────────────────────────────────────┐
│ DIKW 대시보드                    [내보내기]  │
├─────────────────────────────────────────────┤
│ ┌─ 핵심 지표 ─────────────────────────────┐ │
│ │ 고객 5명 │ 주문 12건 │ 매출 ₩34.5M     │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ ┌─ 고객 세그먼트 ──┐ ┌─ 카테고리 분포 ──┐  │
│ │ [파이차트]       │ │ [바차트]         │  │
│ │ VIP 20%         │ │ 전자기기 45%     │  │
│ │ Regular 40%     │ │ 의류 30%        │  │
│ │ Light 40%       │ │ 식품 25%        │  │
│ └─────────────────┘ └─────────────────┘  │
│                                             │
│ ┌─ DIKW 분석 히스토리 ─────────────────────┐│
│ │ W1 패턴분석    high   2,340ms   ▶ 상세  ││
│ │ W4 What-If     medium 3,100ms   ▶ 상세  ││
│ └─────────────────────────────────────────┘│
└─────────────────────────────────────────────┘
```

기술적으로:
- `recharts` 또는 `chart.js` 차트 라이브러리 추가
- `GET /api/v1/graph/stats` 기존 API로 핵심 지표 표시
- Wisdom 분석 히스토리는 프론트엔드 `useState`로 세션 내 관리 (PG 저장은 추후)

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **높음** | 경영진 프레젠테이션용 — "우리 데이터가 이렇게 보입니다" |
| 기술 난이도 | **중간** | 차트 라이브러리 + 새 페이지, 백엔드 변경 적음 |
| 현재 병목 | **낮음** | 없어도 기능적 문제는 없음 |
| 확장성 | **높음** | 차트는 데이터만 넣으면 도메인 무관 |
| 구현 시간 | 3-4일 |

#### 우선순위: **7순위** — 비주얼 임팩트 크지만 핵심 기능 우선

---

## 장기 과제 (1-2개월)

### L1. 도메인 무관 Wisdom (Text-to-Cypher)

#### 문제

S3(커스텀 도메인 Cypher 자동 생성)은 **템플릿 기반**이라
"이 도메인에서 의미 있는 질문"을 사전에 정의해야 한다.
진정한 도메인 무관 Wisdom은 **임의의 질문을 Cypher로 변환**해야 한다.

#### 현재 한계

```
E-commerce DDL → 하드코딩 Cypher 13개 → Wisdom 동작
병원 DDL → ??? → Wisdom 동작 안 함
```

#### 해결 방안: Text-to-Cypher LLM 파이프라인

```
사용자 질문
    │
    ▼
┌─────────────────────────┐
│ 온톨로지 메타데이터 주입  │  노드 타입, 관계 타입, 프로퍼티 스키마
└────────┬────────────────┘
         ▼
┌─────────────────────────┐
│ LLM (GPT-4o)            │  "이 스키마에서 이 질문에 답하는 Cypher를 생성해줘"
│ + Few-shot 예시          │
└────────┬────────────────┘
         ▼
┌─────────────────────────┐
│ Cypher 검증 & 실행       │  문법 검증 → EXPLAIN → 실행 → 결과 수집
└────────┬────────────────┘
         ▼
┌─────────────────────────┐
│ 기존 Wisdom Engine      │  수집된 데이터 → DIKW 분석
└─────────────────────────┘
```

핵심 프롬프트:

```python
TEXT_TO_CYPHER_PROMPT = """
당신은 Neo4j Cypher 쿼리 전문가입니다.

아래 Knowledge Graph 스키마를 참고하여 사용자의 질문에 답하는 Cypher 쿼리를 생성하세요.

## Graph Schema
노드 타입:
{node_types_with_properties}

관계 타입:
{relationship_types}

## 규칙
1. MATCH 패턴만 사용 (CREATE/DELETE/SET 금지)
2. RETURN 절에 의미 있는 alias 사용
3. 집계(count, sum, avg)를 적극 활용
4. LIMIT 20 기본 적용
5. 존재하지 않는 레이블이나 관계 타입 사용 금지

## 출력 형식
```cypher
쿼리
```
설명: 한 줄 설명
"""
```

#### 리스크

- **Cypher 인젝션**: LLM이 `DELETE` 생성 가능 → 읽기 전용 트랜잭션으로 강제
- **잘못된 Cypher**: EXPLAIN으로 사전 검증 + 타임아웃 설정
- **비용**: 질문마다 2회 LLM 호출 (Cypher 생성 + DIKW 분석)
- **정확도**: 복잡한 질문일수록 Cypher 품질 저하

```python
# 안전 장치
def validate_cypher(cypher: str) -> bool:
    """LLM 생성 Cypher의 안전성 검증."""
    forbidden = ["DELETE", "CREATE", "SET ", "REMOVE", "DROP", "MERGE"]
    upper = cypher.upper()
    return not any(f in upper for f in forbidden)

def execute_readonly(cypher: str, params: dict) -> list[dict]:
    """읽기 전용 트랜잭션으로 실행."""
    driver = get_driver()
    with driver.session() as session:
        # Neo4j read transaction — 쓰기 시도 시 자동 실패
        return session.execute_read(lambda tx: [dict(r) for r in tx.run(cypher, **params)])
```

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **최고** | "아무 DDL + 아무 질문 = DIKW" — 제품의 궁극적 비전 |
| 기술 난이도 | **높음** | Text-to-Cypher 정확도, 보안, 비용 관리 |
| 현재 병목 | **높음** | 새 도메인마다 Cypher 수작업이 불가능 |
| 확장성 | **최고** | 이것이 확장성 그 자체 |
| 구현 시간 | 2-3주 |

#### 우선순위: **장기 1순위** — 제품 비전의 핵심이지만, S3 → L1 순서로 점진적 접근

---

### L2. 예측/경고 시스템 (Proactive Wisdom)

#### 문제

현재 시스템은 **사용자가 질문해야만** 인사이트를 제공한다.
사용자가 어떤 질문을 해야 하는지 모르면, 인사이트를 놓친다.

#### 목표

```
현재: 사용자 질문 → 분석 → 인사이트 (Reactive)
목표: 시스템이 자동 분석 → 이상 감지 → 알림 (Proactive)
```

#### 해결 방안

**KG 빌드 완료 후 자동 분석 트리거**:

```python
# app/query/proactive_analyzer.py

PROACTIVE_CHECKS = [
    {
        "name": "supplier_concentration",
        "cypher": """
            MATCH (s:Supplier)<-[:SUPPLIED_BY]-(p:Product)<-[:CONTAINS]-(o:Order)
            WITH s.name AS supplier, count(DISTINCT o) AS orders,
                 sum(toFloat(o.total_amount)) AS revenue
            WITH sum(revenue) AS total_rev, collect({supplier: supplier, revenue: revenue}) AS data
            UNWIND data AS d
            RETURN d.supplier AS supplier,
                   round(d.revenue / total_rev * 100) AS revenue_pct
            ORDER BY revenue_pct DESC
        """,
        "alert_condition": lambda records: any(r["revenue_pct"] > 50 for r in records),
        "alert_message": "공급사 집중도 경고: {supplier}가 매출의 {revenue_pct}%를 차지합니다",
    },
    {
        "name": "low_review_high_sales",
        "cypher": "...",
        "alert_condition": lambda records: ...,
        "alert_message": "리뷰 품질 경고: ...",
    },
]

def run_proactive_analysis() -> list[Alert]:
    alerts = []
    for check in PROACTIVE_CHECKS:
        records = execute_readonly(check["cypher"])
        if check["alert_condition"](records):
            alerts.append(Alert(
                type=check["name"],
                message=check["alert_message"].format(**records[0]),
                severity="warning",
                data=records,
            ))
    return alerts
```

**프론트엔드 알림 배너**:

```tsx
// QueryPage.tsx — 자동 인사이트
useEffect(() => {
  fetchAlerts().then(alerts => {
    if (alerts.length > 0) setProactiveAlerts(alerts);
  });
}, []);

{proactiveAlerts.map(alert => (
  <div className="border-l-4 border-amber-500 bg-amber-50 p-3">
    <p className="text-sm font-medium">{alert.message}</p>
    <button onClick={() => handleSend(alert.suggested_query)}>
      자세히 분석하기
    </button>
  </div>
))}
```

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **최고** | "시스템이 알아서 위험을 알려준다" — Wisdom의 진정한 가치 |
| 기술 난이도 | **중-상** | 분석 규칙 설계 + 알림 UX + 오탐 관리 |
| 현재 병목 | **낮음** | 현재는 없는 기능이라 병목이 아님 |
| 확장성 | **중간** | 분석 규칙이 도메인 종속 → L1(Text-to-Cypher)과 연동 필요 |
| 구현 시간 | 1-2주 |

#### 우선순위: **장기 2순위**

---

### L3. A/B/W 자동 비교

#### 문제

같은 질문에 대해 A/B/W 3개 모드가 각각 어떤 답변을 하는지 비교하기 어렵다.
사용자가 모드를 바꿔가며 같은 질문을 3번 해야 한다.

#### 해결 방안

```
[비교 모드] 버튼 클릭 → 3개 모드 동시 실행 → 3열 비교 표시

┌─────────────┬─────────────┬─────────────────────┐
│ A 템플릿     │ B 로컬서치   │ W 위즈덤             │
├─────────────┼─────────────┼─────────────────────┤
│ 주문 상품:   │ 김민수 고객은 │ [D] 주문 12건...     │
│ 맥북프로,    │ 전자기기...   │ [I] 고객→주문→상품   │
│ 에어팟프로   │             │ [K] VIP 패턴...      │
│             │             │ [W] 리텐션 추천...    │
├─────────────┼─────────────┼─────────────────────┤
│ 12ms        │ 2,340ms     │ 3,100ms             │
│ 0 tokens    │ 1,200 tok   │ 2,800 tok           │
│ cached      │ GPT-4o      │ GPT-4o              │
└─────────────┴─────────────┴─────────────────────┘
```

백엔드:
```python
# routers/query.py
@router.post("/compare")
async def compare_query(req: QueryRequest) -> dict:
    a_result = run_query(req.question, "a")
    b_result = run_query(req.question, "b")
    w_result = run_wisdom_query(req.question)
    return {"a": a_result, "b": b_result, "w": w_result}
```

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **높음** | "같은 데이터를 3가지 관점으로" — 데모에서 강력한 시각적 효과 |
| 기술 난이도 | **낮음** | 기존 API 3개 호출 + 프론트엔드 3열 레이아웃 |
| 현재 병목 | **낮음** | 기능 부재, 병목 아님 |
| 확장성 | **높음** | 도메인 무관 |
| 구현 시간 | 2-3일 |

#### 우선순위: **장기 3순위** — 데모 임팩트는 크지만 핵심 기능은 아님

---

### L4. Wisdom Report 내보내기

#### 문제

DIKW 분석 결과를 **팀과 공유하거나 보고서로 저장**할 수 없다.
데모에서 "이걸 우리 팀에 보여주고 싶은데"라는 요청에 대응 불가.

#### 해결 방안

- **PDF**: `jspdf` + `html2canvas`로 DIKWTimeline 컴포넌트 캡처
- **Markdown**: WisdomResponse → Markdown 템플릿 변환
- **Clipboard**: JSON 또는 요약 텍스트 복사

```typescript
// DIKWTimeline.tsx
function exportToMarkdown(data: WisdomResponse): string {
  let md = `# DIKW 분석: ${data.question}\n\n`;
  md += `> ${data.summary}\n\n`;
  for (const layer of data.dikw_layers) {
    md += `## ${layer.title} (${layer.level.toUpperCase()})\n`;
    md += `${layer.content}\n\n`;
    if (layer.evidence.length > 0) {
      md += `**근거:**\n`;
      layer.evidence.forEach(e => md += `- ${e}\n`);
    }
    md += '\n';
  }
  if (data.action_items.length > 0) {
    md += `## 권장 행동\n`;
    data.action_items.forEach(a => md += `- ${a}\n`);
  }
  return md;
}
```

#### 임팩트 분석

| 축 | 점수 | 근거 |
|---|------|------|
| 고객 임팩트 | **중간** | 공유 기능이지 핵심 기능은 아님 |
| 기술 난이도 | **낮음** | 프론트엔드만 변경 |
| 현재 병목 | **낮음** | 없어도 스크린샷으로 대체 가능 |
| 확장성 | **높음** | 도메인 무관 |
| 구현 시간 | 반나절 |

#### 우선순위: **장기 4순위** — 금방 되지만 우선순위 낮음

---

## 종합 우선순위 로드맵

### Phase 1: 데모 완성도 (1주)

| 순위 | 과제 | 핵심 가치 | 예상 |
|------|------|-----------|------|
| **1** | S1 Wisdom 캐시 | W 모드 데모 즉시 응답 | 2-3시간 |
| **2** | S3 커스텀 도메인 Cypher (1단계) | 비E-commerce DDL 지원 | 1일 |

### Phase 2: 차별화 기능 (2주)

| 순위 | 과제 | 핵심 가치 | 예상 |
|------|------|-----------|------|
| **3** | S2 SSE 스트리밍 (Phase A) | 비캐시 질문 UX 개선 | 4시간 |
| **4** | M1 What-If 시뮬레이션 | W4 정량화 → WOW 효과 | 3-4일 |
| **5** | M2 멀티턴 대화 | 자연스러운 드릴다운 | 2-3일 |

### Phase 3: 제품 비전 (1-2개월)

| 순위 | 과제 | 핵심 가치 | 예상 |
|------|------|-----------|------|
| **6** | M3 Wisdom→그래프 연동 | 인사이트의 시각적 근거 | 2일 |
| **7** | M4 DIKW 대시보드 | 경영진 프레젠테이션 | 3-4일 |
| **8** | L1 Text-to-Cypher | 아무 DDL + 아무 질문 | 2-3주 |
| **9** | L2 Proactive Wisdom | 자동 경고 | 1-2주 |
| **10** | L3 A/B/W 비교 | 3관점 비교 데모 | 2-3일 |

### 의존성 그래프

```
S1 (캐시) ─────────────────── 독립
S3 (도메인 Cypher) ──────────→ L1 (Text-to-Cypher)의 stepping stone
S2 (SSE) ──────────────────── 독립 (S1 이후 효과 감소)
M1 (What-If) ────────────────→ S3에 의존 (비E-commerce에서도 동작하려면)
M2 (멀티턴) ─────────────────── 독립
M3 (그래프 연동) ──────────── Phase 0.5 구조 확장
M4 (대시보드) ──────────────── 독립 (차트 라이브러리 추가)
L1 (Text-to-Cypher) ─────────→ S3의 자연스러운 진화
L2 (Proactive) ──────────────→ L1에 의존 (도메인 무관 분석 규칙)
L3 (A/B/W 비교) ─────────────── 독립
```

### 핵심 판단

**지금 당장 해야 하는 것**: S1 (Wisdom 캐시)
— 2-3시간 투자로 W 모드 데모 경험이 극적으로 개선된다.

**다음으로 해야 하는 것**: S3 (커스텀 도메인 Cypher)
— "아무 DDL을 넣어도 DIKW까지 된다"는 B2B 세일즈의 킬러 포인트.
— L1(Text-to-Cypher)의 첫 번째 단계로, 점진적 발전 경로가 명확하다.

**데모 WOW 효과가 가장 큰 것**: M1 (What-If 시뮬레이션)
— "애플코리아 빠지면 매출 23% 위험, 대체 공급사 2곳 존재"
— 이 한 문장이 경영진의 구매 결정을 이끈다.
