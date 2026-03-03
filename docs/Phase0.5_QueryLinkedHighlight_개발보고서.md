# Phase 0.5: Query-Linked Highlight 개발보고서

> **작성일**: 2026-03-03
> **Phase**: 0.5 (MVP 이후 첫 UX 개선)
> **근거 문서**: `docs/KG_UX_비교분석_보고서.md` — 최우선 개선 사항 "질문하면 그래프가 반응한다"

---

## 1. 개요

### 1.1 배경

기존 시스템에서 QueryPage(채팅)와 ExplorePage(그래프 탐색)가 완전히 분리되어 있어,
사용자가 질문한 결과가 그래프 시각화에 반영되지 않았다.
KG UX 비교분석 보고서에서 도출된 최우선 개선 사항으로,
**"질문 → 관련 노드 하이라이트"** 연동을 최소 기능으로 구현한다.

### 1.2 목표

- ExplorePage 툴바에 **데모 질문 드롭다운** 추가
- 질문 결과의 **관련 노드를 그래프에서 시각적으로 하이라이트** (violet 보더)
- 하이라이트 노드 영역으로 **자동 줌인**
- 답변을 **배너로 표시** + Clear 버튼으로 초기화
- 백엔드 API 응답에 `related_node_ids` 필드 추가 (하위 호환)

---

## 2. 변경 파일 요약

| # | 파일 | 레이어 | 변경 내용 | 추가 라인 |
|---|------|--------|-----------|-----------|
| 1 | `backend/app/models/schemas.py` | 스키마 | `QueryResponse`에 `related_node_ids` 필드 추가 | +1 |
| 2 | `backend/app/query/demo_cache.py` | 캐시 | 5개 캐시 엔트리에 시드 데이터 기반 node ID 하드코딩 | +5 |
| 3 | `backend/app/query/pipeline.py` | 파이프라인 | `_extract_related_node_ids()`, `_batch_resolve_node_ids()` 함수 추가 | +95 |
| 4 | `frontend/src/types/ontology.ts` | TS 타입 | `QueryResponse`에 `related_node_ids` 추가 | +1 |
| 5 | `frontend/src/components/graph/use-graph-data.ts` | 훅 | `highlightNodeIds` 상태 + setter 추가 | +5 |
| 6 | `frontend/src/components/graph/GraphCanvas.tsx` | 캔버스 | `query-highlight` useEffect + violet 스타일 | +37 |
| 7 | `frontend/src/components/graph/GraphToolbar.tsx` | 툴바 | 데모 질문 드롭다운 Select 컴포넌트 | +31 |
| 8 | `frontend/src/pages/ExplorePage.tsx` | 페이지 | sendQuery 연동, 하이라이트/배너 통합 | +46 |

**총 변경**: 8개 파일, **+221 라인** (Phase 0.5 관련)

---

## 3. 상세 구현

### 3.1 백엔드: 스키마 확장

**`backend/app/models/schemas.py`** (line 207)

```python
class QueryResponse(BaseModel):
    ...
    cached: bool = False
    related_node_ids: list[str] = []   # NEW
```

- 기본값 `[]`이므로 기존 API 호환성 100% 유지
- 프론트엔드가 필드를 사용하지 않아도 에러 없음

### 3.2 백엔드: 데모 캐시 하드코딩

**`backend/app/query/demo_cache.py`**

시드 데이터 기반으로 각 질문에 대응하는 노드 ID를 확정 배정:

| 질문 | related_node_ids |
|------|------------------|
| Q1: 고객 김민수가 주문한 상품은? | `Customer_1`, `Product_1`, `Product_2`, `Product_3` |
| Q2: 카테고리 리뷰 평점 Top 3 | `Customer_1`, `Product_7`, `Product_2`, `Product_6`, `Category_4`, `Category_5`, `Category_6` |
| Q3: 가장 많이 팔린 카테고리 Top 3 | `Category_4`, `Category_5`, `Category_6` |
| Q4: 김민수와 이영희 공통 구매 | `Customer_1`, `Customer_2`, `Product_1` |
| Q5: 쿠폰 사용/미사용 비교 | `[]` (집계 쿼리, 특정 노드 없음) |

데모 캐시 히트 시 Neo4j 쿼리 없이 즉시 반환되므로 지연 시간 0ms.

### 3.3 백엔드: 동적 노드 ID 추출 (비-캐시 경로)

**`backend/app/query/pipeline.py`** — 2개 함수 추가

#### `_extract_related_node_ids(records, template_id, slots, params)`

템플릿별로 쿼리 결과 레코드에서 엔티티 이름을 추출하여 `(label, prop, values)` 룩업 튜플 구성:

```
two_hop     → start_label 앵커 + end_label 결과
custom_q2   → Customer 앵커 + Product + Category 결과
agg_with_rel → end_label(Category) 결과
custom_q4   → Customer 2명 + Product 결과
custom_q5   → 빈 리스트 (집계)
```

#### `_batch_resolve_node_ids(lookups)`

Neo4j에 label별 배치 쿼리를 실행하여 이름 → 복합 ID(`{Label}_{nid}`) 변환:

```cypher
MATCH (n:{label}) WHERE n.{prop} IN $vals RETURN n.id AS nid
```

- 중복 제거 후 리스트 반환
- 예외 발생 시 빈 리스트 반환 (graceful degradation)

#### `run_query()` 통합

```python
# 6. Extract related node IDs for graph highlighting
related_node_ids = _extract_related_node_ids(records, template_id, slots, params)

return QueryResponse(
    ...
    related_node_ids=related_node_ids,
)
```

### 3.4 프론트엔드: 타입 동기화

**`frontend/src/types/ontology.ts`** (line 172)

```typescript
export interface QueryResponse {
  ...
  cached: boolean;
  related_node_ids: string[];  // NEW
}
```

### 3.5 프론트엔드: 그래프 데이터 훅 확장

**`frontend/src/components/graph/use-graph-data.ts`**

```typescript
// 인터페이스 추가
highlightNodeIds: Set<string>;
setHighlightNodeIds: (ids: Set<string>) => void;

// 훅 내부 상태
const [highlightNodeIds, setHighlightNodeIds] = useState<Set<string>>(new Set());
```

- 기존 `matchedNodeIds`(검색)와 독립적인 별도 상태
- ExplorePage에서 직접 제어

### 3.6 프론트엔드: 그래프 캔버스 하이라이트 렌더링

**`frontend/src/components/graph/GraphCanvas.tsx`**

#### Props 확장

```typescript
interface GraphCanvasProps {
  ...
  highlightNodeIds: Set<string>;  // NEW
}
```

#### useEffect — 하이라이트 적용 + 자동 줌

```typescript
useEffect(() => {
  const cy = cyRef.current;
  if (!cy) return;

  cy.nodes().removeClass('query-highlight');
  if (highlightNodeIds.size > 0) {
    for (const id of highlightNodeIds) {
      const node = cy.getElementById(id);
      if (node.length > 0) node.addClass('query-highlight');
    }
    const highlighted = cy.nodes('.query-highlight');
    if (highlighted.length > 0) {
      cy.animate(
        { fit: { eles: highlighted, padding: 60 } },
        { duration: 500 },
      );
    }
  }
}, [highlightNodeIds, cyRef]);
```

- 캔버스에 로드되지 않은 노드는 `getElementById` 결과가 빈 컬렉션이므로 자동 skip
- 하이라이트된 노드 전체 영역에 padding 60px로 fit 줌

#### Cytoscape 스타일

```typescript
{
  selector: 'node.query-highlight',
  style: {
    'border-width': 4,
    'border-color': '#8b5cf6',    // violet-500
    'overlay-color': '#8b5cf6',
    'overlay-opacity': 0.2,
    width: 48,                     // search-match(44)보다 약간 큼
    height: 48,
  },
}
```

기존 `search-match`(yellow, 44px)와 시각적으로 구분되는 violet 스타일.

### 3.7 프론트엔드: 툴바 데모 질문 드롭다운

**`frontend/src/components/graph/GraphToolbar.tsx`**

```typescript
const DEMO_QUESTIONS = [
  { label: 'Q1', text: '고객 김민수가 주문한 상품은?' },
  { label: 'Q2', text: '김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?' },
  { label: 'Q3', text: '가장 많이 팔린 카테고리 Top 3는?' },
  { label: 'Q4', text: '김민수와 이영희가 공통으로 구매한 상품은?' },
  { label: 'Q5', text: '쿠폰 사용 주문과 미사용 주문의 평균 금액 비교' },
];
```

- QueryPage와 동일한 5개 데모 질문
- Props: `onDemoQuestion?: (question: string) => void`, `demoQueryLoading?: boolean` (optional이므로 하위 호환)
- Search 입력 필드와 Layout 선택기 사이에 배치
- 로딩 중 `disabled` + placeholder 변경

### 3.8 프론트엔드: ExplorePage 통합

**`frontend/src/pages/ExplorePage.tsx`**

#### 신규 상태

```typescript
const [demoQueryLoading, setDemoQueryLoading] = useState(false);
const [demoAnswer, setDemoAnswer] = useState<string | null>(null);
```

#### handleDemoQuestion 콜백

```typescript
const handleDemoQuestion = useCallback(async (question: string) => {
  setDemoQueryLoading(true);
  setHighlightNodeIds(new Set());     // 기존 하이라이트 초기화
  setDemoAnswer(null);
  try {
    const res = await sendQuery(question, 'a');
    setDemoAnswer(res.answer);
    if (res.related_node_ids?.length > 0) {
      setHighlightNodeIds(new Set(res.related_node_ids));
    }
  } catch {
    setDemoAnswer('Query failed. Please try again.');
  } finally {
    setDemoQueryLoading(false);
  }
}, [setHighlightNodeIds]);
```

#### 답변 배너 UI

```tsx
{demoAnswer && (
  <div className="flex items-center gap-3 border-b bg-violet-50 px-4 py-2 text-sm">
    <span className="flex-1 text-violet-900">{demoAnswer}</span>
    <button onClick={handleClearDemo}
      className="text-violet-600 hover:text-violet-800 font-medium">
      Clear
    </button>
  </div>
)}
```

- 툴바 바로 아래, 그래프 영역 위에 위치
- violet-50 배경으로 하이라이트 색상과 통일감
- Clear 버튼 클릭 시 하이라이트 + 배너 모두 제거

---

## 4. 데이터 흐름도

```
[사용자] 드롭다운에서 Q1 선택
    │
    ▼
[ExplorePage] handleDemoQuestion("고객 김민수가 주문한 상품은?")
    │
    ▼
[sendQuery] POST /api/v1/query { question, mode: "a" }
    │
    ▼
[Backend pipeline.run_query]
    ├─ demo_cache 히트 → cached=True, related_node_ids 포함 즉시 반환
    └─ 캐시 미스 → route → slot fill → execute → _extract_related_node_ids
                                                      → _batch_resolve_node_ids (Neo4j)
    │
    ▼
[QueryResponse] { answer: "...", related_node_ids: ["Customer_1", "Product_1", ...] }
    │
    ▼
[ExplorePage]
    ├─ setDemoAnswer(res.answer)        → 답변 배너 렌더링
    └─ setHighlightNodeIds(new Set(...)) → GraphCanvas로 전파
         │
         ▼
    [GraphCanvas useEffect]
         ├─ cy.nodes().removeClass('query-highlight')
         ├─ 각 노드에 addClass('query-highlight') → violet 보더
         └─ cy.animate({ fit }) → 하이라이트 영역 자동 줌인
```

---

## 5. 엣지 케이스 처리

| 케이스 | 처리 방식 |
|--------|-----------|
| 노드가 캔버스에 로드되지 않은 경우 | `cy.getElementById(id).length === 0`이면 skip, 크래시 없음 |
| 집계 쿼리 (Q5) | `related_node_ids: []` → 하이라이트 없음, 답변 배너만 표시 |
| 다른 질문 선택 시 | `handleDemoQuestion` 시작 시 기존 하이라이트/답변 초기화 |
| mode "b" (local search) | Phase 0.5에서는 mode "a"만 사용, "b"는 기본값 `[]` 반환 |
| Neo4j 연결 실패 (비-캐시 경로) | `_batch_resolve_node_ids`가 예외 catch → 빈 리스트 반환 |
| API 호출 실패 | `catch` 블록에서 에러 메시지 답변으로 표시 |

---

## 6. 하위 호환성

| 항목 | 호환 방식 |
|------|-----------|
| `QueryResponse.related_node_ids` | 기본값 `[]`이므로 기존 응답 구조 유지 |
| `GraphToolbar` props | `onDemoQuestion`, `demoQueryLoading` 모두 optional (`?`) |
| `GraphCanvas` props | `highlightNodeIds`는 필수이나, ExplorePage가 유일한 소비자 |
| 기존 검색 하이라이트 | `search-match` 클래스와 `query-highlight` 클래스가 독립적으로 동작 |

---

## 7. 검증 절차

```bash
# 1. 전체 스택 실행
docker compose up --build

# 2. DDL 업로드 → 온톨로지 승인 → KG 빌드 완료

# 3. Explore 페이지 진입

# 4. 백엔드 단독 테스트
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question":"고객 김민수가 주문한 상품은?","mode":"a"}'
# → 응답에 "related_node_ids": ["Customer_1", "Product_1", "Product_2", "Product_3"] 확인
```

### UI 검증 체크리스트

- [ ] Q1 선택 → 답변 배너에 "김민수 고객이 주문한 상품: 맥북프로, 에어팟프로, 갤럭시탭" 표시
- [ ] Customer_1, Product_1, Product_2, Product_3 노드에 violet 하이라이트
- [ ] 하이라이트된 노드 영역으로 자동 줌인 (500ms 애니메이션)
- [ ] Q3 선택 → Category 노드 3개 하이라이트, 이전 하이라이트 초기화
- [ ] Q5 선택 → 하이라이트 없음, 답변만 표시
- [ ] Clear 버튼 → 하이라이트 + 배너 모두 제거
- [ ] 검색 하이라이트(yellow)와 질문 하이라이트(violet) 독립 동작

---

## 8. 향후 확장 (Phase 1+)

| 항목 | 설명 |
|------|------|
| 자유 질문 입력 | 드롭다운 대신 텍스트 입력 → mode "a" 파이프라인 실행 |
| mode "b" 연동 | Local Search 결과의 subgraph_context에서 node ID 추출 |
| 경로 시각화 | `paths` 필드의 엣지 경로를 그래프 위에 오버레이 |
| 노드 미로드 시 자동 확장 | `related_node_ids` 중 캔버스에 없는 노드를 `expandNode`로 로드 |
| 질문 히스토리 | 이전 질문/답변 목록을 사이드바에 표시 |
