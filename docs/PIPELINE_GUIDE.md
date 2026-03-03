# GraphRAG 파이프라인 완벽 가이드

> SQL 테이블 설계서 한 장으로 Knowledge Graph를 만들고, 자연어로 데이터를 탐색하는 시스템

---

## 0. 한눈에 보기

```
.sql 파일 → [파싱] → ERDSchema → [규칙+AI] → OntologySpec → [검토] → [빌드] → Neo4j KG
                                                                          ↑
                                                                   .csv 데이터(선택)

Neo4j KG → [Cypher 질의]       → 정형 답변  (Mode A)
Neo4j KG → [서브그래프 + Claude] → 자연어 답변 (Mode B)
Neo4j KG → [Graph API]         → 인터랙티브 시각화
```

**비유로 이해하기:** 이 시스템은 "자동 도서관 건설기"와 같습니다.

| 도서관 비유 | GraphRAG |
|-----------|----------|
| 건축 도면 | SQL DDL 파일 |
| 도면 분석 | DDL Parser |
| 서가 배치 설계 | 온톨로지 생성 |
| 사서의 검토·승인 | 사용자 검토 |
| 책 입고·분류 | KG 빌드 |
| "이런 책 있나요?" | 자연어 질의 |
| 서가 지도 | 그래프 시각화 |

---

## 1. STAGE 1 — 스키마 입력 및 파싱

### 이 단계가 하는 일
사용자가 업로드한 `.sql` DDL 파일을 분석해서, 시스템이 이해할 수 있는 구조화된 JSON(ERDSchema)으로 변환합니다.

### 왜 필요한가?
SQL 파일은 사람이 읽을 수 있는 텍스트일 뿐입니다. 시스템이 "고객 테이블은 주문 테이블과 연결되어 있다"는 것을 알려면, 먼저 이 텍스트를 기계가 이해하는 구조로 바꿔야 합니다.

### Before → After

**Before (사용자가 올린 SQL):**
```sql
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(200),
    address_id INTEGER REFERENCES addresses(id)
);
```

**After (시스템이 만든 ERDSchema JSON):**
```json
{
  "tables": [
    {
      "name": "customers",
      "columns": [
        {"name": "id", "data_type": "SERIAL", "is_primary_key": true},
        {"name": "name", "data_type": "VARCHAR(100)", "nullable": false},
        {"name": "email", "data_type": "VARCHAR(200)", "nullable": true},
        {"name": "address_id", "data_type": "INTEGER", "nullable": true}
      ]
    }
  ],
  "foreign_keys": [
    {
      "source_table": "customers",
      "source_column": "address_id",
      "target_table": "addresses",
      "target_column": "id"
    }
  ]
}
```

### 핵심 기술
- **sqlglot**: SQL 구문을 파싱하는 라이브러리. `CREATE TABLE` 문에서 테이블명, 컬럼명, 데이터 타입을 추출합니다.
- **regex 보완**: `sqlglot`이 놓칠 수 있는 `REFERENCES`, `CONSTRAINT` 등의 FK 정의를 정규표현식으로 추가 파싱합니다.

### 선택 기능: CSV 데이터 업로드
DDL은 구조(틀)만 정의합니다. 실제 데이터가 필요하면 CSV 파일을 테이블별로 업로드할 수 있습니다.
- CSV가 있으면 → 실제 데이터로 그래프 구축
- CSV가 없으면 → 시스템이 샘플 데이터를 자동 생성

> **한 줄로 정리하면:** SQL 설계도를 읽어서 "어떤 테이블이 있고, 서로 어떻게 연결되어 있는지"를 JSON으로 정리하는 단계.

---

## 2. STAGE 2 — 온톨로지 자동 생성

### 이 단계가 하는 일
ERDSchema(테이블 구조)를 Knowledge Graph의 설계도인 OntologySpec(노드 타입 + 관계 타입)으로 변환합니다.

### 왜 필요한가?
관계형 데이터베이스(테이블)와 그래프 데이터베이스(노드-관계)는 데이터를 표현하는 방식이 다릅니다. 테이블의 외래키(FK)를 그래프의 관계로 바꾸는 "번역 규칙"이 필요합니다.

### 비유
테이블 구조는 "엑셀 스프레드시트"이고, 온톨로지는 "마인드맵 설계도"입니다. 이 단계는 스프레드시트를 보고 마인드맵을 어떻게 그릴지 설계하는 과정입니다.

### 2단계 파이프라인

#### Stage 2-1: FK Rule Engine (결정론적 규칙)
사람의 판단 없이, 정해진 규칙으로 자동 변환합니다.

| 규칙 | 테이블 구조 | 그래프 결과 |
|------|------------|------------|
| 테이블 → 노드 | `customers` 테이블 | `Customer` 노드 라벨 |
| FK → 관계 | `orders.customer_id → customers.id` | `(Order)-[BELONGS_TO_CUSTOMER]->(Customer)` |
| 조인 테이블 → 관계 | `order_items` (FK 2개, 고유 컬럼 적음) | `(Order)-[HAS_ITEM]->(Product)` |
| 자기참조 FK | `categories.parent_id → categories.id` | `(Category)-[HAS_PARENT]->(Category)` |

**변환 예시:**
```
[customers 테이블]          →  (Customer) 노드
[orders 테이블]             →  (Order) 노드
[orders.customer_id FK]     →  (Order)-[BELONGS_TO_CUSTOMER]->(Customer) 관계
```

#### Stage 2-2: LLM 보강 (선택적)
Claude API를 사용해 규칙 기반 결과를 개선합니다.
- 관계 이름을 더 자연스럽게 (`BELONGS_TO_CUSTOMER` → `ORDERED_BY`)
- 누락된 의미적 관계 추가
- 모든 LLM 제안에는 `derivation="llm_suggested"` 태그 부착

#### 품질 평가
Golden Data(정답 데이터)와 비교해서 정확도·커버리지 메트릭을 계산합니다.

### Before → After

**Before (ERDSchema 일부):**
```
테이블: customers, orders, order_items, products
FK: orders.customer_id → customers.id
FK: order_items.order_id → orders.id
FK: order_items.product_id → products.id
```

**After (OntologySpec):**
```json
{
  "node_types": [
    {"name": "Customer", "source_table": "customers", "properties": ["name", "email"]},
    {"name": "Order", "source_table": "orders", "properties": ["status", "total_amount"]},
    {"name": "Product", "source_table": "products", "properties": ["name", "price"]}
  ],
  "relationship_types": [
    {"name": "PLACED", "source_node": "Customer", "target_node": "Order"},
    {"name": "CONTAINS", "source_node": "Order", "target_node": "Product"}
  ]
}
```

> **한 줄로 정리하면:** 테이블 간 FK 관계를 분석해서 "무엇이 노드이고, 무엇이 관계인지" 자동으로 설계하는 단계.

---

## 3. STAGE 3 — 사용자 검토 및 KG 빌드

### 이 단계가 하는 일
자동 생성된 온톨로지를 사용자가 검토·수정한 뒤, 승인하면 실제 Knowledge Graph를 Neo4j에 구축합니다.

### 왜 필요한가?
자동 생성이 아무리 정확해도, 도메인 전문가의 검토가 필요합니다. "이 관계 이름이 맞나?", "이 테이블은 노드가 아니라 관계로 표현하는 게 나을까?" 같은 판단은 사람이 해야 합니다.

### 검토 화면 (ReviewPage)
```
┌─────────────────────────────────────────────┐
│  노드 타입 목록          │  관계 타입 목록   │
│  ☑ Customer (customers)  │  PLACED           │
│  ☑ Order (orders)        │  Customer → Order  │
│  ☑ Product (products)    │  CONTAINS          │
│  ☐ OrderItem (삭제 가능) │  Order → Product   │
│                          │                    │
│  [+ 노드 추가]           │  [+ 관계 추가]    │
│                          │                    │
│  ── LLM 변경사항 ──      │                   │
│  ✨ "PLACED" (was: BELONGS_TO_CUSTOMER)      │
│                          │                    │
│  [Approve] [Build KG]    │                    │
└─────────────────────────────────────────────┘
```

### KG 빌드 과정

**[Build KG] 클릭 시 진행되는 과정:**

```
1. 데이터 소스 결정
   ├── CSV 세션이 있으면 → 실제 업로드 데이터 사용
   └── 없으면 → 샘플 데이터 자동 생성

2. FK 무결성 검증
   └── 모든 FK 참조가 유효한지 확인

3. Neo4j 로드 (핵심)
   ├── 기존 그래프 전체 삭제 (MATCH (n) DETACH DELETE n)
   ├── 유니크 제약조건 생성 (CREATE CONSTRAINT ...)
   ├── 노드 배치 삽입 (UNWIND + MERGE)
   └── 관계 배치 삽입 (UNWIND + MERGE)

4. 카운트 검증
   └── 생성된 노드/관계 수 확인
```

### Cypher 쿼리 예시 (실제 실행되는 코드)

**노드 생성:**
```cypher
UNWIND $rows AS row
MERGE (n:Customer {id: row.id})
SET n.name = row.name, n.email = row.email, n.phone = row.phone
```

**관계 생성:**
```cypher
UNWIND $rows AS row
MATCH (a:Order {id: row.source_id})
MATCH (b:Customer {id: row.target_id})
MERGE (a)-[r:PLACED]->(b)
```

### 비동기 처리
빌드는 백그라운드 태스크로 실행됩니다 (HTTP 202 응답). 프론트엔드가 주기적으로 진행 상태를 폴링합니다.

```
Poll 1: running - nodes=15, rels=0
Poll 2: running - nodes=50, rels=30
Poll 3: succeeded - nodes=50, rels=82
```

> **한 줄로 정리하면:** 자동 설계를 사람이 확인·수정한 뒤, 버튼 하나로 Neo4j에 실제 그래프를 구축하는 단계.

---

## 4. STAGE 4 — 활용: 자연어 질의 + 시각화

Knowledge Graph가 완성되면 두 가지 방법으로 활용합니다.

### 4-A. 자연어 질의 (QueryPage)

사용자가 한국어로 질문하면, 시스템이 그래프를 탐색해서 답변합니다.

#### Mode A: 템플릿 기반 (정확한 정형 답변)

```
사용자: "김민수가 주문한 상품은?"
    ↓
1. 규칙 매칭 (regex 패턴)
   "~가 주문한 상품" → customer_orders 템플릿 매칭
    ↓
2. (매칭 실패 시) LLM 라우터 (Claude Haiku)
   질문 → 가장 적합한 템플릿 선택
    ↓
3. Cypher 템플릿 슬롯 채우기
   MATCH (c:Customer {name: "김민수"})-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
   RETURN p.name, o.total_amount
    ↓
4. Neo4j 실행 → 결과 포맷팅
    ↓
답변: "김민수 고객이 주문한 상품: 맥북프로(₩3,500,000), 에어팟프로(₩359,000), 갤럭시탭(₩699,000)"
```

**장점:** 빠르고 정확. Cypher 쿼리를 직접 보여줘서 투명.
**한계:** 미리 정의된 질문 패턴에만 대응 가능.

#### Mode B: 로컬 서치 (유연한 자연어 답변)

```
사용자: "김민수가 산 것들 중에서 평점 높은 비슷한 상품 추천해줘"
    ↓
1. 엔티티 추출 (규칙 기반)
   "김민수" → Customer 엔티티
    ↓
2. Neo4j 서브그래프 탐색 (1~3홉)
   김민수 → 주문 → 상품 → 카테고리 → 같은 카테고리 상품 → 리뷰
    ↓
3. Claude Sonnet에 컨텍스트 주입
   "다음 그래프 데이터를 바탕으로 질문에 답해주세요: [서브그래프 JSON]"
    ↓
4. 자연어 답변 생성
    ↓
답변: "김민수 고객이 구매한 맥북프로와 같은 노트북 카테고리에서 맥북에어가
      평균 평점 5.0으로 가장 높은 평가를 받고 있습니다. 가격도 ₩1,690,000으로
      맥북프로(₩3,500,000)보다 합리적입니다."
```

**장점:** 미리 정의되지 않은 복잡한 질문에도 대응. 자연스러운 한국어 답변.
**한계:** LLM 호출 비용, Mode A보다 느림.

### 4-B. 인터랙티브 그래프 탐색 (ExplorePage)

Knowledge Graph를 시각적으로 탐색할 수 있는 인터페이스입니다.

```
┌─ 검색바 | 레이아웃 선택 | 줌 버튼 ──────────────────────┐
│                                                          │
│  ┌── 필터 ──┐  ┌── 그래프 캔버스 ──────┐  ┌── 상세 ──┐  │
│  │ ☑ Customer│  │                       │  │ 김민수    │  │
│  │ ☑ Order   │  │   (김민수)            │  │          │  │
│  │ ☑ Product │  │    ↓  ↓  ↓            │  │ email:   │  │
│  │ ☐ Address │  │  (주문1)(주문2)(주문3) │  │ minsu@.. │  │
│  │           │  │    ↓     ↓     ↓      │  │          │  │
│  │ ☑ PLACED  │  │  (맥북) (에어팟)(탭)  │  │ 연결: 3  │  │
│  │ ☑ CONTAINS│  │                       │  │ [Expand] │  │
│  └──────────┘  └───────────────────────┘  └─────────┘  │
└──────────────────────────────────────────────────────────┘
```

**3개 API 엔드포인트:**
| 엔드포인트 | 역할 |
|-----------|------|
| `GET /graph/stats` | 노드/엣지 타입별 카운트 |
| `GET /graph/full?limit=500` | 전체 그래프 데이터 (제한) |
| `GET /graph/neighbors/{id}` | 특정 노드 주변 확장 |

**인터랙션:**
- **노드 클릭** → 우측 상세 패널 (속성, 연결 노드)
- **Expand 버튼** → 주변 노드 동적 로드
- **검색** → 매칭 노드로 줌·센터링
- **필터** → 타입별 표시/숨김
- **레이아웃 전환** → COSE(기본), Concentric, Grid

**렌더링 엔진:** Cytoscape.js (Canvas 기반)
- DOM이 아닌 Canvas에 그려서 1000+ 노드도 부드럽게 처리
- 노드 타입별 색상 구분 (Customer=인디고, Product=에메랄드 등)

> **한 줄로 정리하면:** 완성된 그래프에 한국어로 질문하거나, 마인드맵처럼 시각적으로 탐색하는 단계.

---

## 5. 인프라 구성 (Docker Compose)

전체 시스템은 5개의 Docker 컨테이너로 구성됩니다.

```
┌─────────────────────────────────────────────────────┐
│                   Docker Compose                     │
│                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐   │
│  │ Frontend │    │ Backend  │    │   Neo4j      │   │
│  │ React 19 │───▶│ FastAPI  │───▶│ 그래프 DB    │   │
│  │ :80      │    │ :8000    │    │ Bolt :7687   │   │
│  └──────────┘    └────┬─────┘    └──────────────┘   │
│                       │                              │
│                  ┌────┴─────┐                       │
│            ┌─────┴──┐  ┌───┴────┐                   │
│            │ Postgres│  │ Redis  │                   │
│            │ 메타DB  │  │ 캐시   │                   │
│            │ :5432   │  │ :6379  │                   │
│            └────────┘  └────────┘                   │
└─────────────────────────────────────────────────────┘
```

| 컨테이너 | 역할 | 저장하는 것 |
|----------|------|------------|
| **Frontend** | React 19 + Tailwind → Nginx 서빙 | UI 화면 |
| **Backend** | FastAPI (Python) + Uvicorn | 비즈니스 로직, API |
| **Neo4j** | 그래프 데이터베이스 | 노드, 관계 (Knowledge Graph) |
| **PostgreSQL** | 관계형 데이터베이스 | 온톨로지 버전, 빌드 이력 |
| **Redis** | 인메모리 캐시 | CSV 세션, 임시 데이터 |

### 왜 DB가 3개인가?
각 DB가 잘하는 일이 다릅니다:
- **Neo4j**: "김민수와 연결된 모든 것을 3단계까지 탐색" → 그래프 순회에 최적
- **PostgreSQL**: "온톨로지 버전 5의 상세 정보" → 구조화된 메타데이터 저장에 최적
- **Redis**: "방금 업로드한 CSV 임시 보관" → 빠른 읽기/쓰기, 세션 관리에 최적

---

## 6. 핵심 가치 — 왜 이 시스템이 필요한가?

### 기존 방식의 문제
```
개발자가 SQL 작성 → DBA가 쿼리 최적화 → 결과를 보고서로 정리 → 비개발자에게 전달
```
- 비개발자는 SQL을 모름
- 데이터 간 관계를 파악하기 어려움
- 새로운 질문마다 개발자에게 요청해야 함

### GraphRAG의 해결
```
누구나 SQL DDL 업로드 → 자동으로 KG 구축 → 한국어로 질문 → 시각적으로 탐색
```
- **자동화**: DDL만 있으면 그래프가 만들어짐
- **접근성**: SQL 몰라도 한국어로 데이터 탐색
- **투명성**: Cypher 쿼리와 증거 경로를 함께 보여줌
- **범용성**: 이커머스, 회계, HR 등 어떤 도메인이든 작동

### 데이터 변환 여정 (전체 흐름)

```
SQL DDL 텍스트
    ↓ [파싱]
ERDSchema JSON (테이블 + FK)
    ↓ [규칙 엔진]
OntologySpec JSON (노드 + 관계 설계)
    ↓ [검토·승인]
OntologySpec JSON (확정)
    ↓ [빌드]
Neo4j Graph (Cypher로 질의 가능한 실제 그래프)
    ↓ [활용]
├── 자연어 답변 (Mode A/B)
└── 인터랙티브 시각화 (Cytoscape.js)
```

> **최종 한 줄 요약:** GraphRAG는 "SQL 설계서를 넣으면 Knowledge Graph가 나오고, 한국어로 질문하면 답이 나오는" 엔드투엔드 자동화 시스템입니다.
