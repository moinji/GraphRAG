# Demo v0 개발 보고서
> 작성일: 2026-02-24 | 목적: 멘토 대상 "구현 가능성" 증명 Vertical Slice

---

## 1. 요약

`python demo.py` **한 줄로 DDL → KG → Q&A 전체 파이프라인이 동작**하는 데모를 완성했습니다.

| 지표 | 목표 | 실제 | 상태 |
|------|------|------|------|
| DDL 파싱 (테이블) | 12 | 12 | PASS |
| DDL 파싱 (FK) | 15 | 15 | PASS |
| KG 노드 타입 | 9 | 9 | PASS |
| KG 관계 타입 | 12 | 12 | PASS |
| FK 무결성 위반 | 0 | 0 | PASS |
| Neo4j 노드 적재 | - | 60 | PASS |
| Neo4j 관계 적재 | - | 97 | PASS |
| Q&A 정답률 | 3/3 | 3/3 | PASS |

---

## 2. 구현 범위 — WBS 대비 진행률

### Demo v0의 위치

> Demo v0는 **Week 1~5 범위의 핵심 로직을 수직 관통(Vertical Slice)** 한 것입니다.
> API 서버, UI, LLM 연동, 비동기 Job 등은 제외하고 **코어 파이프라인만** 구현했습니다.

| WBS 주차 | 핵심 작업 | Demo v0 반영 | 미반영 (정규 일정에서 구현) |
|----------|----------|-------------|--------------------------|
| **Week 1** | DDL 파서 + 인프라 | sqlglot 파서, Docker Compose(Neo4j), Pydantic 모델 | FastAPI 라우터, PostgreSQL, Redis, 파서 단위 테스트 10개 |
| **Week 2** | FK 규칙 온톨로지 | FK 규칙 엔진 (9노드/12관계), derivation 태그 | LLM 보강(Claude), 평가 리포트 자동화, PG 버전 저장 |
| **Week 3** | 온톨로지 리뷰 UI | - | React UI 전체 (Auto/Review 모드) |
| **Week 4** | KG Builder + 샘플 데이터 | Neo4j 벌크 로더, FK 무결 샘플 데이터, 제약조건 자동 생성 | 비동기 Job 모델, CSV 파일 생성, Faker 대량 데이터 |
| **Week 5** | 라우터 + Cypher 템플릿 | Cypher 템플릿 3개, 하드코딩 Q→템플릿 매핑, 근거 경로 출력 | 규칙+LLM 하이브리드 라우터, 템플릿 10~15개 |

### 코드 규모

| 파일 | 라인 수 | 역할 |
|------|---------|------|
| `app/ontology/fk_rule_engine.py` | 205 | FK 규칙 → 온톨로지 변환 |
| `app/data_generator/generator.py` | 184 | FK 무결 샘플 데이터 |
| `app/query/executor.py` | 146 | Q1~Q3 실행 + 경로 포맷팅 |
| `app/kg_builder/loader.py` | 130 | Neo4j MERGE 배치 적재 |
| `demo.py` | 113 | 파이프라인 오케스트레이터 |
| `app/ddl_parser/parser.py` | 108 | sqlglot + regex DDL 파싱 |
| `demo_ecommerce.sql` | 100 | 12테이블 DDL |
| `app/models/schemas.py` | 79 | Pydantic 공유 모델 |
| `app/query/templates.py` | 47 | Cypher 템플릿 3개 |
| **합계** | **1,132** | |

---

## 3. 실행 결과 상세

### Step 1: DDL 파싱

```
12 tables × 15 FK constraints 100% 추출
파서: sqlglot AST (테이블/컬럼) + regex (inline REFERENCES FK)
```

| 테이블 | 컬럼 수 | FK 수 |
|--------|---------|-------|
| addresses | 5 | 0 |
| categories | 3 | 1 (self-ref) |
| suppliers | 4 | 0 |
| coupons | 5 | 0 |
| customers | 5 | 1 |
| products | 6 | 2 |
| orders | 6 | 2 |
| order_items | 5 | 2 |
| payments | 6 | 1 |
| reviews | 6 | 2 |
| wishlists | 4 | 2 |
| shipping | 7 | 2 |
| **합계** | **67** | **15** |

### Step 2: 온톨로지 생성

**9 노드 타입** (3개 테이블은 관계로 매핑):

| 노드 | 원본 테이블 | 속성 수 |
|------|-----------|---------|
| Customer | customers | 4 |
| Address | addresses | 5 |
| Category | categories | 2 |
| Supplier | suppliers | 4 |
| Product | products | 4 |
| Order | orders | 4 |
| Payment | payments | 5 |
| Review | reviews | 4 |
| Coupon | coupons | 5 |

**12 관계 타입** (직접 FK 9개 + 조인테이블 3개):

| # | 관계 | 방향 | 유래 |
|---|------|------|------|
| 1 | PLACED | Customer → Order | fk_direct (flipped) |
| 2 | LIVES_AT | Customer → Address | fk_direct |
| 3 | WROTE | Customer → Review | fk_direct (flipped) |
| 4 | WISHLISTED | Customer → Product | fk_join_table (wishlists) |
| 5 | CONTAINS | Order → Product | fk_join_table (order_items) |
| 6 | PAID_BY | Order → Payment | fk_direct (flipped) |
| 7 | SHIPPED_TO | Order → Address | fk_join_table (shipping) |
| 8 | USED_COUPON | Order → Coupon | fk_direct |
| 9 | BELONGS_TO | Product → Category | fk_direct |
| 10 | SUPPLIED_BY | Product → Supplier | fk_direct |
| 11 | REVIEWS | Review → Product | fk_direct |
| 12 | PARENT_OF | Category → Category | fk_direct (self-ref) |

**고정 규칙 반영 확인** (PLAN.md 섹션 3.3):

| 테이블 | 매핑 전략 | 계획 | 실제 | 일치 |
|--------|----------|------|------|------|
| order_items | 관계 (CONTAINS) | O | O | YES |
| payments | 노드 (Payment) | O | O | YES |
| shipping | 관계 (SHIPPED_TO) | O | O | YES |
| wishlists | 관계 (WISHLISTED) | O | O | YES |

### Step 3: 샘플 데이터

| 테이블 | 행 수 | 비고 |
|--------|-------|------|
| addresses | 5 | |
| categories | 6 | 3 top-level + 3 sub (전자기기 하위) |
| suppliers | 3 | 애플코리아, 삼성전자, LG전자 |
| coupons | 2 | |
| customers | 5 | 김민수=id 1 (데모 주인공) |
| products | 8 | 맥북프로, 에어팟프로, 갤럭시탭 포함 |
| orders | 8 | 김민수 주문 3건 |
| order_items | 12 | |
| payments | 8 | |
| reviews | 15 | Q2 답변용 평점 설계 |
| wishlists | 4 | |
| shipping | 8 | |
| **합계** | **84** | FK 위반 0건 |

### Step 4: Neo4j 적재

```
Neo4j 노드:  60개 (9타입)
Neo4j 관계:  97개 (12타입)
```

- 매회 DB 초기화 (`MATCH (n) DETACH DELETE n`) → 재현성 보장
- `CREATE CONSTRAINT IF NOT EXISTS` → 노드별 UNIQUE(id)
- `UNWIND + MERGE` 배치 로딩

### Step 5: Q&A 결과

**Q1: "고객 김민수가 주문한 상품은?"** — 템플릿: `two_hop`

```
답변: 맥북프로, 에어팟프로, 갤럭시탭

근거 경로:
  Customer(김민수) → PLACED → Order → CONTAINS → Product(맥북프로)
  Customer(김민수) → PLACED → Order → CONTAINS → Product(에어팟프로)
  Customer(김민수) → PLACED → Order → CONTAINS → Product(갤럭시탭)
```

**Q2: "김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?"** — 템플릿: `custom_q2`

```
답변: 1위 맥북에어(노트북, 평점 5.0)
      2위 에어팟프로(오디오, 평점 4.67)
      3위 아이패드에어(태블릿, 평점 4.5)

근거 경로:
  Customer(김민수) → PLACED → Order → CONTAINS → Product(*)
    → BELONGS_TO → Category(노트북) ← BELONGS_TO ← Product(맥북에어)
    ← REVIEWS ← Review [avg=5.0]
```

**Q3: "가장 많이 팔린 카테고리 Top 3는?"** — 템플릿: `agg_with_rel`

```
답변: 1위 노트북(6건), 2위 오디오(4건), 3위 태블릿(2건)

근거 경로:
  Order(*) → CONTAINS → Product(*) → BELONGS_TO → Category(노트북) [count=6]
  Order(*) → CONTAINS → Product(*) → BELONGS_TO → Category(오디오) [count=4]
  Order(*) → CONTAINS → Product(*) → BELONGS_TO → Category(태블릿) [count=2]
```

---

## 4. 기술 스택 (Demo v0)

| 레이어 | 기술 | 용도 |
|--------|------|------|
| DDL 파싱 | sqlglot 29.x | PostgreSQL DDL AST 파싱 |
| 데이터 모델 | Pydantic 2.x | ERDSchema, OntologySpec, QueryResult |
| Graph DB | Neo4j 5 Community (Docker) | KG 저장/쿼리 |
| DB 드라이버 | neo4j-python 6.x | Bolt 프로토콜 연결 |
| 설정 | python-dotenv | .env 파일 로딩 |

---

## 5. 아키텍처 결정 기록

| # | 결정 | 근거 |
|---|------|------|
| 1 | **LLM 없음** (v0) | 구현 가능성 증명에 집중, Week 5에서 LLM 라우터 추가 |
| 2 | **인메모리 데이터 전달** | CSV 불필요, dict로 직접 전달하여 단순화 |
| 3 | **매회 DB 초기화** | 재현성 보장 (DETACH DELETE → 재적재) |
| 4 | **FK 방향 하드코딩** (DIRECTION_MAP) | v0에서는 12개 관계의 방향을 명시적으로 매핑 |
| 5 | **Q2는 커스텀 Cypher** | 3홉+집계+조인이 단순 템플릿으로 불가 |

---

## 6. 파일 구조

```
GraphRAG/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── models/
│   │   │   └── schemas.py           ← Pydantic 공유 모델
│   │   ├── ddl_parser/
│   │   │   └── parser.py            ← sqlglot DDL 파싱
│   │   ├── ontology/
│   │   │   └── fk_rule_engine.py    ← FK 규칙 → 온톨로지
│   │   ├── data_generator/
│   │   │   └── generator.py         ← FK 무결 샘플 데이터
│   │   ├── kg_builder/
│   │   │   └── loader.py            ← Neo4j MERGE 적재
│   │   └── query/
│   │       ├── templates.py          ← Cypher 템플릿 3개
│   │       └── executor.py           ← Q1~Q3 실행
│   ├── demo.py                       ← 파이프라인 오케스트레이터
│   └── demo_ecommerce.sql            ← 12테이블 DDL
├── docker-compose.yml                ← Neo4j 컨테이너
├── requirements.txt
└── .env.example
```

---

## 7. 다음 단계 (정규 Week 1부터)

Demo v0에서 **검증된 것**과 **정규 일정에서 추가할 것**:

| 검증 완료 (Demo v0) | 정규 일정 추가 필요 |
|---------------------|-------------------|
| DDL 파싱 로직 | FastAPI REST API (`POST /api/v1/ddl/upload`) |
| FK 규칙 온톨로지 엔진 | LLM 보강 (Claude, derivation 태그 분리) |
| Neo4j 벌크 로더 | 비동기 Job 모델 (`BackgroundTasks`) |
| Cypher 템플릿 3개 | 템플릿 10~15개 + 규칙+LLM 하이브리드 라우터 |
| 샘플 데이터 84행 | Faker 기반 대량 데이터 (12테이블 × 200~500행) |
| 콘솔 데모 | React UI (DDL 업로드 → 온톨로지 리뷰 → Q&A 채팅) |
| - | PostgreSQL 메타데이터 (온톨로지 버전, 빌드 이력) |
| - | 평가 자동화 리포트 |

---

## 8. 실행 방법

```bash
# 1. Docker Desktop 실행 후
docker compose up -d

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 데모 실행
cd backend && python demo.py
```

소요 시간: Neo4j 최초 기동 ~15초, 파이프라인 실행 ~3초

---

*Demo v0 — DDL→KG→Q&A Vertical Slice 완성*
