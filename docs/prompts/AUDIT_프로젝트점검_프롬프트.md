# GraphRAG 프로젝트 오류 점검 프롬프트

아래 프롬프트를 Claude Code에 그대로 붙여넣어 사용합니다.
프로젝트 루트에서 실행해야 모든 파일을 읽을 수 있습니다.

---

## 프롬프트

```
너는 시니어 백엔드 엔지니어 + 보안 감사자 역할이야.
아래 프로젝트의 소스 코드를 전수 조사해서, 버그·보안 취약점·장애 위험을 찾아줘.

"아마 괜찮을 것이다"는 넘어가지 말고, 코드를 직접 읽고 근거를 대.
반드시 해당 파일명과 줄 번호를 함께 적어.

---

## 프로젝트 정보

- Python 3.11+ / FastAPI 백엔드 + React/TS 프론트엔드
- DB: Neo4j 5 (그래프) + PostgreSQL 16 (메타데이터)
- 외부 API: OpenAI (gpt-4o / gpt-4o-mini)
- 배포: Docker Compose → GCP VM (Nginx 리버스 프록시)
- 인메모리 저장소: CSV 세션 (_csv_sessions dict), KG 빌드 잡 (_jobs dict)
- 싱글 프로세스 (uvicorn 1 worker)

## 점검 대상 파일 구조

```
backend/app/
├── main.py                          — FastAPI app factory, CORS, error handlers
├── config.py                        — pydantic-settings (env → Settings)
├── exceptions.py                    — 10개 커스텀 예외 + handler
├── models/schemas.py                — 30+ Pydantic 모델
├── db/
│   ├── neo4j_client.py              — Neo4j 싱글톤 드라이버
│   ├── pg_client.py                 — PG ontology_versions CRUD
│   ├── kg_build_store.py            — PG kg_builds CRUD
│   └── migrations.py                — PG 스키마 마이그레이션
├── ddl_parser/parser.py             — sqlglot + regex DDL 파싱
├── ontology/
│   ├── fk_rule_engine.py            — FK → 온톨로지 변환 규칙
│   ├── pipeline.py                  — 2단계 오케스트레이터
│   ├── llm_enricher.py              — OpenAI API 호출
│   └── prompts.py                   — LLM 프롬프트
├── csv_import/parser.py             — CSV 파싱 + 인메모리 세션 관리
├── data_generator/generator.py      — 샘플 데이터 생성 + FK 무결성 검증
├── kg_builder/
│   ├── service.py                   — KG 빌드 잡 오케스트레이터 (인메모리 + PG)
│   └── loader.py                    — Neo4j UNWIND+MERGE 배치 로드
├── query/
│   ├── template_registry.py         — 13개 Cypher 템플릿
│   ├── slot_filler.py               — 슬롯 검증 + Cypher 렌더링
│   ├── router_rules.py              — regex 기반 규칙 라우터
│   ├── router_llm.py                — OpenAI LLM 라우터
│   ├── router.py                    — 하이브리드 라우터 오케스트레이터
│   ├── pipeline.py                  — Q&A 전체 파이프라인
│   ├── local_search.py              — B안 로컬 서치
│   ├── local_prompts.py             — B안 프롬프트
│   └── demo_cache.py                — 데모 질문 캐시
├── evaluation/
│   ├── evaluator.py                 — 골든 데이터 비교
│   ├── golden_ecommerce.py          — 9 노드 + 12 관계 골든셋
│   ├── qa_golden.py                 — 50 QA 골든 페어
│   └── qa_evaluator.py              — QA 평가 엔진
├── routers/
│   ├── health.py                    — GET /health
│   ├── ddl.py                       — POST /ddl/upload
│   ├── ontology.py                  — POST /ontology/generate
│   ├── ontology_versions.py         — GET/PUT/POST /ontology/versions/{id}
│   ├── kg_build.py                  — POST/GET /kg/build
│   ├── query.py                     — POST /query
│   ├── csv_upload.py                — POST /csv/upload
│   ├── evaluation.py                — POST /evaluation/run, GET /evaluation/golden
│   └── graph.py                     — GET /graph/stats, /full, /neighbors, DELETE /reset
frontend/src/
├── api/client.ts                    — fetch 래퍼 10개
├── pages/                           — UploadPage, ReviewPage, QueryPage, ExplorePage
├── components/review/               — NodeTypeTable, RelationshipTable, EditDialog 등
├── types/ontology.ts, graph.ts      — TS 타입
└── constants.ts                     — 공유 상수
```

---

## 점검 체크리스트 (9개 카테고리)

### 1. 보안 취약점
반드시 확인할 것:
- [ ] **Cypher 인젝션**: slot_filler.py의 화이트리스트가 모든 경로를 커버하는가? graph.py에서 f-string으로 Cypher를 조립하는 곳이 있는가? label, id_val 등 사용자 입력이 Cypher에 직접 삽입되는가?
- [ ] **CORS 설정**: main.py의 allow_origins가 와일드카드("*")가 되는 경우가 있는가? CORS_ORIGINS 환경변수 미설정 시 기본값은 안전한가?
- [ ] **SQL 인젝션**: pg_client.py, kg_build_store.py에서 파라미터 바인딩을 사용하는가, 아니면 f-string으로 SQL을 조립하는가?
- [ ] **파일 업로드**: ddl.py, csv_upload.py에서 파일 크기 제한이 실제로 동작하는가? 파일명에 경로 탐색(../../../)이 가능한가?
- [ ] **인증/인가**: DELETE /graph/reset 같은 파괴적 엔드포인트에 인증이 있는가?
- [ ] **비밀 노출**: .env.example에 실제 비밀번호가 하드코딩되어 있는가? config.py에 기본 비밀번호가 있는가?
- [ ] **의존성 취약점**: requirements.txt의 패키지 버전에 알려진 CVE가 있는가?

### 2. 동시성 / 레이스 컨디션
- [ ] **인메모리 dict 경합**: _csv_sessions, _jobs가 BackgroundTasks와 API 핸들러에서 동시에 읽기/쓰기되는가? GIL만으로 안전한가, 아니면 Lock이 필요한가?
- [ ] **Neo4j 싱글톤**: neo4j_client.py의 get_driver()가 여러 스레드에서 동시 호출 시 드라이버가 2개 생성될 수 있는가?
- [ ] **KG 빌드 동시 실행**: 두 사용자가 동시에 Build KG를 누르면? MATCH (n) DETACH DELETE n이 다른 빌드의 데이터를 날릴 수 있는가?
- [ ] **CSV 세션 1회 소비**: kg_build.py에서 get_session → delete_session 사이에 다른 요청이 같은 session_id를 사용할 수 있는가?

### 3. 에러 핸들링 / 복원력
- [ ] **PG 장애 시 동작**: pg_client.py 호출이 실패하면 어떻게 되는가? best-effort 패턴이 일관되게 적용되어 있는가?
- [ ] **Neo4j 장애 시 동작**: Neo4j가 다운되면 health 엔드포인트, graph.py, query pipeline이 적절한 에러를 반환하는가, 아니면 500으로 크래시하는가?
- [ ] **OpenAI API 장애**: llm_enricher.py, router_llm.py, local_search.py에서 API 키 없음 / 타임아웃 / 429(rate limit)를 어떻게 처리하는가?
- [ ] **빌드 실패 시 롤백**: service.py에서 except 블록의 MATCH (n) DETACH DELETE n이 다른 성공한 빌드의 데이터까지 삭제하지 않는가?
- [ ] **on_event("startup") 실패**: PG 테이블 생성이 실패하면 앱이 시작은 되지만 이후 모든 PG 요청이 실패하는가?

### 4. 데이터 정합성
- [ ] **ERD와 CSV 불일치**: CSV 컬럼이 ERD에 없는 경우 warning만 주는데, ERD에 있지만 CSV에 없는 필수 컬럼은 어떻게 처리하는가?
- [ ] **온톨로지 버전 정합성**: 승인된 버전의 ontology로 KG를 빌드한 후, 다른 버전을 승인하고 다시 빌드하면 이전 KG가 완전히 삭제되는가?
- [ ] **노드 ID 충돌**: 서로 다른 테이블에서 같은 id 값을 가진 노드가 있으면 MERGE가 잘못 합쳐지는가? (예: Customer id=1과 Product id=1)
- [ ] **타입 변환 손실**: csv_import/parser.py의 _coerce_value에서 DECIMAL → float 변환 시 정밀도 손실이 있는가?

### 5. 성능 / 메모리
- [ ] **인메모리 누수**: _csv_sessions의 TTL(1h)과 MAX_SESSIONS(50)이 실제로 동작하는가? cleanup이 호출되지 않는 경로가 있는가?
- [ ] **_jobs dict 무한 성장**: MAX_COMPLETED_JOBS=100이지만, running 상태에서 멈춘 잡이 영원히 남는가?
- [ ] **대용량 CSV**: 50MB CSV 파일을 통째로 메모리에 올리는가? parse_csv_files가 content를 bytes로 받는데, 50MB × 50파일 = 2.5GB가 가능한가?
- [ ] **Neo4j UNWIND 배치 크기**: loader.py에서 모든 행을 한 번에 UNWIND하는가? 행이 많으면 Neo4j 메모리 초과가 발생하는가?
- [ ] **graph/full 엔드포인트**: limit=5000일 때 5000개 노드의 모든 edge를 한 번에 가져오면 응답이 얼마나 커지는가?

### 6. API 설계 / 엣지 케이스
- [ ] **빈 DDL 파일 업로드**: 0바이트 .sql 파일을 올리면 어떻게 되는가?
- [ ] **테이블 0개인 ERD**: DDL에 CREATE TABLE이 하나도 없으면 온톨로지 생성이 크래시하는가?
- [ ] **FK가 0개인 ERD**: FK 없는 단독 테이블만 있으면 relationship_types가 빈 배열이 되는가, 에러가 나는가?
- [ ] **중복 Build KG 요청**: 같은 version_id로 연속 2번 빌드하면 첫 번째 빌드 중에 두 번째 빌드가 DETACH DELETE로 데이터를 날리는가?
- [ ] **node_id 파싱**: graph.py의 node_id.split("_", 1)에서 Label이 "_"를 포함하면 잘못 분리되는가? (예: Order_Item_1)
- [ ] **QueryRequest.mode 검증**: mode에 "a", "b" 외의 값(예: "c", "", "ab")이 오면 어떻게 되는가?

### 7. 프론트엔드
- [ ] **에러 표시**: API가 500을 반환하면 사용자에게 의미 있는 메시지가 표시되는가, 아니면 빈 화면인가?
- [ ] **폴링 메모리 누수**: ReviewPage의 setInterval(2s)이 컴포넌트 언마운트 시 반드시 정리되는가?
- [ ] **XSS**: QueryPage에서 AI 답변을 dangerouslySetInnerHTML로 렌더링하는가, 아니면 텍스트로 처리하는가?
- [ ] **타입 불일치**: frontend/types/ontology.ts의 타입이 backend/schemas.py와 정확히 일치하는가? 누락된 필드가 있는가?
- [ ] **API 호출 경로**: client.ts의 BASE = '/api/v1'이 Nginx 프록시 설정과 일치하는가?

### 8. 배포 / 인프라
- [ ] **Docker 볼륨**: neo4j_data, postgres_data 볼륨이 named volume이어서 docker compose down으로 삭제되지 않는가?
- [ ] **Healthcheck 순서**: backend가 neo4j/postgres의 service_healthy를 기다리지만, depends_on만으로 충분한가? 타이밍 이슈는?
- [ ] **Neo4j 메모리**: Neo4j 5 community의 기본 힙 설정이 e2-medium(4GB)에서 충분한가?
- [ ] **Nginx 설정**: 파일 업로드 크기 제한(client_max_body_size)이 DDL 10MB + CSV 50MB를 허용하는가?
- [ ] **로그 로테이션**: 컨테이너 로그가 디스크를 가득 채울 수 있는가?
- [ ] **profiles: ["local"]**: docker-compose.yml에서 neo4j에 profiles: ["local"]이 있으면 기본 docker compose up에서 neo4j가 시작되지 않는가?

### 9. 코드 품질 / 유지보수
- [ ] **미사용 코드**: exceptions.py에 LLMEnrichmentError와 llm_enrichment_error_handler가 정의되어 있지만 main.py에 등록되어 있는가?
- [ ] **버전 불일치**: main.py의 version="0.8.0"이 실제 기능 수준과 맞는가? (MEMORY에는 v0.9.0으로 기록)
- [ ] **deprecated API**: on_event("startup")이 FastAPI 최신 버전에서 deprecated되었는가? lifespan으로 마이그레이션해야 하는가?
- [ ] **테스트 커버리지 빈틈**: 어떤 라우터/함수가 테스트에서 빠져 있는가?

---

## 출력 형식

각 발견 사항을 아래 형식으로 정리해줘:

### [심각도] 제목
- **파일**: `파일경로:줄번호`
- **문제**: 무엇이 잘못되었는지 1~2줄
- **영향**: 이 문제로 인해 실제로 어떤 일이 발생하는지
- **재현 방법**: 어떻게 하면 이 문제를 트리거할 수 있는지
- **수정 제안**: 코드 수준의 구체적인 수정 방법

심각도 기준:
- **[CRITICAL]**: 데이터 손실, 보안 침해, 서비스 다운 가능
- **[HIGH]**: 특정 조건에서 오류 발생, 데이터 정합성 문제
- **[MEDIUM]**: 엣지 케이스 미처리, 성능 저하 가능
- **[LOW]**: 코드 품질, 미사용 코드, 미래 유지보수 이슈

마지막에 심각도별 요약 표를 추가해줘.
```
