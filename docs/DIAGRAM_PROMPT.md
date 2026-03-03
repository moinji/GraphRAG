# GraphRAG 파이프라인 다이어그램 생성 프롬프트

> 아래 프롬프트를 Claude, ChatGPT, 또는 다이어그램 생성 AI에 붙여넣기하세요.

---

## 프롬프트

다음 시스템의 **전체 파이프라인 아키텍처 다이어그램**을 그려줘. 깔끔하고 전문적인 기술 다이어그램으로, 비개발자도 데이터 흐름을 이해할 수 있어야 해.

### 시스템 개요
**GraphRAG** — SQL DDL에서 Knowledge Graph를 자동 구축하고, 자연어 질의와 인터랙티브 시각화를 제공하는 풀스택 시스템.

### 인프라 (Docker Compose, 5개 컨테이너)
- **Frontend**: React 19 + TypeScript + Tailwind + Shadcn UI → Nginx로 서빙 (포트 80)
- **Backend**: FastAPI (Python) → Uvicorn (포트 8000)
- **Neo4j**: 그래프 데이터베이스 (Bolt 7687) — 노드/관계 저장 및 Cypher 질의
- **PostgreSQL**: 메타데이터 저장소 — 온톨로지 버전, 빌드 이력
- **Redis**: 캐시/세션 (포트 6379)

### 파이프라인 4단계

#### [STAGE 1] 스키마 입력 및 파싱
```
사용자 → .sql DDL 파일 업로드
         ↓
    DDL Parser (sqlglot + regex)
         ↓
    ERDSchema 생성 (테이블, 컬럼, FK 관계)
         ↓
    (선택) CSV 데이터 업로드 → 유효성 검증 → 인메모리 세션 저장
```
- 입력: SQL CREATE TABLE 문
- 출력: ERDSchema JSON (테이블 구조 + FK 관계 목록)
- CSV는 테이블별 실제 데이터 제공 (없으면 샘플 자동 생성)

#### [STAGE 2] 온톨로지 생성 (2단계 파이프라인)
```
ERDSchema
    ↓
  ┌─────────────────────────────────────┐
  │ Stage 2-1: FK Rule Engine (결정론적) │
  │  • 테이블 → PascalCase 노드 라벨    │
  │  • FK 컬럼 → 관계 타입 매핑         │
  │  • 조인테이블 → 관계로 변환          │
  │  • 자기참조 FK 처리 (parent_id 등)   │
  └─────────────┬───────────────────────┘
                ↓
         Baseline OntologySpec
                ↓
  ┌─────────────────────────────────────────┐
  │ Stage 2-2: LLM 보강 (선택, Claude API)   │
  │  • 관계 이름 개선                        │
  │  • 누락된 의미적 관계 추가               │
  │  • derivation="llm_suggested" 태그       │
  └─────────────┬───────────────────────────┘
                ↓
         Golden Data 평가 (정확도/커버리지 메트릭)
                ↓
         PostgreSQL에 버전 저장 (status=draft)
```
- 핵심: 어떤 도메인 DDL이든 자동으로 그래프 온톨로지 생성
- 출력: OntologySpec (노드 타입 + 관계 타입 + 속성 매핑)

#### [STAGE 3] 사용자 검토 → KG 빌드
```
ReviewPage (프론트엔드)
    ├── 노드/관계 편집 (추가/수정/삭제)
    ├── LLM 변경사항 Diff 확인
    ├── 평가 메트릭 확인
    └── [Approve] 클릭 → status = "approved"
         ↓
    [Build KG] 클릭 (+ 선택적 csv_session_id)
         ↓
    백그라운드 태스크 (비동기 202 응답)
         ↓
  ┌──────────────────────────────────────┐
  │ KG Builder                           │
  │  1. 데이터 소스 결정                  │
  │     • CSV 세션 있으면 → 실제 데이터   │
  │     • 없으면 → 샘플 데이터 자동 생성  │
  │  2. FK 무결성 검증                    │
  │  3. Neo4j 로드                       │
  │     • 기존 그래프 삭제                │
  │     • 유니크 제약조건 생성            │
  │     • UNWIND + MERGE 노드 배치 삽입  │
  │     • UNWIND + MERGE 관계 배치 삽입  │
  │  4. 카운트 검증                      │
  └──────────────────────────────────────┘
         ↓
    프론트엔드 폴링 → 진행률 표시 (노드/관계 생성 수)
```

#### [STAGE 4] 활용 — 질의 + 시각화

**4-A. 자연어 질의 (QueryPage)**
```
사용자 질문 입력
    ↓
  ┌──────── Mode A: 템플릿 기반 ────────┐
  │  규칙 매칭 (regex 패턴)              │
  │    ↓ 실패 시                        │
  │  LLM 라우터 (Claude Haiku)          │
  │    ↓                                │
  │  Cypher 템플릿 슬롯 채우기           │
  │    ↓                                │
  │  Neo4j 실행 → 결과 포맷팅           │
  └──────────────────────────────────────┘
                또는
  ┌──────── Mode B: 로컬 서치 ──────────┐
  │  엔티티 추출 (규칙 기반)             │
  │    ↓                                │
  │  Neo4j 서브그래프 탐색 (1~3홉)      │
  │    ↓                                │
  │  Claude Sonnet에 컨텍스트 주입      │
  │    ↓                                │
  │  자연어 답변 생성                    │
  └──────────────────────────────────────┘
    ↓
  답변 + Cypher + 증거경로 + 메타데이터 표시
```

**4-B. 인터랙티브 그래프 탐색 (ExplorePage)**
```
  Neo4j → Graph API (3개 엔드포인트)
    ├── /stats: 노드/엣지 타입별 카운트
    ├── /full?limit=500: 전체 그래프 데이터
    └── /neighbors/{id}: 노드 주변 확장
         ↓
  Cytoscape.js (Canvas 렌더링)
    ├── 노드: 타입별 색상 구분
    ├── 관계: 방향성 엣지
    ├── 레이아웃: COSE / Grid / Circle / Breadthfirst
    └── 인터랙션:
        • 노드 클릭 → 속성 패널
        • 검색 → 노드 하이라이트 + 줌
        • 필터 → 타입별 표시/숨김
        • Expand → 이웃 노드 동적 로드
```

### 다이어그램 스타일 요구사항
1. **좌→우 또는 상→하 흐름**으로 4단계를 순차적으로 배치
2. 각 단계를 **색상으로 구분** (예: Stage 1=파랑, Stage 2=초록, Stage 3=주황, Stage 4=보라)
3. **인프라 컴포넌트**(Neo4j, PG, Redis)는 하단에 별도 레이어로 배치하고, 점선으로 연결
4. **프론트엔드 4개 페이지**(Upload, Review, Query, Explore)를 상단에 배치
5. 데이터 흐름은 **실선 화살표**, 선택적 흐름은 **점선 화살표**
6. 각 화살표 위에 **데이터 포맷** 표기 (ERDSchema, OntologySpec, GraphData 등)
7. 핵심 기술 스택을 각 컴포넌트 박스 안에 작은 글씨로 표기
8. **한국어** 라벨 사용
9. 깔끔하고 전문적인 느낌, 여백 충분히

### 핵심 데이터 흐름 요약
```
.sql DDL → [파싱] → ERDSchema → [FK규칙+LLM] → OntologySpec → [검토/승인] → [빌드] → Neo4j Graph
                                                                      ↑
                                                              .csv 데이터 (선택)

Neo4j Graph → [Cypher 질의] → 자연어 답변 (Mode A)
Neo4j Graph → [서브그래프 + Claude] → 자연어 답변 (Mode B)
Neo4j Graph → [Graph API] → Cytoscape.js 시각화
```
