# Week 3 개발 보고서 — 온톨로지 리뷰 UI + Auto/Review 모드 + 버전 관리 API
> 작성일: 2026-02-24 | 목적: React 프론트엔드 (테이블 뷰 CRUD) + Auto/Review 모드 + 백엔드 버전 관리 API

---

## 1. 요약

백엔드에 **온톨로지 버전 관리 API (GET/PUT/POST)**를 추가하고, **Vite + React + TypeScript + Tailwind + shadcn/ui** 기반 프론트엔드를 구축하여 온톨로지 리뷰 워크플로(Upload → Review → Approve)를 완성했습니다.

| 지표 | 목표 | 실제 | 상태 |
|------|------|------|------|
| GET /ontology/versions/{id} | 200 | 200 | PASS |
| PUT /ontology/versions/{id} (draft) | 200 | 200 | PASS |
| PUT /ontology/versions/{id} (approved) | 409 | 409 | PASS |
| POST /ontology/versions/{id}/approve | 200 | 200 | PASS |
| 버전 API 테스트 | 10/10 | 10/10 | PASS |
| 전체 백엔드 테스트 | 46+ | 56 | PASS |
| 프론트엔드 빌드 (`npm run build`) | 에러 0 | 에러 0 | PASS |
| demo.py 하위 호환 | All 5 steps | All 5 steps | PASS |

> 테스트 56건 = 28개 고유 테스트 × 2 async 백엔드 (asyncio + trio)

---

## 2. 구현 범위

### 백엔드 신규 파일 (3개)

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `app/db/migrations.py` | 31 | PG 스키마 마이그레이션 (status 컬럼) |
| `app/routers/ontology_versions.py` | 87 | GET/PUT/POST 버전 관리 엔드포인트 |
| `tests/test_ontology_versions.py` | 215 | 버전 API 테스트 10개 |
| **소계** | **333** | |

### 백엔드 수정 파일 (4개)

| 파일 | 변경 내용 |
|------|----------|
| `app/exceptions.py` | `VersionNotFoundError`(404), `VersionConflictError`(409) + 핸들러 2개 추가 |
| `app/db/pg_client.py` | `_CREATE_TABLE_SQL`에 status 컬럼 추가, `update_version()`, `approve_version()` 2개 함수 추가 |
| `app/main.py` | `ontology_versions` 라우터 등록, 예외 핸들러 등록, startup에 `run_migrations()` 추가, 버전 0.3.0 |
| `app/models/schemas.py` | `OntologyVersionResponse`, `OntologyUpdateRequest`, `OntologyUpdateResponse`, `OntologyApproveResponse` 4개 모델 추가 |

### 프론트엔드 신규 파일 (12개)

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `src/types/ontology.ts` | 115 | TS 타입 (백엔드 Pydantic 미러) |
| `src/api/client.ts` | 73 | API 클라이언트 (fetch wrapper 5개) |
| `src/App.tsx` | 50 | 루트 (upload → review 상태 전환) |
| `src/pages/UploadPage.tsx` | 117 | DDL 업로드 + 온톨로지 생성 |
| `src/pages/ReviewPage.tsx` | 307 | 메인 리뷰 (Auto/Review 모드 + CRUD) |
| `src/components/ModeToggle.tsx` | 22 | Auto/Review 모드 탭 토글 |
| `src/components/EvalCard.tsx` | 52 | 평가 지표 카드 (8개 메트릭) |
| `src/components/NodeTypeTable.tsx` | 88 | 노드 테이블 (CRUD) |
| `src/components/RelationshipTable.tsx` | 125 | 관계 테이블 (CRUD + 방향 반전) |
| `src/components/EditNodeDialog.tsx` | 182 | 노드 추가/편집 다이얼로그 |
| `src/components/EditRelationshipDialog.tsx` | 257 | 관계 추가/편집 다이얼로그 |
| `src/components/DiffPanel.tsx` | 50 | LLM diff 표시 (before/after) |
| **소계** | **1,438** | |

### 기타 수정

| 파일 | 변경 내용 |
|------|----------|
| `.gitignore` | `node_modules/`, `dist/` 추가 |

---

## 3. 아키텍처 — 온톨로지 리뷰 워크플로

```
┌──────────────────────────────────────────────────────────┐
│  Frontend (localhost:3000)                                │
│                                                          │
│  ┌─────────────┐    ┌──────────────────────────────────┐ │
│  │ UploadPage   │───▶│ ReviewPage                       │ │
│  │              │    │                                  │ │
│  │ 1. DDL 업로드 │    │ ┌─────────┐  ┌───────────────┐  │ │
│  │ 2. ERD 요약   │    │ │Auto Mode│  │Review Mode    │  │ │
│  │ 3. Generate  │    │ │ 요약카드  │  │ 노드 테이블    │  │ │
│  │              │    │ │ 자동승인  │  │ 관계 테이블    │  │ │
│  └─────────────┘    │ └─────────┘  │ 변경사항 탭    │  │ │
│                      │              │ 저장 + 승인    │  │ │
│                      │              └───────────────┘  │ │
│                      └──────────────────────────────────┘ │
└───────────────┬──────────────────────────────────────────┘
                │  Vite 프록시 (/api → :8000)
┌───────────────▼──────────────────────────────────────────┐
│  Backend (localhost:8000)                                 │
│                                                          │
│  POST /ddl/upload           → ERDSchema                  │
│  POST /ontology/generate    → OntologyGenerateResponse   │
│  GET  /ontology/versions/N  → OntologyVersionResponse    │
│  PUT  /ontology/versions/N  → 수정 저장 (draft만)         │
│  POST /ontology/versions/N/approve → 승인 (draft→approved)│
│                                                          │
│  ┌────────────────┐  ┌────────────────┐                  │
│  │ evaluate()     │  │ PostgreSQL     │                  │
│  │ 골든 대비 재평가 │  │ ontology_      │                  │
│  │ (PUT 시 자동)   │  │ versions       │                  │
│  └────────────────┘  │ + status 컬럼  │                  │
│                       └────────────────┘                  │
└──────────────────────────────────────────────────────────┘
```

### 핵심 설계 원칙

| # | 원칙 | 구현 |
|---|------|------|
| 1 | **react-router 미사용** | 2페이지(upload/review)만 있으므로 상태 변수로 전환. Week 5 Q&A 추가 시 도입 |
| 2 | **로컬 React state만 사용** | Redux/Zustand 불필요. 단방향 데이터 흐름 (API → ReviewPage → 자식) |
| 3 | **PUT 시 평가 재계산** | 수정된 온톨로지로 `evaluate()` 재실행, eval_json 갱신 |
| 4 | **Draft/Approved 2상태** | rejected 없음 (다시 편집 = draft 유지). 1인 PoC에서 충분 |
| 5 | **Vite 프록시** | `/api/v1/...` → localhost:8000 프록시. 운영 환경 리버스 프록시와 동일 패턴 |
| 6 | **KG 빌드 버튼 Week 4 stub** | disabled 상태로 표시, Week 4에서 구현 |

---

## 4. API 엔드포인트 (신규 3개)

### `GET /api/v1/ontology/versions/{version_id}`

**Response (200):**
```json
{
  "version_id": 1,
  "erd_hash": "abc123...",
  "ontology": {"node_types": [...], "relationship_types": [...]},
  "eval_report": {"critical_error_rate": 0.0, "fk_relationship_coverage": 1.0, ...},
  "status": "draft",
  "created_at": "2026-02-25T10:00:00"
}
```
**404:** `{"detail": "Version 999 not found"}`

### `PUT /api/v1/ontology/versions/{version_id}`

**Request:**
```json
{"ontology": {"node_types": [...], "relationship_types": [...]}}
```
**Response (200):** `{"version_id": 1, "status": "draft", "updated": true}`

| 상태 코드 | 조건 |
|-----------|------|
| 200 | draft 상태 버전 수정 성공 (eval 재계산 포함) |
| 404 | 버전 없음 |
| 409 | 이미 approved된 버전 수정 시도 |
| 422 | 잘못된 요청 바디 |

### `POST /api/v1/ontology/versions/{version_id}/approve`

**Response (200):** `{"version_id": 1, "status": "approved"}`

| 상태 코드 | 조건 |
|-----------|------|
| 200 | draft → approved 전환 성공 |
| 404 | 버전 없음 |
| 409 | 이미 approved된 버전 |

---

## 5. PG 스키마 변경

### 마이그레이션

```sql
ALTER TABLE ontology_versions
ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'draft' NOT NULL;
```

- `_CREATE_TABLE_SQL`도 status 컬럼 포함으로 업데이트 (신규 설치 대응)
- `run_migrations()` → startup에서 `ensure_table()` 후 호출, 멱등

### 추가 CRUD 함수

| 함수 | 설명 |
|------|------|
| `update_version(version_id, ontology_json, eval_json)` | UPDATE WHERE status='draft', rowcount 기반 bool 반환 |
| `approve_version(version_id)` | UPDATE status='approved' WHERE status='draft' |

---

## 6. 프론트엔드 구조

### 기술 스택

| 기술 | 버전 | 용도 |
|------|------|------|
| Vite | 7.3 | 빌드 도구 + HMR + API 프록시 |
| React | 19 | UI 라이브러리 |
| TypeScript | 5.x | 타입 안전성 |
| Tailwind CSS | 4.x | 유틸리티 CSS |
| shadcn/ui | latest | 컴포넌트 라이브러리 (table, badge, button, card, tabs, dialog, input, select, label, checkbox) |

### 페이지 흐름

```
UploadPage                          ReviewPage
┌──────────────────┐               ┌───────────────────────────────┐
│ 1. 파일 선택       │               │ [Auto] [Review]  모드 토글     │
│ 2. "Upload" 클릭   │──generate──▶ │                               │
│ 3. ERD 요약 표시    │               │ ┌───────────────────────────┐ │
│    (12 tables,     │               │ │ EvalCard (8개 지표)        │ │
│     15 FKs)        │               │ └───────────────────────────┘ │
│ 4. LLM 보강 체크박스│               │                               │
│ 5. "Generate" 클릭 │               │ Auto: 요약 + 자동승인 버튼     │
└──────────────────┘               │ Review: 노드/관계/변경사항 탭   │
                                    │   + 편집/삭제/반전/추가         │
                                    │   + 저장 + 승인 버튼            │
                                    └───────────────────────────────┘
```

### 컴포넌트 계층

```
App.tsx
├── UploadPage.tsx
│   └── uploadDDL() → generateOntology() → onGenerated()
└── ReviewPage.tsx
    ├── ModeToggle.tsx           (Auto | Review 탭)
    ├── EvalCard.tsx             (8개 평가 지표 그리드)
    ├── NodeTypeTable.tsx        (이름, 원본 테이블, 속성 수, [편집][삭제])
    │   └── EditNodeDialog.tsx   (name, source_table, 속성 서브테이블)
    ├── RelationshipTable.tsx    (이름, 방향, derivation 배지, [반전][편집][삭제])
    │   └── EditRelationshipDialog.tsx  (source/target select, 속성 서브테이블)
    └── DiffPanel.tsx            (LLM before/after, reason)
```

### Derivation 배지 색상

| derivation | 배지 색상 | CSS |
|------------|----------|-----|
| `fk_direct` | 파란색 | `bg-blue-100 text-blue-800` |
| `fk_join_table` | 파란색 | `bg-blue-100 text-blue-800` |
| `llm_suggested` | 주황색 | `bg-orange-100 text-orange-800` |

### API 클라이언트 (5개 함수)

| 함수 | HTTP | 엔드포인트 |
|------|------|-----------|
| `uploadDDL(file)` | POST | `/api/v1/ddl/upload` |
| `generateOntology(erd, skipLlm)` | POST | `/api/v1/ontology/generate` |
| `getVersion(id)` | GET | `/api/v1/ontology/versions/{id}` |
| `updateVersion(id, ontology)` | PUT | `/api/v1/ontology/versions/{id}` |
| `approveVersion(id)` | POST | `/api/v1/ontology/versions/{id}/approve` |

---

## 7. 테스트 결과 상세

### 버전 API 테스트 (10개)

| # | 테스트명 | 검증 내용 | 결과 |
|---|---------|----------|------|
| 1 | `test_get_version_success` | GET → 200, ontology + status="draft" | PASS |
| 2 | `test_get_version_not_found` | GET /999 → 404, "999" in detail | PASS |
| 3 | `test_update_version_success` | PUT 유효한 ontology → 200, updated=true | PASS |
| 4 | `test_update_version_not_found` | PUT /999 → 404 | PASS |
| 5 | `test_update_version_already_approved` | PUT (approved) → 409, "approved" in detail | PASS |
| 6 | `test_approve_version_success` | POST approve → 200, status="approved" | PASS |
| 7 | `test_approve_version_not_found` | POST /999/approve → 404 | PASS |
| 8 | `test_approve_version_already_approved` | POST approve (이미 approved) → 409 | PASS |
| 9 | `test_update_version_invalid_body` | PUT 잘못된 JSON → 422 | PASS |
| 10 | `test_update_recalculates_eval` | PUT 후 eval_json 재계산 (critical_error_rate=0.0) | PASS |

### 전체 테스트 실행

```
======================= 56 passed, 70 warnings in 1.99s =======================
```

| 테스트 파일 | 고유 테스트 수 | 실행 수 (×2 backend) | 결과 |
|------------|-------------|---------------------|------|
| `test_ddl_parser.py` | 10 | 10 | 10 PASS |
| `test_api_ddl.py` | 3 | 6 | 6 PASS |
| `test_ontology.py` | 16 (4 API ×2) | 20 | 20 PASS |
| `test_ontology_versions.py` | 10 (×2) | 20 | 20 PASS |
| **합계** | **39** | **56** | **56 PASS** |

---

## 8. Draft/Approved 상태 워크플로

```
           ┌────────────────────────────────────────┐
           │                                        │
    생성 ──▶│  draft                                  │
           │  - 온톨로지 편집 가능 (PUT)               │
           │  - 노드/관계 CRUD (로컬 → 저장)          │
           │  - eval 재계산 (PUT 시 자동)             │
           │                                        │
           └──────────────┬─────────────────────────┘
                          │ POST /approve
                          ▼
           ┌────────────────────────────────────────┐
           │                                        │
           │  approved                               │
           │  - 편집 불가 (PUT → 409)                 │
           │  - UI 편집 버튼 비활성화                   │
           │  - 상태 배지 "approved"                   │
           │  - KG 빌드 준비 완료 (Week 4)             │
           │                                        │
           └────────────────────────────────────────┘
```

- **rejected 상태 없음**: 수정이 필요하면 draft 상태에서 계속 편집
- **1인 PoC에서 충분**: 멀티유저 승인 플로는 향후 확장

---

## 9. DoD 체크리스트

| # | 검증 항목 | 명령어 | 결과 |
|---|----------|--------|------|
| 1 | 백엔드 테스트 | `cd backend && pytest tests/ -v` | 56 passed |
| 2 | 프론트엔드 빌드 | `cd frontend && npm run build` | 에러 없이 빌드 성공 |
| 3 | GET 버전 조회 | `GET /api/v1/ontology/versions/1` → 200 | PASS |
| 4 | PUT 수정 저장 (draft) | `PUT /api/v1/ontology/versions/1` → 200, updated=true | PASS |
| 5 | PUT 수정 저장 (approved) | `PUT /api/v1/ontology/versions/1` → 409 | PASS |
| 6 | POST 승인 | `POST /api/v1/ontology/versions/1/approve` → 200, status=approved | PASS |
| 7 | demo.py 하위 호환 | `python demo.py` → All 5 steps passed | PASS |

---

## 10. 파일 구조 (Week 3 후)

```
GraphRAG/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── exceptions.py                ← [MOD] +VersionNotFoundError, +VersionConflictError
│   │   ├── main.py                      ← [MOD] +versions 라우터, +migration startup, v0.3.0
│   │   ├── models/
│   │   │   └── schemas.py               ← [MOD] +4 버전 API 모델
│   │   ├── routers/
│   │   │   ├── health.py
│   │   │   ├── ddl.py
│   │   │   ├── ontology.py
│   │   │   └── ontology_versions.py     ← [NEW] GET/PUT/POST 버전 관리
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
│   │   │   ├── pg_client.py             ← [MOD] +status 컬럼, +update/approve
│   │   │   └── migrations.py            ← [NEW] PG 스키마 마이그레이션
│   │   ├── data_generator/
│   │   │   └── generator.py
│   │   ├── kg_builder/
│   │   │   └── loader.py
│   │   └── query/
│   │       ├── templates.py
│   │       └── executor.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_ddl_parser.py
│   │   ├── test_api_ddl.py
│   │   ├── test_ontology.py
│   │   └── test_ontology_versions.py    ← [NEW] 버전 API 테스트 10개
│   ├── demo.py
│   └── demo_ecommerce.sql
├── frontend/                             ← [NEW] Vite + React + TS
│   ├── src/
│   │   ├── main.tsx
│   │   ├── index.css                    (Tailwind + shadcn)
│   │   ├── App.tsx                      ← 루트 (upload ↔ review)
│   │   ├── types/
│   │   │   └── ontology.ts             ← TS 타입 미러
│   │   ├── api/
│   │   │   └── client.ts               ← fetch wrapper 5개
│   │   ├── pages/
│   │   │   ├── UploadPage.tsx           ← DDL 업로드 + 생성
│   │   │   └── ReviewPage.tsx           ← Auto/Review 모드 + CRUD
│   │   ├── components/
│   │   │   ├── ModeToggle.tsx           ← Auto/Review 탭
│   │   │   ├── EvalCard.tsx             ← 평가 지표 카드
│   │   │   ├── NodeTypeTable.tsx        ← 노드 CRUD 테이블
│   │   │   ├── RelationshipTable.tsx    ← 관계 CRUD 테이블
│   │   │   ├── EditNodeDialog.tsx       ← 노드 편집 다이얼로그
│   │   │   ├── EditRelationshipDialog.tsx ← 관계 편집 다이얼로그
│   │   │   ├── DiffPanel.tsx            ← LLM diff 표시
│   │   │   └── ui/                      (shadcn 컴포넌트 10개)
│   │   └── lib/
│   │       └── utils.ts                 (shadcn cn() 유틸)
│   ├── vite.config.ts                   ← Tailwind + 프록시 설정
│   ├── tsconfig.json
│   ├── tsconfig.app.json                ← @/ 경로 별칭
│   ├── package.json
│   └── components.json                  (shadcn 설정)
├── docker-compose.yml
├── requirements.txt
└── .gitignore                           ← [MOD] +node_modules/, +dist/
```

---

## 11. 코드 규모 누적

| 구분 | Demo v0 | Week 1 | Week 2 | Week 3 | 합계 |
|------|---------|--------|--------|--------|------|
| 백엔드 애플리케이션 | 1,132 | 214 | 547 | 118 | 2,011 |
| 백엔드 테스트 | 0 | 185 | 230 | 215 | 630 |
| 프론트엔드 코드 | 0 | 0 | 0 | 1,438 | 1,438 |
| 인프라 설정 | 31 | 30 | 29 | 0 | 90 |
| **총합** | **1,163** | **429** | **806** | **1,771** | **4,169** |

---

## 12. 다음 단계 (Week 4)

| Week 4 작업 | 설명 |
|-------------|------|
| KG 빌드 연동 | 승인된 온톨로지 → Neo4j KG 빌드 API |
| 샘플 데이터 로딩 | data_generator → Neo4j 노드/관계 MERGE |
| 프론트엔드 KG 빌드 버튼 활성화 | "Build KG" → POST API → 진행률 표시 |
| Cypher 쿼리 실행 | 3개 템플릿 쿼리 API 연동 |

---

*Week 3 — 온톨로지 리뷰 UI + Auto/Review 모드 + 버전 관리 API 완성*
