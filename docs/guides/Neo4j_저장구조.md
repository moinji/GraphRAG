# Neo4j 데이터 저장 구조

> `MATCH (n) RETURN n LIMIT 50` 쿼리로 보이는 데이터가 어디에 저장되고, 어떻게 들어가는지 설명한다.

---

## 1. 물리적 저장 위치

### Docker Named Volume

```yaml
# docker-compose.yml
neo4j:
  image: neo4j:5-community
  volumes:
    - neo4j_data:/data    # ← 모든 그래프 데이터가 여기에 저장

volumes:
  neo4j_data:             # Docker managed volume
```

| 항목 | 값 |
|------|-----|
| 볼륨 이름 | `neo4j_data` |
| 컨테이너 내부 경로 | `/data` |
| 호스트 물리 경로 (Windows Docker Desktop) | `\\wsl$\docker-desktop-data\data\docker\volumes\neo4j_data\_data\` |
| 접속 포트 (Browser UI) | `http://localhost:7474` |
| 접속 포트 (Bolt Driver) | `bolt://localhost:7687` |
| 인증 | `neo4j` / `password123` |

### 데이터 영속성

- `docker compose down` → 컨테이너 삭제, **볼륨 유지** (데이터 보존)
- `docker compose down -v` → 컨테이너 + **볼륨 삭제** (데이터 삭제)
- `docker compose up` → 기존 볼륨이 있으면 이전 데이터 그대로 복원

---

## 2. 데이터가 들어가는 과정

### 전체 흐름

```
[1] DDL 업로드 (.sql)
     │  POST /api/v1/ontology/generate
     ▼
[2] 온톨로지 생성
     │  ERD → FK Rule Engine → OntologySpec (노드/관계 정의)
     │  (선택) LLM 보강 → 방향성/이름 개선
     ▼
[3] 온톨로지 승인
     │  POST /api/v1/ontology/versions/{id}/approve
     ▼
[4] KG 빌드 (비동기 Job)
     │  POST /api/v1/kg/build
     ▼
[5] Neo4j 로딩
     │  backend/app/kg_builder/loader.py
     │  MERGE 쿼리로 노드/관계 일괄 삽입
     ▼
[6] 완료 → Explore 페이지에서 그래프 조회
```

### 핵심 파일: `backend/app/kg_builder/loader.py`

`load_to_neo4j()` 함수가 실행하는 순서:

```cypher
-- Step 1: 기존 데이터 전부 삭제
MATCH (n) DETACH DELETE n

-- Step 2: 유니크 제약 생성 (노드 타입별)
CREATE CONSTRAINT FOR (n:Customer) REQUIRE n.id IS UNIQUE
CREATE CONSTRAINT FOR (n:Product) REQUIRE n.id IS UNIQUE
...

-- Step 3: 노드 일괄 삽입 (노드 타입별 배치)
UNWIND $rows AS row
MERGE (n:Customer {id: row.id})
SET n.name = row.name, n.email = row.email, n.phone = row.phone

UNWIND $rows AS row
MERGE (n:Product {id: row.id})
SET n.name = row.name, n.price = row.price, n.description = row.description
...

-- Step 4: 관계 일괄 삽입 (관계 타입별 배치)
UNWIND $rows AS row
MATCH (src:Customer {id: row.__src})
MATCH (tgt:Order {id: row.__tgt})
MERGE (src)-[r:PLACED]->(tgt)

UNWIND $rows AS row
MATCH (src:Order {id: row.__src})
MATCH (tgt:Product {id: row.__tgt})
MERGE (src)-[r:CONTAINS]->(tgt)
SET r.quantity = row.quantity, r.unit_price = row.unit_price
...

-- Step 5: 검증
MATCH (n) RETURN count(n) AS node_count
MATCH ()-[r]->() RETURN count(r) AS rel_count
```

---

## 3. 데이터 소스 (2가지 경로)

### 경로 A: 샘플 데이터 자동 생성 (CSV 없이 빌드)

CSV를 업로드하지 않고 KG 빌드를 실행하면, `data_generator.py`가 E-Commerce 시드 데이터를 코드로 자동 생성한다.

데모에서 보이는 김민수, 맥북프로, 에어팟프로 등이 이 경로로 생성된 데이터.

```
KG Build (csv_session_id=None)
  → data_generator.py가 Python dict로 샘플 행 생성
  → loader.py가 Neo4j에 MERGE
```

### 경로 B: CSV 업로드

사용자가 직접 CSV 파일을 업로드하면 해당 데이터를 사용한다.

```
CSV 업로드 → parser.py가 파싱/검증 → session_id 발급
  → KG Build (csv_session_id=xxx)
  → loader.py가 파싱된 CSV 데이터를 Neo4j에 MERGE
```

CSV 예시 파일: `examples/data/accounting/*.csv` (10개 파일)

---

## 4. 온톨로지 → Neo4j 매핑 규칙

`backend/app/ontology/fk_rule_engine.py`가 ERD를 분석하여 매핑 결정:

### 노드 매핑

| SQL 테이블 | Neo4j 노드 라벨 | 규칙 |
|-----------|----------------|------|
| `customers` | `Customer` | PascalCase 변환 |
| `products` | `Product` | PascalCase 변환 |
| `categories` | `Category` | PascalCase 변환 |
| `orders` | `Order` | PascalCase 변환 |
| `order_items` | (관계로 변환) | Join 테이블 → 노드가 아닌 관계 |

- 모든 컬럼(FK 제외)이 노드 property가 됨
- `id` 컬럼이 유니크 키로 사용됨

### 관계 매핑

| FK 관계 | Neo4j 관계 | 방향 |
|---------|-----------|------|
| `orders.customer_id → customers.id` | `(Customer)-[:PLACED]->(Order)` | FK 역방향 |
| `products.category_id → categories.id` | `(Product)-[:BELONGS_TO]->(Category)` | FK 정방향 |
| `order_items (join table)` | `(Order)-[:CONTAINS]->(Product)` | Join 테이블 해소 |
| `reviews.product_id` | `(Review)-[:REVIEWS]->(Product)` | FK 정방향 |

---

## 5. 데이터 저장 계층 요약

| 계층 | 기술 | 볼륨 | 저장 내용 |
|------|------|------|-----------|
| **Neo4j** | Graph DB (neo4j:5-community) | `neo4j_data:/data` | 노드, 관계, 속성 (그래프 데이터) |
| **PostgreSQL** | Metadata DB | `postgres_data:/var/lib/postgresql/data` | 온톨로지 버전, KG 빌드 이력 |
| **Redis** | Cache | In-memory | 쿼리 결과 캐시 |

---

## 6. 자주 쓰는 Neo4j 쿼리

```cypher
-- 전체 노드 조회 (50개 제한)
MATCH (n) RETURN n LIMIT 50

-- 노드 + 관계 함께 조회
MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50

-- 라벨별 노드 수 확인
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC

-- 관계 타입별 수 확인
MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS cnt ORDER BY cnt DESC

-- 특정 고객의 주문 경로 탐색
MATCH path = (c:Customer {name: "김민수"})-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN path

-- 전체 삭제 (주의!)
MATCH (n) DETACH DELETE n
```
