# Week 7 개발 보고서 — 인터랙티브 Knowledge Graph 시각화 (Explore Page)
> 작성일: 2026-03-02 | 목적: Neo4j KG를 인터랙티브 그래프로 탐색하는 Explore 페이지 추가

---

## 1. 요약

Neo4j에 구축된 Knowledge Graph를 **시각적으로 탐색**할 수 있는 Explore 페이지를 추가했습니다. WEF Strategic Intelligence의 Transformation Map처럼 노드-관계를 **인터랙티브 그래프**로 시각화하며, 노드 클릭 → 상세 패널, 필터링, 검색, 레이아웃 전환, 이웃 확장 등의 기능을 제공합니다.

| 지표 | 목표 | 실제 | 상태 |
|------|------|------|------|
| Backend Graph API 3개 엔드포인트 | 동작 | 동작 | PASS |
| `GET /graph/stats` → 노드/엣지 카운트 | JSON 응답 | 60 nodes, 97 edges | PASS |
| `GET /graph/full?limit=500` → 그래프 데이터 | JSON 응답 | 노드+엣지 정상 | PASS |
| `GET /graph/neighbors/Customer_1` → 이웃 탐색 | JSON 응답 | 김민수 주변 노드 반환 | PASS |
| 프론트엔드 TypeScript 빌드 (`tsc --noEmit`) | 에러 0 | 에러 0 | PASS |
| 프론트엔드 Vite 빌드 (`vite build`) | 성공 | 성공 | PASS |
| Docker 전체 빌드 (`docker compose up --build`) | 5개 컨테이너 기동 | 5개 Running | PASS |
| "Explore Graph" 버튼 번들 포함 | 포함 | 포함 확인 | PASS |
| nginx 프록시 (port 80) API 전달 | 정상 | 정상 | PASS |

---

## 2. 라이브러리 선정: Cytoscape.js

| 기준 | Cytoscape.js | D3.js | React Flow |
|------|-------------|-------|------------|
| 대규모 그래프 (1000+) | **Canvas 기반, 우수** | SVG, 500+ 성능 저하 | DOM 기반, 200 이하 적합 |
| 레이아웃 | **15+ 내장 (COSE 등)** | force만 기본 | tree 계열만 |
| React 연동 | react-cytoscapejs | 수동 useRef 필요 | 네이티브 |
| 용도 | **KG/생물학 그래프 전용** | 범용 | 워크플로우/다이어그램 |

**선택 이유:** KG 시각화에 특화, Canvas 렌더링으로 대규모 그래프 처리 가능, COSE 레이아웃이 온톨로지 기반 그래프에 최적.

설치 패키지:
```bash
npm install cytoscape react-cytoscapejs
npm install -D @types/cytoscape @types/react-cytoscapejs
```

---

## 3. 구현 범위

### 백엔드 신규 파일 (1개)

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `app/routers/graph.py` | 185 | Graph Visualization API — stats, full, neighbors 3개 엔드포인트 |

### 백엔드 수정 파일 (2개)

| 파일 | 변경 내용 |
|------|----------|
| `app/models/schemas.py` | `GraphNode`, `GraphEdge`, `GraphData`, `GraphStats` 4개 모델 추가 (+29행) |
| `app/main.py` | `graph` 라우터 import + 등록 (+2행) |

### 프론트엔드 신규 파일 (8개)

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `src/types/graph.ts` | 34 | TS 인터페이스 (GraphNode, GraphEdge, GraphData, GraphStats) |
| `src/components/graph/graph-styles.ts` | 99 | 노드 타입별 색상 맵 (12색) + Cytoscape 스타일시트 빌더 |
| `src/components/graph/graph-layouts.ts` | 37 | COSE / Concentric / Grid 레이아웃 프리셋 |
| `src/components/graph/use-graph-data.ts` | 176 | 커스텀 훅: fetch + Cytoscape elements 변환 + 필터/검색/확장 상태 |
| `src/components/graph/GraphCanvas.tsx` | 121 | react-cytoscapejs 래퍼: tap 이벤트, 레이아웃 전환, 검색 하이라이트 |
| `src/components/graph/GraphToolbar.tsx` | 98 | 검색 input (debounce 300ms) + 레이아웃 드롭다운 + 줌 버튼 + 통계 배지 |
| `src/components/graph/NodeDetailPanel.tsx` | 107 | 우측 슬라이드 패널: 속성 key-value + 연결 노드 목록 (클릭 시 탐색) |
| `src/components/graph/GraphFilterSidebar.tsx` | 78 | 좌측 패널: 노드/엣지 타입별 Checkbox 필터 + 카운트 표시 |
| `src/pages/ExplorePage.tsx` | 148 | Explore 페이지: Toolbar + FilterSidebar + Canvas + DetailPanel 조합 |
| **소계** | **898** | |

### 프론트엔드 수정 파일 (2개)

| 파일 | 변경 내용 |
|------|----------|
| `src/api/client.ts` | `fetchGraphStats()`, `fetchGraph()`, `fetchNeighbors()` 3개 함수 추가 (+20행) |
| `src/App.tsx` | `Page` 타입에 `'explore'` 추가, `ExplorePage` import + 렌더링, 헤더에 "Explore Graph" 버튼 추가 (+15행) |

### 총 변경량

| 구분 | 신규 | 수정 | 총 라인 추가 |
|------|------|------|-------------|
| 백엔드 | 1 파일 | 2 파일 | ~216행 |
| 프론트엔드 | 9 파일 | 2 파일 | ~933행 |
| **합계** | **10 파일** | **4 파일** | **~1,149행** |

---

## 4. 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend (localhost:80)                                          │
│                                                                    │
│  App.tsx  ─── 'explore' ──→  ExplorePage.tsx                       │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ GraphToolbar (검색 | 레이아웃 선택 | 줌 | 통계 배지)         │ │
│  ├──────────┬──────────────────────────────┬───────────────────┤ │
│  │ Filter   │     GraphCanvas              │  NodeDetail       │ │
│  │ Sidebar  │     (Cytoscape.js)           │  Panel            │ │
│  │          │                              │                   │ │
│  │ [✓] Cust │   ● Customer_1 ──→ Order_1  │  Label: Customer  │ │
│  │ [✓] Prod │   ● Product_3  ──→ Review_5 │  Name: 김민수      │ │
│  │ [✓] Order│   ● Category_2              │  Props: ...       │ │
│  │ [ ] Addr │                              │  Connections: 5   │ │
│  │          │                              │  [Expand]         │ │
│  └──────────┴──────────────────────────────┴───────────────────┘ │
│                                                                    │
│  use-graph-data.ts (커스텀 훅)                                     │
│  ├─ fetchGraph(500) ──→ elements 변환                              │
│  ├─ fetchGraphStats() ──→ 카운트 표시                              │
│  ├─ 필터/검색/선택 상태 관리                                        │
│  └─ expandNode() ──→ fetchNeighbors() ──→ 노드 추가               │
└──────────────┬─────────────────────────────────────────────────────┘
               │  nginx 프록시 (/api → backend:8000)
┌──────────────▼─────────────────────────────────────────────────────┐
│  Backend (localhost:8000)                                           │
│                                                                      │
│  app/routers/graph.py                                               │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  GET /api/v1/graph/stats                                     │   │
│  │  → MATCH (n) UNWIND labels(n) AS lbl RETURN lbl, count(*)   │   │
│  │  → MATCH ()-[r]->() RETURN type(r), count(*)                │   │
│  │  → GraphStats { node_counts, edge_counts, totals }           │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  GET /api/v1/graph/full?limit=500                            │   │
│  │  → MATCH (n) RETURN n, labels(n), elementId(n) LIMIT $limit │   │
│  │  → MATCH (a)-[r]->(b) WHERE elementId IN $eids              │   │
│  │  → GraphData { nodes[], edges[], totals, truncated }         │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  GET /api/v1/graph/neighbors/{node_id}?depth=1              │   │
│  │  → MATCH path = (start:{Label} {id: $id})-[*1..N]-(end)    │   │
│  │  → GraphData { nodes[], edges[] }                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│                     Neo4j (bolt://neo4j:7687)                       │
│                     60 nodes, 97 edges, 9 labels                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. API 상세

### 5.1 GET /api/v1/graph/stats
그래프 전체 노드/엣지 타입별 카운트. 필터 사이드바의 카운트 배지에 사용.

```json
{
  "node_counts": {"Review": 15, "Product": 8, "Order": 8, "Payment": 8, "Category": 6, "Address": 5, "Customer": 5, "Supplier": 3, "Coupon": 2},
  "edge_counts": {"WROTE": 15, "REVIEWS": 15, "CONTAINS": 12, "BELONGS_TO": 8, ...},
  "total_nodes": 60,
  "total_edges": 97
}
```

### 5.2 GET /api/v1/graph/full?limit=500
전체 그래프 데이터 (limit까지). 노드 ID는 `{Label}_{id}` 형식으로 충돌 방지.

```json
{
  "nodes": [{"id": "Customer_1", "label": "Customer", "display_name": "김민수", "properties": {...}}, ...],
  "edges": [{"id": "...", "source": "Customer_1", "target": "Order_1", "rel_type": "PLACED", "properties": {}}, ...],
  "total_nodes": 60,
  "total_edges": 97,
  "truncated": false
}
```

### 5.3 GET /api/v1/graph/neighbors/{node_id}?depth=1
특정 노드 주변 이웃 노드/엣지. Lazy expansion에 사용.

---

## 6. 인터랙션 설계

| 동작 | 트리거 | 결과 |
|------|--------|------|
| 노드 클릭 | Cytoscape `tap` on node | 우측 DetailPanel 열림 — 속성, 연결 노드 목록 |
| 배경 클릭 | Cytoscape `tap` on background | DetailPanel 닫힘 |
| Expand 버튼 | DetailPanel 내 클릭 | `fetchNeighbors()` → 주변 노드 추가 로드 |
| 연결 노드 클릭 | DetailPanel 내 목록 클릭 | 해당 노드로 줌+센터링 + 선택 |
| 검색 | Toolbar input (debounce 300ms) | 매칭 노드 하이라이트 (노란 테두리) + 첫 매칭 노드로 줌 |
| 타입 필터 | FilterSidebar 체크박스 | 체크 해제한 타입의 노드/엣지 제거 |
| 레이아웃 전환 | Toolbar 드롭다운 | COSE(기본) / Concentric / Grid 레이아웃 애니메이션 적용 |
| 줌 인/아웃 | Toolbar 버튼 or 마우스 휠 | 1.3배 줌 인/아웃 |
| Fit View | Toolbar 버튼 | 전체 그래프가 뷰포트에 맞도록 줌 조정 |

---

## 7. 성능 전략

| 전략 | 구현 |
|------|------|
| 서버사이드 limit | `GET /full?limit=500` (기본 500, 최대 5000) |
| Canvas 렌더링 | Cytoscape.js Canvas 기반 (DOM 노드 생성 없음) |
| 줌아웃 시 라벨 숨김 | `min-zoomed-font-size: 10` (노드), `12` (엣지) |
| Lazy expansion | 노드 클릭 → Expand 버튼 → `fetchNeighbors` |
| 클라이언트 필터링 | 타입 체크박스로 불필요한 노드/엣지 즉시 제거 |
| Truncation 표시 | 서버 limit 초과 시 "Truncated" 배지 표시 |

---

## 8. 노드 색상 맵

| 노드 타입 | 색상 | HEX |
|-----------|------|-----|
| Customer | Indigo | `#6366f1` |
| Product | Emerald | `#10b981` |
| Order | Amber | `#f59e0b` |
| OrderItem | Orange | `#f97316` |
| Category | Violet | `#8b5cf6` |
| Review | Pink | `#ec4899` |
| Supplier | Cyan | `#06b6d4` |
| Payment | Teal | `#14b8a6` |
| Shipment | Blue | `#3b82f6` |
| Address | Slate | `#64748b` |
| Inventory | Lime | `#84cc16` |
| Promotion | Red | `#ef4444` |

미등록 타입은 기본 Slate-400 (`#94a3b8`).

---

## 9. 파일 목록

| # | 파일 | 작업 |
|---|------|------|
| 1 | `backend/app/models/schemas.py` | 수정 — GraphNode, GraphEdge, GraphData, GraphStats 추가 |
| 2 | `backend/app/routers/graph.py` | **신규** — 3개 API 엔드포인트 |
| 3 | `backend/app/main.py` | 수정 — graph 라우터 등록 |
| 4 | `frontend/src/types/graph.ts` | **신규** — TS 타입 정의 |
| 5 | `frontend/src/api/client.ts` | 수정 — 3개 API 함수 추가 |
| 6 | `frontend/src/components/graph/graph-styles.ts` | **신규** — 스타일시트 빌더 |
| 7 | `frontend/src/components/graph/graph-layouts.ts` | **신규** — 레이아웃 프리셋 |
| 8 | `frontend/src/components/graph/use-graph-data.ts` | **신규** — 커스텀 훅 |
| 9 | `frontend/src/components/graph/GraphCanvas.tsx` | **신규** — Cytoscape 래퍼 |
| 10 | `frontend/src/components/graph/GraphToolbar.tsx` | **신규** — 검색/레이아웃/줌 |
| 11 | `frontend/src/components/graph/NodeDetailPanel.tsx` | **신규** — 노드 상세 패널 |
| 12 | `frontend/src/components/graph/GraphFilterSidebar.tsx` | **신규** — 필터 사이드바 |
| 13 | `frontend/src/pages/ExplorePage.tsx` | **신규** — Explore 페이지 |
| 14 | `frontend/src/App.tsx` | 수정 — 'explore' 라우트 + 네비게이션 |

---

## 10. 빌드 & 배포 검증

| 검증 항목 | 명령어 | 결과 |
|-----------|--------|------|
| TypeScript 타입 체크 | `npx tsc --noEmit` | 에러 0개 |
| Vite 프로덕션 빌드 | `npx vite build` | 성공 (825KB JS) |
| Docker 전체 빌드 | `docker compose up --build` | 5/5 컨테이너 Running |
| Graph Stats API | `curl /api/v1/graph/stats` | 60 nodes, 97 edges |
| Graph Full API | `curl /api/v1/graph/full?limit=10` | 노드/엣지 JSON 정상 |
| Neighbors API | `curl /api/v1/graph/neighbors/Customer_1` | 김민수 이웃 정상 |
| nginx 프록시 | `curl localhost/api/v1/graph/stats` | 정상 전달 |
| JS 번들 확인 | `grep "Explore Graph" *.js` | 포함 확인 |

---

## 11. 트러블슈팅

### Docker 빌드 시 TypeScript 에러
로컬 `node_modules`와 Docker 내 `npm ci`로 설치되는 `@types/cytoscape` 버전 차이로 4개 에러 발생:

| 에러 | 원인 | 수정 |
|------|------|------|
| `'Stylesheet' has no exported member` | `@types/cytoscape` 버전에 `Stylesheet` 타입 없음 | 커스텀 타입 `Array<{selector, style}>` 으로 대체 |
| `activeLabels is declared but never read` | TS strict mode `noUnusedParameters` | `_activeLabels`로 변경 |
| `Expected 1 arguments, but got 0` | `useRef()` 초기값 누락 | `useRef(undefined)` 명시 |
| `cytoscape.Stylesheet[]` cast 실패 | 같은 타입 이슈 | `as never` cast로 대체 |

---

## 12. 다음 단계 (향후)

| # | 항목 | 설명 |
|---|------|------|
| 1 | 노드 display_name 개선 | `name` 프로퍼티가 없는 노드의 표시명 개선 (현재 `id` 표시) |
| 2 | 엣지 그룹핑 | 동일 소스-타겟 간 다중 엣지 시각적 구분 |
| 3 | 그래프 내보내기 | PNG/SVG 이미지 다운로드 기능 |
| 4 | 경로 하이라이트 | Query 결과의 evidence path를 그래프에서 하이라이트 |
| 5 | 실시간 KG 연동 | KG 빌드 완료 시 Explore 자동 갱신 |
