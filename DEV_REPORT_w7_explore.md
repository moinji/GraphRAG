# GraphRAG - 인터랙티브 Knowledge Graph 시각화 구현 계획

## Context
Neo4j에 구축된 KG를 시각적으로 탐색할 수 있는 기능이 없음. WEF Strategic Intelligence의 Transformation Map처럼 노드-관계를 인터랙티브 그래프로 보여주는 ExplorePage를 추가한다.

## 라이브러리 선정: Cytoscape.js

| 기준 | Cytoscape.js | D3.js | React Flow |
|------|-------------|-------|------------|
| 대규모 그래프 (1000+) | Canvas 기반, 우수 | SVG, 500+ 성능 저하 | DOM 기반, 200 이하 적합 |
| 레이아웃 | 15+ 내장 (COSE 등) | force만 기본 | tree 계열만 |
| React 연동 | react-cytoscapejs | 수동 useRef 필요 | 네이티브 |
| 용도 | KG/생물학 그래프 전용 | 범용 | 워크플로우/다이어그램 |

**선택 이유:** KG 시각화에 특화, Canvas 렌더링으로 대규모 그래프 처리 가능, COSE 레이아웃이 온톨로지 기반 그래프에 최적.

```bash
npm install cytoscape react-cytoscapejs
npm install -D @types/cytoscape @types/react-cytoscapejs
```

---

## 구현 단계

### Step 1: Backend - Pydantic 모델 추가
**파일:** `backend/app/models/schemas.py` (수정, line 246 이후 추가)

`QueryResponse` 아래에 추가:
- `GraphNode(id, label, properties, display_name)`
- `GraphEdge(id, source, target, rel_type, properties)`
- `GraphData(nodes, edges, total_nodes, total_edges, truncated)`
- `GraphStats(node_counts, edge_counts, total_nodes, total_edges)`

### Step 2: Backend - Graph API 라우터 생성
**파일:** `backend/app/routers/graph.py` (신규)

3개 엔드포인트:
- `GET /api/v1/graph/stats` → 노드/엣지 타입별 카운트
- `GET /api/v1/graph/full?limit=500` → 전체 그래프 데이터 (제한 포함)
- `GET /api/v1/graph/neighbors/{node_id}?depth=1` → 특정 노드 주변 탐색

**중요:** 노드 ID 충돌 방지를 위해 `{label}_{id}` 형식 사용 (예: `Customer_1`, `Order_1`). Neo4j 쿼리는 `n.id` (application property) 사용. 기존 `loader.py`의 `_wait_for_neo4j` 패턴과 `GraphDatabase.driver()` 사용 방식 참고.

### Step 3: Backend - 라우터 등록
**파일:** `backend/app/main.py` (수정)
- import에 `graph` 추가
- `application.include_router(graph.router)` 추가

### Step 4: Frontend - TypeScript 타입 생성
**파일:** `frontend/src/types/graph.ts` (신규)
- `GraphNode`, `GraphEdge`, `GraphData`, `GraphStats` 인터페이스

### Step 5: Frontend - API 클라이언트 확장
**파일:** `frontend/src/api/client.ts` (수정, 기존 `sendQuery` 함수 아래에 추가)
- `fetchGraphStats()`, `fetchGraph(limit)`, `fetchNeighbors(nodeId, depth)` 추가
- 기존 `request<T>()` 헬퍼 재사용

### Step 6: Frontend - npm 패키지 설치
```bash
cd frontend && npm install cytoscape react-cytoscapejs && npm install -D @types/cytoscape @types/react-cytoscapejs
```

### Step 7: Frontend - 그래프 컴포넌트 생성
모두 `frontend/src/components/graph/` 하위:

| 파일 | 역할 |
|------|------|
| `graph-styles.ts` | 노드 타입별 색상 맵 (Customer=indigo, Product=emerald 등), Cytoscape 스타일시트 빌더 |
| `graph-layouts.ts` | COSE(기본)/Concentric/Grid 레이아웃 프리셋 |
| `use-graph-data.ts` | 커스텀 훅: fetchGraph + elements 변환 + 필터/선택 상태 (기존 패턴: useState 로컬 상태) |
| `GraphCanvas.tsx` | react-cytoscapejs 래퍼, 노드 tap/배경 tap 이벤트 핸들링 |
| `GraphToolbar.tsx` | 검색 input, 레이아웃 드롭다운, 줌 버튼 (기존 `@/components/ui/` 재사용) |
| `NodeDetailPanel.tsx` | 우측 슬라이드 패널: 속성 key-value + 연결 노드 목록 (클릭 시 탐색) |
| `GraphFilterSidebar.tsx` | 좌측 패널: 노드/엣지 타입별 Checkbox 필터 + 카운트 표시 |

### Step 8: Frontend - ExplorePage 생성
**파일:** `frontend/src/pages/ExplorePage.tsx` (신규)

```
┌─ GraphToolbar (검색 | 레이아웃 | 줌) ─────────────────┐
├─ FilterSidebar │ GraphCanvas (Cytoscape) │ DetailPanel ─┤
│  [체크박스]     │  [인터랙티브 그래프]     │  [노드 정보] │
└────────────────┴──────────────────────────┴─────────────┘
```

### Step 9: Frontend - App.tsx 라우팅 통합
**파일:** `frontend/src/App.tsx` (수정)
- `Page` 타입에 `'explore'` 추가
- `ExplorePage` import + 렌더링 블록 추가
- 헤더에 "Explore Graph" 네비게이션 버튼 추가

---

## 인터랙션 설계

- **노드 클릭** → 우측 DetailPanel 열림 (속성, 연결 노드)
- **노드 Expand 버튼** → `fetchNeighbors`로 주변 노드 추가 로드
- **배경 클릭** → DetailPanel 닫힘
- **검색** → 클라이언트사이드 필터링 (debounce 300ms), 매칭 노드로 줌+센터링
- **타입 필터** → 체크 해제한 타입의 노드/엣지 제거
- **레이아웃 전환** → COSE(기본), Concentric, Grid 드롭다운

## 성능 전략
- 서버사이드 limit (기본 500 노드)
- Canvas 렌더링 (DOM 아님)
- 줌아웃 시 라벨 숨김 (`min-zoomed-font-size`)
- Lazy expansion (클릭 시 주변 노드 로드)
- 타입 필터로 불필요한 노드 제거

---

## 파일 요약

| # | 파일 | 작업 | 상태 |
|---|------|------|------|
| 1 | `backend/app/models/schemas.py` | 수정 - 4개 모델 추가 | ✅ 완료 |
| 2 | `backend/app/routers/graph.py` | 신규 - 3개 API 엔드포인트 | ✅ 완료 |
| 3 | `backend/app/main.py` | 수정 - 라우터 등록 | ✅ 완료 |
| 4 | `frontend/src/types/graph.ts` | 신규 - TS 타입 | ✅ 완료 |
| 5 | `frontend/src/api/client.ts` | 수정 - 3개 API 함수 | ✅ 완료 |
| 6 | `frontend/src/components/graph/graph-styles.ts` | 신규 | ✅ 완료 |
| 7 | `frontend/src/components/graph/graph-layouts.ts` | 신규 | ✅ 완료 |
| 8 | `frontend/src/components/graph/use-graph-data.ts` | 신규 | ✅ 완료 |
| 9 | `frontend/src/components/graph/GraphCanvas.tsx` | 신규 | ✅ 완료 |
| 10 | `frontend/src/components/graph/GraphToolbar.tsx` | 신규 | ✅ 완료 |
| 11 | `frontend/src/components/graph/NodeDetailPanel.tsx` | 신규 | ✅ 완료 |
| 12 | `frontend/src/components/graph/GraphFilterSidebar.tsx` | 신규 | ✅ 완료 |
| 13 | `frontend/src/pages/ExplorePage.tsx` | 신규 | ✅ 완료 |
| 14 | `frontend/src/App.tsx` | 수정 - 라우팅 | ✅ 완료 |

## 빌드 검증
- `npx tsc --noEmit` → 에러 0개
- `npx vite build` → 빌드 성공

## 검증 방법
1. `docker compose up --build` 후 `http://localhost/api/v1/graph/stats` 확인
2. `http://localhost/api/v1/graph/full` 에서 노드/엣지 JSON 확인
3. `http://localhost` 접속 → DDL 업로드 → KG 빌드 → Explore 페이지 진입
4. 노드 클릭 → 상세 패널 표시 확인
5. 필터/검색/레이아웃 전환 동작 확인
