# GraphRAG Ontology Builder — Gap Analysis & Priority Roadmap

**Date:** 2026-03-06
**Version:** v0.9.0 (PoC)
**Analyst:** Claude Opus 4.6 (코드 기반 자동 분석)

---

## 1. Product Gaps (제품 완성도)

### 1.1 도메인 일반화 — 이커머스에 강하게 결합

| 발견 | 근거 |
|------|------|
| `TABLE_TO_LABEL` 9개 이커머스 테이블 하드코딩 | `fk_rule_engine.py:22-32` |
| `JOIN_TABLE_CONFIG` 3개만 고정 (order_items, wishlists, shipping) | `fk_rule_engine.py:35-54` |
| `DIRECTION_MAP` FK 15개 이커머스만 | `fk_rule_engine.py:62-75` |
| 평가 golden data 이커머스 전용 (9노드, 12관계) | `golden_ecommerce.py:11-41` |
| Q&A 골든 50개 전부 이커머스 시드 데이터 기반 | `qa_golden.py:1-83` |
| Entity extraction 하드코딩 (김민수, 맥북프로 등) | `local_search.py:28-34` |

**영향:** `demo_accounting.sql`, `bootcamp_ddl.sql` 업로드 시 자동 매핑은 되지만 관계 방향 오류 가능, 평가 불가능, Q&A 데모 불가능.

### 1.2 DDL 파싱 엣지 케이스

| 미지원 항목 | 근거 |
|------------|------|
| 복합 PK (`PRIMARY KEY (a, b)`) | `parser.py:65-66` — `pk_col` 단일값만 |
| 스키마 프리픽스 (`schema.table`) | `parser.py:77-81` — `\w+` 단일 매칭만 |
| VIEW, ENUM, TYPE | `parser.py:28` — `exp.Create` (TABLE만) |
| CHECK 제약조건 | 파서에 미구현 |
| DEFAULT 값 | `ColumnInfo` 모델에 필드 없음 |
| UNIQUE 제약조건 | 파서에 미구현 |

### 1.3 Q&A 정확도 한계

| 한계 | 근거 |
|------|------|
| Rule router 5개 정규식만 (이커머스 용어) | `router_rules.py:15-50` |
| 13개 Cypher 템플릿 (SUM/MIN/MAX 없음, Subquery 없음) | `template_registry.py:129-247` |
| Entity extraction이 시드 데이터 고정 (CSV 임포트 후 새 엔티티 미인식) | `local_search.py:28-34` |
| Aggregate 질문 7개 패턴만 | `local_search.py:157-165` |

### 1.4 CSV 임포트 제약

| 제약 | 근거 |
|------|------|
| UTF-8만 지원 (CP949, Shift-JIS 불가) | `csv_import/parser.py:147-155` |
| 전체 행 메모리 로드 (스트리밍 없음) | `parser.py:174` — `list(reader)` |
| 한 컬럼 실패 시 전체 행 드롭 | `parser.py:195-202` |
| NULL 변형 미인식 ("N/A", "-" 등) | `parser.py:208-225` |

---

## 2. Technical Debt (기술 부채)

### 2.1 인메모리 상태 — 서버 재시작 시 유실

| 상태 | 근거 | 심각도 |
|------|------|--------|
| KG 빌드 job dict | `kg_builder/service.py:27` — `_jobs: dict = {}` | Critical |
| CSV 세션 스토어 | `csv_import/parser.py:16` — `_csv_sessions: dict = {}` | Critical |
| PG 저장은 "best-effort" (실패해도 조용히 진행) | `service.py:61-66`, `pipeline.py:77-86` | Critical |

### 2.2 보안

| 취약점 | 근거 | 심각도 |
|--------|------|--------|
| API 인증/인가 완전 부재 | `main.py:38-79` — 모든 엔드포인트 공개 | Critical |
| DB 비밀번호 기본값 하드코딩 | `config.py:23-24` — `password123`, `graphrag123` | Critical |
| CORS `allow_methods=["*"]`, `allow_headers=["*"]` | `main.py:46-53` | High |
| Cypher 라벨 regex 검증만 (파라미터 바인딩은 사용) | `slot_filler.py:14-50` | Low |

### 2.3 에러 핸들링

| 문제 | 근거 |
|------|------|
| best-effort 패턴 (except -> logger.warning -> 계속) 5곳 이상 | `service.py`, `pipeline.py`, `main.py` |
| KG 빌드 실패 시 그래프 정리도 실패 가능 (조용히 스킵) | `service.py:141-149` |
| 실패 stage 판별에 `"data" in dir()` 사용 (불안정) | `service.py:129` |

### 2.4 테스트/성능

| 문제 | 근거 |
|------|------|
| PG/Neo4j 실제 연동 테스트 0건 (전부 mock) | `test_e2e_integration.py` |
| Neo4j UNIQUE 제약만, 일반 인덱스 없음 | `loader.py:64-68` |
| PG 연결 풀 없음 (매 요청 새 연결) | `pg_client.py:29-38` |
| UNWIND 배치 크기 제한 없음 | `loader.py:71-80` |
| N+1 쿼리 패턴 (노드 ID lookup) | `pipeline.py:318-335` |

### 2.5 배포/운영

| 문제 | 근거 |
|------|------|
| Graceful shutdown 불완전 (BackgroundTasks 미대기) | `main.py:97-104` |
| 구조화 로깅 없음 (요청 ID 추적 불가) | 전체 |
| Prometheus 메트릭 없음 | 전체 |

---

## 3. UX/UI Completeness (UX/UI 완성도)

### 심각한 부족점

| 문제 | 근거 |
|------|------|
| **모바일 완전 미대응** — 그래프 3단 레이아웃(w-56 + flex-1 + w-72) 깨짐 | `ExplorePage.tsx:171-289` |
| **React Router 없음** — 새로고침 시 항상 Upload로, 브라우저 뒤로가기 불가 | `App.tsx:37-84` |
| **온보딩 거의 없음** — 첫 사용자가 어디서 시작할지 불명확 | `UploadPage.tsx:72-76` |
| **접근성 미흡** — aria-live 없음, 키보드 네비게이션 부분적, 색상만으로 구분 | `QueryPage.tsx:60-74` |
| **fetch timeout 없음** — AbortController 미사용 | `api/client.ts:30-46` |
| **KG 빌드 진행률 표시 없음** — "queued/running/succeeded"만 | `BuildKGActions.tsx:52-59` |
| **페이지 상태 미보존** — 리뷰->쿼리->리뷰 시 처음부터 | `App.tsx:14-26` |

---

## 4. Scaling Readiness (스케일링 준비도)

| 항목 | 준비도 | 권장 한계 | 주요 병목 |
|------|--------|---------|---------|
| 멀티 테넌트 | **0%** | 불가 | 전역 공유 구조, tenant_id 없음 |
| 동시 사용자 | **20%** | 5-10명 | 전역 dict 락 없음, PG 연결 풀 없음 |
| Neo4j | **40%** | ~100만 노드 | Community Edition, 인덱스 부재, 배치 무제한 |
| LLM 비용 | **50%** | $100-500/월 | 5개 캐시만, rate limiting 없음, 토큰 추적 부분적 |
| 데이터 크기 | **30%** | CSV 50MB, 그래프 100만 노드 | 메모리 스트리밍 없음 |

---

## 5. Competitive Moat (시장 차별화)

### 핵심 경쟁 우위

| 차별점 | 강도 | 근거 |
|--------|------|------|
| 자동 FK->온톨로지 결정적 엔진 | +++++ | `fk_rule_engine.py:134-277` |
| 2-Stage (FK규칙 + 선택적 LLM) | ++++ | `ontology/pipeline.py` — LLM 없어도 97% 작동 |
| A/B 비교 모드 (템플릿 vs 로컬서치) | +++ | `query/pipeline.py:21-56` |
| TTV ~3분 실측 달성 | +++ | `PoC_성공기준_KPI.md`, `demo_cache.py` |
| 캐시 기반 5/5 데모 100% 보증 | +++ | `demo_cache.py:32-88` |

### 부족한 기능

| 기능 | 시장 필요도 | 추가 비용 |
|------|-----------|---------|
| 온톨로지 도메인 템플릿 라이브러리 | 높음 (70%) | 2-4주 |
| 다국어 Q&A (영어 등) | 높음 (글로벌 시) | 1주 |
| 자연어->DDL 역변환 | 낮음 (10%) | 1-2주 |
| 스키마 추천/자동 인덱싱 | 중간 (30%) | 2주 |

---

## 6. Priority Roadmap (Impact x Effort)

### P0 — Demo/Sales Critical (1-2 weeks)

| # | Task | Impact | Effort | Rationale |
|---|------|--------|--------|-----------|
| 1 | **API Authentication** (Bearer token / API key) | H | L | `main.py` — Public server allows anyone to create/delete KGs |
| 2 | **Dynamic Entity Extraction** — query Neo4j for entity lists at runtime | H | L | `local_search.py:28-34` — New entities after CSV import not recognized |
| 3 | **Fetch timeout + retry button** | H | L | `api/client.ts:30-46` — Users stuck during KG build timeout |
| 4 | **KG Build progress display** (step-by-step %) | M | L | `BuildKGActions.tsx` — "Is it frozen?" during demos |

### P1 — MVP Must-Have (1 month)

| # | Task | Impact | Effort | Rationale |
|---|------|--------|--------|-----------|
| 5 | **In-memory -> PG persistent storage** (jobs, csv_sessions) | H | M | `service.py:27`, `parser.py:16` — Server restart loses all in-progress work |
| 6 | **Multi-domain support** — Separate DIRECTION_MAP/JOIN_TABLE_CONFIG per domain + auto join table detection | H | H | `fk_rule_engine.py:22-75` — Cannot demo non-ecommerce domains |
| 7 | **URL-based routing** (React Router) | H | M | `App.tsx:37-84` — Refresh loses state, no deep links |
| 8 | **PG connection pool** (psycopg2.pool) | H | L | `pg_client.py:29-38` — 10+ concurrent requests exhaust connections |
| 9 | **Composite PK parsing** | M | M | `parser.py:65-66` — Common in real-world DDLs |
| 10 | **Fix best-effort pattern** — Explicit error return or retry on PG failure | M | M | `service.py:61-66` — Silent data loss |

### P2 — Growth Phase (3 months)

| # | Task | Impact | Effort | Rationale |
|---|------|--------|--------|-----------|
| 11 | **Multi-tenancy foundation** — `tenant_id` in DB, Neo4j namespacing | H | H | Global shared structure — B2B SaaS requirement |
| 12 | **LLM token tracking + rate limiting** | M | M | `llm_enricher.py`, `router_llm.py` — No cost control |
| 13 | **Mobile graph view refactoring** (tab/modal based) | M | M | `ExplorePage.tsx:171-289` — 3-column layout breaks on mobile |
| 14 | **Neo4j index auto-generation + batch size limits** | M | L | `loader.py:64-68` — Only UNIQUE constraint, no general indexes |
| 15 | **Structured logging + Prometheus metrics** | M | M | No debugging/monitoring capability in production |
| 16 | **CSV streaming + CP949 encoding** | M | M | `parser.py:174` — OOM risk for 50MB+ files |
| 17 | **Domain-specific evaluation framework** | M | M | `golden_ecommerce.py` — Cannot measure quality for new domains |

### P3 — Nice to Have

| # | Task | Impact | Effort | Rationale |
|---|------|--------|--------|-----------|
| 18 | Onboarding tour (first-visit guide) | L | L | `UploadPage.tsx:72-76` |
| 19 | Accessibility (aria-live, keyboard nav) | L | M | `QueryPage.tsx:151` |
| 20 | Multilingual Q&A (English) | M | L | Claude API already supports; extend cache/router |
| 21 | Graceful shutdown (await BackgroundTasks) | L | M | `main.py:97-104` |
| 22 | Schema prefix / VIEW / ENUM parsing | L | M | `parser.py:28, 77-81` |
| 23 | Natural language -> DDL reverse generation | L | M | Low market demand (10%) |

---

## Implementation Status (Updated 2026-03-06)

### P0 — All Complete
- [x] #1 API Authentication — Pure ASGI middleware (`app/auth.py`)
- [x] #2 Dynamic Entity Extraction — Neo4j query + TTL cache + fallback (`local_search.py`)
- [x] #3 Fetch timeout — AbortController 30s/180s (`client.ts`)
- [x] #4 KG Build progress — Step-by-step % bar (`BuildKGActions.tsx`)

### P1 — All Complete
- [x] #5 PG job persistence — `get_job()` PG fallback (`service.py`)
- [x] #6 Multi-domain support — Auto join-table detection + auto PascalCase mapping (`fk_rule_engine.py`)
- [x] #7 React Router — URL-based routing (`App.tsx`, `main.tsx`)
- [x] #8 PG connection pool — `SimpleConnectionPool(1,10)` (`pg_client.py`)
- [x] #9 Composite PK parsing — sqlglot AST + regex fallback (`parser.py`)
- [x] #10 Best-effort fix — `error` log level + `warnings[]` in response (`pipeline.py`, `service.py`)

### P2 — All Complete
- [x] #14 Neo4j 인덱스 자동 생성 — `name` 프로퍼티 인덱스 + UNWIND 배치 5000건 제한 (`loader.py`)
- [x] #12 LLM 토큰 추적 — 중앙 tracker (`llm_tracker.py`), 5개 LLM caller 연동, `GET /api/v1/llm-usage` 엔드포인트
- [x] #15 구조화 로깅 — JSON(prod) / colored text(dev) 듀얼 포맷 (`logging_config.py`)
- [x] #16 CSV CP949/EUC-KR — 한글 엑셀 CSV 자동 인코딩 감지 (`csv_import/parser.py`)
- [x] #13 모바일 그래프 뷰 — 사이드바/디테일패널 오버레이, 토글 버튼 (`ExplorePage.tsx`)
- [x] #17 도메인별 평가 — 이커머스 감지 + auto-golden 생성 (`auto_golden.py`, `pipeline.py`)
- [x] #11 Multi-tenancy foundation — tenant.py 유틸, 3-mode auth, PG tenant_id 컬럼, Neo4j label prefix, 전체 router/service tenant_id threading, 프론트엔드 API key header

### P3 — All Complete
- [x] #20 Multilingual Q&A — English regex patterns (Q1-Q5), bilingual answer generation, English demo buttons
- [x] #18 Onboarding tour — 4-step first-visit guide with localStorage (`OnboardingTour.tsx`)
- [x] #21 Graceful shutdown — `wait_for_active_builds()` + 30s timeout on shutdown (`service.py`, `main.py`)
- [x] #22 Schema prefix / VIEW / ENUM parsing — schema prefix strip, VIEW/ENUM skip, IF NOT EXISTS (`parser.py`)
- [x] #19 Accessibility — aria-live, role=log/status/alert, aria-expanded, skip-to-content, keyboard nav
- [x] #23 NL→DDL — LLM-based DDL generation from NL (`nl_to_ddl.py`), POST /api/v1/ddl/generate-from-nl, frontend UI

**Test results:** 259 tests passing (17 new: 8 query + 3 parser + 4 NL→DDL + 2 clean_ddl), frontend build clean.

---

## Summary

> **Now (P0):** Security (auth) + Dynamic entity extraction + UI timeout -> Demo stability
> **1 month (P1):** Persistent storage + Multi-domain + Routing -> MVP minimum
> **3 months (P2):** Multi-tenancy + Cost control + Monitoring -> Production-ready B2B SaaS
