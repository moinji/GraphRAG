# Week 4 개발 보고서 — KG Builder Job 모델 + 샘플 데이터 + 프론트엔드 빌드 연동
> 작성일: 2026-02-26 | 목적: 비동기 KG Build Job 모델 + FK 무결성 샘플 데이터 + 프론트엔드 Build KG 버튼 활성화

---

## 1. 요약

**승인된(approved) 온톨로지 버전으로 Knowledge Graph를 비동기 빌드하는 Job 모델**을 백엔드에 추가하고, **프론트엔드에 Build KG 버튼 + 2초 폴링 진행 표시**를 구현했습니다. 기존 `generate_sample_data()` + `load_to_neo4j()` 재사용으로 demo.py 호환성을 유지합니다.

| 지표 | 목표 | 실제 | 상태 |
|------|------|------|------|
| POST /kg/build → 202 (queued) | 202 | 202 | PASS |
| POST /kg/build (draft 버전) → 409 | 409 | 409 | PASS |
| POST /kg/build (없는 버전) → 404 | 404 | 404 | PASS |
| GET /kg/build/{job_id} → 200 | 200 | 200 | PASS |
| GET /kg/build/{없는 job} → 404 | 404 | 404 | PASS |
| 빌드 성공 → succeeded + progress | succeeded | succeeded | PASS |
| 빌드 실패 → failed + error | failed | failed | PASS |
| KG Build 테스트 | 10/10 | 10/10 | PASS |
| 전체 백엔드 테스트 | 66+ | 76 | PASS |
| 프론트엔드 빌드 (`npm run build`) | 에러 0 | 에러 0 | PASS |

> 테스트 76건 = 38개 고유 테스트 × 2 async 백엔드 (asyncio + trio)

---

## 2. 구현 범위

### 백엔드 신규 파일 (4개)

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `app/db/kg_build_store.py` | 115 | PG kg_builds 테이블 CRUD (best-effort) |
| `app/kg_builder/service.py` | 174 | KG Build Job 오케스트레이터 (인메모리 dict + PG) |
| `app/routers/kg_build.py` | 57 | POST /kg/build (202) + GET /kg/build/{job_id} |
| `tests/test_kg_build.py` | 274 | KG Build API 테스트 10개 |
| **소계** | **620** | |

### 백엔드 수정 파일 (4개)

| 파일 | 변경 내용 |
|------|----------|
| `app/models/schemas.py` | `KGBuildRequest`, `KGBuildProgress`, `KGBuildErrorDetail`, `KGBuildResponse` 4개 모델 추가 (+28행) |
| `app/exceptions.py` | `BuildJobNotFoundError`(404) + `build_job_not_found_handler()` 추가 (+14행) |
| `app/main.py` | `kg_build` 라우터 등록, 예외 핸들러 등록, 버전 0.4.0 (+4행) |
| `app/db/migrations.py` | `ensure_kg_builds_table()` 호출 추가 (+7행) |

### 프론트엔드 수정 파일 (3개)

| 파일 | 변경 내용 |
|------|----------|
| `src/types/ontology.ts` | `KGBuildProgress`, `KGBuildErrorDetail`, `KGBuildResponse` TS 타입 3개 추가 (+23행) |
| `src/api/client.ts` | `startKGBuild()`, `getKGBuildStatus()` 2개 함수 추가 (+20행) |
| `src/pages/ReviewPage.tsx` | Build KG 버튼 활성화 + 2초 폴링 + 진행/에러 표시 (+106행) |

---

## 3. 아키텍처 — KG Build Job 모델

```
┌────────────────────────────────────────────────────────┐
│  Frontend (localhost:3000)                              │
│                                                        │
│  ReviewPage                                            │
│  ┌──────────────────────────────────────┐              │
│  │ [Build KG] 버튼 (approved 일 때만)     │              │
│  │    ↓                                  │              │
│  │ POST /kg/build → 202 (queued)         │              │
│  │    ↓                                  │              │
│  │ setInterval(2초)                       │              │
│  │    GET /kg/build/{job_id}             │              │
│  │    ↓                                  │              │
│  │ queued → running → succeeded/failed   │              │
│  │    ↓                                  │              │
│  │ 노드/관계 카운트 표시 또는 에러 메시지    │              │
│  └──────────────────────────────────────┘              │
└───────────────┬────────────────────────────────────────┘
                │  Vite 프록시 (/api → :8000)
┌───────────────▼────────────────────────────────────────┐
│  Backend (localhost:8000)                               │
│                                                        │
│  POST /api/v1/kg/build  ← KGBuildRequest               │
│   1. get_version(version_id) — approved 검증            │
│   2. job_id 생성 (build_{timestamp}_{random})           │
│   3. _jobs[job_id] = queued                            │
│   4. BackgroundTasks.add_task(run_kg_build)             │
│   5. 202 응답 반환                                      │
│                                                        │
│  GET /api/v1/kg/build/{job_id}                          │
│   → _jobs[job_id] 조회 → 200 또는 404                   │
│                                                        │
│  ┌─────────────────────────────────────────────────┐   │
│  │ run_kg_build (BackgroundTask)                    │   │
│  │  1. status = running                            │   │
│  │  2. generate_sample_data(erd) + verify_fk       │   │
│  │  3. load_to_neo4j(ontology, data)               │   │
│  │  4. 성공: status=succeeded, progress 기록         │   │
│  │  5. 실패: status=failed, error 기록               │   │
│  │           MATCH (n) DETACH DELETE n (정리)        │   │
│  └────────────┬────────────────────────┬───────────┘   │
│               │                        │               │
│  ┌────────────▼──────┐   ┌────────────▼───────────┐   │
│  │ In-Memory Dict    │   │ PG kg_builds          │   │
│  │ (primary, polling)│   │ (best-effort backup)  │   │
│  └───────────────────┘   └────────────────────────┘   │
│                                                        │
│  ┌──────────────────────┐   ┌───────────────────────┐  │
│  │ data_generator       │   │ Neo4j (bolt:7687)    │  │
│  │ generate_sample_data │──▶│ UNWIND + MERGE       │  │
│  │ verify_fk_integrity  │   │ 9 node types         │  │
│  └──────────────────────┘   │ 12 relationship types│  │
│                              └───────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

### 핵심 설계 원칙

| # | 원칙 | 구현 |
|---|------|------|
| 1 | **인메모리 dict + PG best-effort** | 1인 PoC에서 Redis 큐 불필요. PG 실패해도 Job 동작 |
| 2 | **FastAPI BackgroundTasks** | Celery/Redis Worker 불필요. MVP1 전환 시 인터페이스 분리 가능 |
| 3 | **approved 버전만 빌드** | draft 빌드 방지. version_id로 PG에서 ontology 조회 |
| 4 | **기존 고정 시드 데이터 사용** | demo.py Q1-Q3 답변이 이 데이터에 의존. 호환성 유지 |
| 5 | **실패 시 전체 정리** | partial graph 위험하므로 MATCH (n) DETACH DELETE n |
| 6 | **폴링 2초 간격** | WebSocket 불필요. succeeded/failed 시 clearInterval |

---

## 4. API 엔드포인트 (신규 2개)

### `POST /api/v1/kg/build` → 202

**Request:**
```json
{
  "version_id": 1,
  "erd": {"tables": [...], "foreign_keys": [...]}
}
```

**Response (202 — Accepted):**
```json
{
  "build_job_id": "build_1708900000_a1b2",
  "status": "queued",
  "progress": null,
  "error": null,
  "version_id": 1,
  "started_at": null,
  "completed_at": null
}
```

| 상태 코드 | 조건 |
|-----------|------|
| 202 | 빌드 Job 생성 성공 (비동기 실행 시작) |
| 404 | version_id에 해당하는 버전 없음 |
| 409 | 버전이 approved 상태가 아님 (draft) |

### `GET /api/v1/kg/build/{job_id}` → 200

**Response (succeeded):**
```json
{
  "build_job_id": "build_1708900000_a1b2",
  "status": "succeeded",
  "progress": {
    "nodes_created": 60,
    "relationships_created": 97,
    "duration_seconds": 12.5
  },
  "error": null,
  "version_id": 1,
  "started_at": "2026-02-26T10:00:01",
  "completed_at": "2026-02-26T10:00:13"
}
```

**Response (failed):**
```json
{
  "build_job_id": "build_1708900000_a1b2",
  "status": "failed",
  "progress": null,
  "error": {
    "stage": "neo4j_load",
    "message": "Neo4j not reachable at bolt://localhost:7687 after 30s",
    "detail": ""
  },
  "version_id": 1,
  "started_at": "2026-02-26T10:00:01",
  "completed_at": "2026-02-26T10:00:31"
}
```

| 상태 코드 | 조건 |
|-----------|------|
| 200 | Job 상태 조회 성공 |
| 404 | job_id에 해당하는 Job 없음 |

---

## 5. PG 스키마 — kg_builds 테이블

```sql
CREATE TABLE IF NOT EXISTS kg_builds (
    id           VARCHAR(64) PRIMARY KEY,
    version_id   INTEGER NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress     JSONB,
    error        JSONB,
    started_at   TIMESTAMP,
    completed_at TIMESTAMP,
    created_at   TIMESTAMP DEFAULT NOW()
);
```

### CRUD 함수

| 함수 | 설명 |
|------|------|
| `ensure_kg_builds_table()` | CREATE TABLE IF NOT EXISTS (startup 시 실행) |
| `save_build(job_id, version_id)` | INSERT (status=queued) |
| `update_build(job_id, status, progress, error, ...)` | UPDATE 상태/결과 |
| `get_build(job_id)` | SELECT 단일 조회 |

> PG는 **best-effort**: 모든 CRUD가 try/except로 감싸져 있으며, PG 실패해도 인메모리 Job은 정상 동작

---

## 6. KG Build 파이프라인

```
run_kg_build(job_id, version_id, erd, ontology)
│
├── 1. status = running, started_at = now
│
├── 2. generate_sample_data(erd)
│       → 12 테이블, 60 행 (고정 시드 데이터)
│
├── 3. verify_fk_integrity(data, erd)
│       → FK 참조 무결성 검증 (위반 시 warning 로그)
│
├── 4. load_to_neo4j(ontology, data, uri, user, password)
│       → clean → constraints → nodes → relationships
│       → 반환: {nodes: 60, relationships: 97}
│
├── 성공 시:
│   status = succeeded
│   progress = {nodes_created: 60, relationships_created: 97, duration_seconds: N}
│   completed_at = now
│
└── 실패 시:
    status = failed
    error = {stage: "neo4j_load"|"data_generation", message: "..."}
    MATCH (n) DETACH DELETE n  (partial graph 정리, best-effort)
    completed_at = now
```

### Job 상태 전이

```
           POST /kg/build
                │
                ▼
        ┌──────────────┐
        │    queued     │  ← 202 응답 즉시 반환
        └──────┬───────┘
               │ BackgroundTask 시작
               ▼
        ┌──────────────┐
        │   running     │  ← 데이터 생성 + Neo4j 적재 중
        └──────┬───────┘
               │
        ┌──────┴───────┐
        ▼              ▼
┌──────────────┐ ┌──────────────┐
│  succeeded   │ │   failed     │
│ progress:    │ │ error:       │
│  nodes: 60   │ │  stage: ...  │
│  rels: 97    │ │  message: .. │
│  dur: 12.5s  │ │              │
└──────────────┘ └──────────────┘
```

---

## 7. 프론트엔드 변경

### Build KG 버튼 동작

1. **활성화 조건**: `status === 'approved'` && `versionId` 존재
2. **클릭 시**: `startKGBuild(versionId, erd)` → 202 응답 수신
3. **폴링**: `setInterval(2000ms)` → `getKGBuildStatus(jobId)`
4. **상태별 UI**:

| 상태 | UI 표시 |
|------|---------|
| queued | "Processing..." (pulse 애니메이션) |
| running | "Processing..." (pulse 애니메이션) |
| succeeded | "60 nodes, 97 relationships (12.5s)" (초록색) |
| failed | "neo4j_load: Neo4j unreachable..." (빨간색) |

5. **폴링 종료**: `succeeded` 또는 `failed` 시 `clearInterval`
6. **cleanup**: 컴포넌트 언마운트 시 `useEffect` cleanup으로 폴링 정리

### API 클라이언트 추가 (2개)

| 함수 | HTTP | 엔드포인트 |
|------|------|-----------|
| `startKGBuild(versionId, erd)` | POST | `/api/v1/kg/build` |
| `getKGBuildStatus(jobId)` | GET | `/api/v1/kg/build/{jobId}` |

---

## 8. 테스트 결과 상세

### KG Build 테스트 (10개)

| # | 테스트명 | 검증 내용 | 결과 |
|---|---------|----------|------|
| 1 | `test_build_returns_202` | POST → 202, status=queued, build_job_id 포함 | PASS |
| 2 | `test_build_requires_approved_version` | POST (draft 버전) → 409 | PASS |
| 3 | `test_build_version_not_found` | POST (없는 version_id) → 404 | PASS |
| 4 | `test_get_job_status_queued` | GET → 200, status=queued | PASS |
| 5 | `test_get_job_not_found` | GET /nonexistent → 404 | PASS |
| 6 | `test_build_succeeds` | 빌드 실행 후 GET → status=succeeded + progress | PASS |
| 7 | `test_build_failure_records_error` | Neo4j 실패 mock → status=failed + error | PASS |
| 8 | `test_build_progress_has_counts` | 성공 후 progress에 nodes/rels 카운트 | PASS |
| 9 | `test_fk_integrity_verified` | verify_fk_integrity 호출 확인 | PASS |
| 10 | `test_pg_store_best_effort` | PG 실패해도 빌드 계속 진행 + succeeded | PASS |

### 전체 테스트 실행

```
====================== 76 passed, 106 warnings in 4.76s =======================
```

| 테스트 파일 | 고유 테스트 수 | 실행 수 (×2 backend) | 결과 |
|------------|-------------|---------------------|------|
| `test_ddl_parser.py` | 10 | 10 | 10 PASS |
| `test_api_ddl.py` | 3 | 6 | 6 PASS |
| `test_ontology.py` | 16 (4 API ×2) | 20 | 20 PASS |
| `test_ontology_versions.py` | 10 (×2) | 20 | 20 PASS |
| `test_kg_build.py` | 10 (×2) | 20 | 20 PASS |
| **합계** | **49** | **76** | **76 PASS** |

---

## 9. DoD 체크리스트

| # | 검증 항목 | 명령어 | 결과 |
|---|----------|--------|------|
| 1 | 백엔드 테스트 | `cd backend && pytest tests/ -v` | 76 passed |
| 2 | 프론트엔드 빌드 | `cd frontend && npm run build` | 에러 없이 빌드 성공 |
| 3 | POST /kg/build (approved) → 202 | queued 상태 반환 | PASS |
| 4 | POST /kg/build (draft) → 409 | "must be approved" 에러 | PASS |
| 5 | POST /kg/build (없는 버전) → 404 | "not found" 에러 | PASS |
| 6 | GET /kg/build/{job_id} → 200 | 상태 조회 성공 | PASS |
| 7 | GET /kg/build/{없는 job} → 404 | "not found" 에러 | PASS |
| 8 | 빌드 성공 시 progress 기록 | nodes_created + relationships_created | PASS |
| 9 | 빌드 실패 시 error 기록 | stage + message | PASS |
| 10 | PG 실패해도 빌드 정상 | best-effort 패턴 | PASS |

---

## 10. 파일 구조 (Week 4 후)

```
GraphRAG/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── exceptions.py                ← [MOD] +BuildJobNotFoundError(404)
│   │   ├── main.py                      ← [MOD] +kg_build 라우터, v0.4.0
│   │   ├── models/
│   │   │   └── schemas.py               ← [MOD] +KGBuild 모델 4개
│   │   ├── routers/
│   │   │   ├── health.py
│   │   │   ├── ddl.py
│   │   │   ├── ontology.py
│   │   │   ├── ontology_versions.py
│   │   │   └── kg_build.py              ← [NEW] POST/GET KG Build Job
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
│   │   │   ├── migrations.py            ← [MOD] +kg_builds 테이블 마이그레이션
│   │   │   └── kg_build_store.py        ← [NEW] PG kg_builds CRUD
│   │   ├── data_generator/
│   │   │   └── generator.py             (재사용: generate_sample_data, verify_fk_integrity)
│   │   ├── kg_builder/
│   │   │   ├── loader.py                (재사용: load_to_neo4j)
│   │   │   └── service.py              ← [NEW] KG Build Job 오케스트레이터
│   │   └── query/
│   │       ├── templates.py
│   │       └── executor.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_ddl_parser.py           (10 tests)
│   │   ├── test_api_ddl.py              (3 tests ×2)
│   │   ├── test_ontology.py             (16 tests, 4 API ×2)
│   │   ├── test_ontology_versions.py    (10 tests ×2)
│   │   └── test_kg_build.py            ← [NEW] 10 tests ×2
│   ├── demo.py
│   └── demo_ecommerce.sql
├── frontend/
│   ├── src/
│   │   ├── types/
│   │   │   └── ontology.ts             ← [MOD] +KGBuild TS 타입 3개
│   │   ├── api/
│   │   │   └── client.ts               ← [MOD] +startKGBuild, +getKGBuildStatus
│   │   ├── pages/
│   │   │   ├── UploadPage.tsx
│   │   │   └── ReviewPage.tsx           ← [MOD] Build KG 버튼 + 폴링 + 진행 표시
│   │   └── ...
│   └── ...
├── docker-compose.yml
├── requirements.txt
├── PLAN.md
├── DEV_REPORT_v0.md
├── DEV_REPORT_w1.md
├── DEV_REPORT_w2.md
├── DEV_REPORT_w3.md
└── DEV_REPORT_w4.md                    ← [NEW] 본 보고서
```

---

## 11. 코드 규모 누적

| 구분 | Demo v0 | Week 1 | Week 2 | Week 3 | Week 4 | 합계 |
|------|---------|--------|--------|--------|--------|------|
| 백엔드 애플리케이션 | 1,132 | 214 | 547 | 118 | 399 | 2,410 |
| 백엔드 테스트 | 0 | 185 | 230 | 215 | 274 | 904 |
| 프론트엔드 코드 | 0 | 0 | 0 | 1,438 | 149 | 1,587 |
| 인프라 설정 | 31 | 30 | 29 | 0 | 0 | 90 |
| **총합** | **1,163** | **429** | **806** | **1,771** | **822** | **4,991** |

> Week 4 백엔드: kg_build_store(115) + service(174) + kg_build router(57) + schemas/exceptions/main/migrations 변경(53) = 399행
> Week 4 프론트엔드: types(23) + client(20) + ReviewPage(106) = 149행
> Week 4 테스트: test_kg_build(274)

---

## 12. 다음 단계 (Week 5)

| Week 5 작업 | 설명 |
|-------------|------|
| Cypher 쿼리 API | 3개 템플릿 쿼리 API 엔드포인트 |
| Q&A 프론트엔드 | 질문 선택 → Cypher 실행 → 결과 표시 |
| CSV 벌크 임포트 | 대용량 데이터 CSV 업로드 + 검증 |
| 프론트엔드 Q&A 페이지 | ReviewPage → QueryPage 전환 |

---

*Week 4 — KG Builder Job 모델 + 샘플 데이터 + 프론트엔드 Build KG 버튼 활성화 완성*
