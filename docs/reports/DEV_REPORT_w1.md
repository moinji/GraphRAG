# Week 1 개발 보고서 — 프로젝트 부트스트랩 + DDL 파서
> 작성일: 2026-02-24 | 목적: FastAPI API 서버 + 인프라 확장 + 파서 테스트

---

## 1. 요약

Demo v0의 코어 파이프라인 위에 **FastAPI 서버, Docker 서비스 3종(Neo4j/PG/Redis), pytest 16개**를 추가하여 정규 개발 기반을 완성했습니다.

| 지표 | 목표 | 실제 | 상태 |
|------|------|------|------|
| Docker 서비스 (healthy) | 3 | 3 | PASS |
| Health 엔드포인트 | healthy | healthy | PASS |
| DDL 업로드 → 테이블 수 | 12 | 12 | PASS |
| DDL 업로드 → FK 수 | 15 | 15 | PASS |
| 파서 단위 테스트 | 10/10 | 10/10 | PASS |
| API 통합 테스트 | 3/3 | 6/6* | PASS |
| demo.py 하위 호환 | All 5 steps | All 5 steps | PASS |

> *API 테스트는 asyncio + trio 두 백엔드에서 자동 실행되어 6건으로 집계

---

## 2. 구현 범위

### 신규 파일 (10개)

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `app/config.py` | 30 | pydantic-settings 환경 설정 통합 |
| `app/exceptions.py` | 30 | DDLParseError(422), FileTooLargeError(413) + FastAPI 핸들러 |
| `app/main.py` | 43 | FastAPI 앱 팩토리 (CORS, 에러핸들러, 라우터) |
| `app/routers/__init__.py` | 0 | 패키지 init |
| `app/routers/health.py` | 72 | `GET /api/v1/health` — Neo4j/PG/Redis 연결 체크 |
| `app/routers/ddl.py` | 39 | `POST /api/v1/ddl/upload` — DDL 파일 수신→파싱 |
| `tests/__init__.py` | 0 | 패키지 init |
| `tests/conftest.py` | 31 | pytest 픽스처 (ecommerce_ddl, app, async client) |
| `tests/test_ddl_parser.py` | 103 | 파서 단위 테스트 10개 |
| `tests/test_api_ddl.py` | 51 | API 통합 테스트 3개 |
| **합계** | **399** | |

### 수정 파일 (3개)

| 파일 | 변경 내용 |
|------|----------|
| `docker-compose.yml` | postgres:16-alpine, redis:7-alpine 서비스 + healthcheck 추가 |
| `requirements.txt` | fastapi, uvicorn, pydantic-settings 등 8개 패키지 추가 |
| `.env.example` | PG/Redis/App 환경변수 8개 추가 |

---

## 3. API 엔드포인트

### `GET /api/v1/health`

```json
{
  "status": "healthy",
  "neo4j":    {"status": "ok", "latency_ms": 80.6},
  "postgres": {"status": "ok", "latency_ms": 33.0},
  "redis":    {"status": "ok", "latency_ms": 37.9}
}
```

- 3개 서비스 중 하나라도 실패 시 `"status": "degraded"` 반환
- 동기 드라이버 사용 (psycopg2, redis-py) — FastAPI threadpool 위임

### `POST /api/v1/ddl/upload`

| 시나리오 | 응답 코드 | 동작 |
|----------|----------|------|
| 정상 .sql 파일 | 200 | `ERDSchema` JSON (tables + foreign_keys) |
| 빈 파일 | 422 | `{"detail": "Uploaded file is empty"}` |
| 비UTF-8 바이너리 | 422 | `{"detail": "File is not valid UTF-8 text"}` |
| 10MB 초과 | 413 | `{"detail": "File exceeds maximum size of 10MB"}` |
| 파싱 실패 | 422 | `{"detail": "DDL parsing failed: ..."}` |

---

## 4. 테스트 결과 상세

### 파서 단위 테스트 (10개)

| # | 테스트명 | 검증 내용 | 결과 |
|---|---------|----------|------|
| 1 | `test_ecommerce_table_count` | 전체 DDL → 12 tables | PASS |
| 2 | `test_ecommerce_fk_count` | 전체 DDL → 15 FKs | PASS |
| 3 | `test_single_table_no_fk` | 단일 테이블, FK 없음 | PASS |
| 4 | `test_column_types_preserved` | SERIAL/VARCHAR/DECIMAL 타입 보존 | PASS |
| 5 | `test_nullable_detection` | NOT NULL vs nullable 구분 | PASS |
| 6 | `test_self_referential_fk` | categories.parent_id → categories.id | PASS |
| 7 | `test_multiple_fks_same_table` | products: category_id + supplier_id | PASS |
| 8 | `test_nullable_fk` | orders.coupon_id (nullable FK) | PASS |
| 9 | `test_empty_ddl` | 빈 입력 → tables=[], fks=[] | PASS |
| 10 | `test_non_create_ignored` | DROP/ALTER/INSERT 무시, CREATE만 파싱 | PASS |

### API 통합 테스트 (3개)

| # | 테스트명 | 검증 내용 | 결과 |
|---|---------|----------|------|
| 1 | `test_upload_valid_ddl` | 정상 업로드 → 200 + 12 tables, 15 FKs | PASS |
| 2 | `test_upload_empty_file` | 빈 파일 → 422 | PASS |
| 3 | `test_upload_binary_file` | 비UTF-8 바이너리 → 422 | PASS |

```
============================= 16 passed in 0.60s ==============================
```

---

## 5. 인프라 구성

### Docker Compose 서비스

| 서비스 | 이미지 | 포트 | Healthcheck | 용도 |
|--------|--------|------|-------------|------|
| neo4j | neo4j:5-community | 7474, 7687 | cypher-shell RETURN 1 | Knowledge Graph 저장 |
| postgres | postgres:16-alpine | 5432 | pg_isready | 메타데이터 (Week 2~) |
| redis | redis:7-alpine | 6379 | redis-cli ping | 캐시/Job 큐 (Week 4~) |

### 의존성 추가

| 패키지 | 버전 | 용도 |
|--------|------|------|
| fastapi | ≥0.110.0 | REST API 프레임워크 |
| uvicorn[standard] | ≥0.27.0 | ASGI 서버 |
| pydantic-settings | ≥2.0.0 | 환경 변수 설정 |
| python-multipart | ≥0.0.6 | 파일 업로드 (UploadFile) |
| psycopg2-binary | ≥2.9.0 | PostgreSQL 드라이버 |
| redis | ≥5.0.0 | Redis 드라이버 |
| pytest | ≥8.0.0 | 테스트 프레임워크 |
| httpx | ≥0.27.0 | 비동기 테스트 클라이언트 |

---

## 6. DoD 체크리스트

| # | 검증 항목 | 명령어 | 결과 |
|---|----------|--------|------|
| 1 | Docker 서비스 3종 healthy | `docker compose up -d && docker compose ps` | neo4j, postgres, redis 모두 healthy |
| 2 | FastAPI 서버 시작 | `uvicorn app.main:app --reload` | Started, 8000 포트 |
| 3 | Health 체크 | `curl /api/v1/health` | `{"status": "healthy", ...}` |
| 4 | DDL 업로드 | `curl -X POST /api/v1/ddl/upload -F "file=@demo_ecommerce.sql"` | 200, tables: 12, FKs: 15 |
| 5 | 파서 테스트 | `pytest tests/ -v` | 16/16 PASSED (0.60s) |
| 6 | demo.py 호환 | `python demo.py` | All 5 steps passed |

---

## 7. 아키텍처 결정 기록

| # | 결정 | 근거 |
|---|------|------|
| 1 | **기존 `parse_ddl()` 직접 호출** | 서비스 레이어 불필요, 라우터에서 바로 호출하여 단순화 |
| 2 | **PG/Redis는 연결 확인만** | Week 1에서는 테이블 미생성, Week 2에서 ontology_versions 등 추가 |
| 3 | **동기 health check** | psycopg2/redis-py 동기 드라이버 사용, FastAPI threadpool 처리 |
| 4 | **`create_app()` 팩토리 패턴** | 테스트용 앱 인스턴스 분리, 향후 설정 주입 용이 |
| 5 | **CORS localhost:3000 허용** | Week 3 React 프론트엔드 대비 |
| 6 | **DDL 사이즈 가드 10MB** | 환경 변수(`DDL_MAX_SIZE_MB`)로 설정 가능 |

---

## 8. 파일 구조 (Week 1 후)

```
GraphRAG/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py                ← [NEW] pydantic-settings 설정
│   │   ├── exceptions.py            ← [NEW] 커스텀 예외 + 핸들러
│   │   ├── main.py                  ← [NEW] FastAPI 앱 팩토리
│   │   ├── models/
│   │   │   └── schemas.py
│   │   ├── routers/                 ← [NEW]
│   │   │   ├── __init__.py
│   │   │   ├── health.py            ← GET /api/v1/health
│   │   │   └── ddl.py               ← POST /api/v1/ddl/upload
│   │   ├── ddl_parser/
│   │   │   └── parser.py
│   │   ├── ontology/
│   │   │   └── fk_rule_engine.py
│   │   ├── data_generator/
│   │   │   └── generator.py
│   │   ├── kg_builder/
│   │   │   └── loader.py
│   │   └── query/
│   │       ├── templates.py
│   │       └── executor.py
│   ├── tests/                       ← [NEW]
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_ddl_parser.py       ← 파서 단위 테스트 10개
│   │   └── test_api_ddl.py          ← API 통합 테스트 3개
│   ├── demo.py
│   └── demo_ecommerce.sql
├── docker-compose.yml               ← [MOD] +postgres, +redis
├── requirements.txt                 ← [MOD] +8 패키지
└── .env.example                     ← [MOD] +8 환경변수
```

---

## 9. 코드 규모 누적

| 구분 | Demo v0 | Week 1 추가 | 합계 |
|------|---------|------------|------|
| 애플리케이션 코드 | 1,132 lines | 214 lines | 1,346 lines |
| 테스트 코드 | 0 lines | 185 lines | 185 lines |
| 인프라 설정 | 31 lines | +30 lines | 61 lines |
| **총합** | **1,163 lines** | **429 lines** | **1,592 lines** |

---

## 10. 다음 단계 (Week 2)

| Week 2 작업 | 설명 |
|-------------|------|
| FK 규칙 온톨로지 API | `POST /api/v1/ontology/generate` — ERDSchema → OntologySpec |
| LLM 보강 (Claude) | FK 규칙 엔진 결과를 Claude로 검증/보강 |
| PG 메타데이터 저장 | ontology_versions 테이블, 버전 관리 |
| 평가 리포트 자동화 | 온톨로지 품질 지표 (커버리지, 관계 정확도) |
| 테스트 확장 | 온톨로지 엔진 단위 테스트 추가 |

---

*Week 1 — FastAPI 부트스트랩 + DDL 파서 테스트 완성*
