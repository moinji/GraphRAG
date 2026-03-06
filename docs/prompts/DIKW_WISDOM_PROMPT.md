# DIKW Wisdom Layer 강화 프롬프트

> 이 문서는 GraphRAG 프로젝트의 Wisdom 계층 구현을 위한 종합 설계 프롬프트입니다.
> Claude/GPT에게 이 프롬프트를 전달하면 구현 코드를 생성할 수 있습니다.

---

## 배경: 현재 DIKW 파이프라인 상태

```
[Data]        DDL/CSV 업로드 → 원시 스키마, 행 데이터           ✅ 완료
[Information] ERD 파싱 → FK 관계 추출 → 온톨로지 생성           ✅ 완료
[Knowledge]   Neo4j KG → Cypher 질의 → 서브그래프 탐색          ✅ 완료
[Wisdom]      패턴 발견 → 인사이트 → 추천 → 의사결정 지원        ⚠️ 미구현
```

현재 Q&A는 "김민수가 주문한 상품은?" 같은 **조회(lookup)** 수준에 머물러 있다.
Wisdom 계층은 "왜?", "그래서?", "다음에 뭘 해야 하지?"에 답하는 것이다.

---

## 프롬프트 본문

아래는 이 프로젝트에 Wisdom 계층을 추가하기 위한 구현 지시서입니다.

### 1. 아키텍처 개요

```
사용자 질문
    │
    ▼
┌─────────────────────────────────────────────┐
│              Wisdom Router                   │
│  질문 의도 분류:                              │
│    lookup → 기존 A안/B안 파이프라인            │
│    insight → Insight Engine (새로 추가)       │
│    recommendation → Recommendation Engine     │
│    what_if → What-If Simulator               │
│    dikw_trace → DIKW Trace Visualizer        │
└─────────────────────────────────────────────┘
         │           │            │          │
         ▼           ▼            ▼          ▼
    [기존 Q&A]  [Insight]  [Recommend]  [What-If]
                     │           │          │
                     └─────┬─────┘──────────┘
                           ▼
                  ┌─────────────────┐
                  │  DIKW Dashboard  │
                  │  계층별 시각화    │
                  └─────────────────┘
```

### 2. Wisdom 질문 유형 5가지

#### Type W1: 패턴 발견 (Pattern Discovery)
```
질문 예시:
  "우리 고객들의 구매 패턴에서 어떤 트렌드가 보이나요?"
  "어떤 상품 조합이 자주 같이 구매되나요?"
  "고객 세그먼트별 특징은?"

처리 방식:
  1. Neo4j에서 다중 집계 Cypher 실행 (주문빈도, 카테고리분포, 시간대별 등)
  2. 결과를 LLM에게 전달하며 "패턴을 발견하고 비즈니스 의미를 해석하라" 지시
  3. 응답에 [DATA → INFORMATION → KNOWLEDGE → WISDOM] 태그 포함

Cypher 예시 (함께 실행):
  # 고객별 카테고리 선호도
  MATCH (c:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product)-[:BELONGS_TO]->(cat:Category)
  RETURN c.name AS customer, cat.name AS category, count(*) AS purchase_count
  ORDER BY customer, purchase_count DESC

  # 상품 동시구매 패턴 (Co-purchase)
  MATCH (o:Order)-[:CONTAINS]->(p1:Product), (o)-[:CONTAINS]->(p2:Product)
  WHERE id(p1) < id(p2)
  RETURN p1.name AS product_1, p2.name AS product_2, count(o) AS co_purchase_count
  ORDER BY co_purchase_count DESC

  # 고객 세그먼트 (주문금액 기준)
  MATCH (c:Customer)-[:PLACED]->(o:Order)
  WITH c.name AS customer, count(o) AS orders, sum(toFloat(o.total_amount)) AS total_spent
  RETURN customer, orders, total_spent,
    CASE
      WHEN total_spent > 5000000 THEN 'VIP'
      WHEN total_spent > 2000000 THEN 'Regular'
      ELSE 'Light'
    END AS segment
  ORDER BY total_spent DESC
```

#### Type W2: 인과 분석 (Causal Analysis)
```
질문 예시:
  "왜 전자기기 카테고리의 주문이 가장 많은가요?"
  "리뷰 평점이 높은 상품이 실제로 더 많이 팔리나요?"
  "쿠폰 사용이 주문 금액에 어떤 영향을 미치나요?"

처리 방식:
  1. 질문에서 "원인 변수"와 "결과 변수" 추출
  2. KG에서 두 변수 사이의 경로 탐색 + 관련 데이터 수집
  3. LLM에게 "상관관계와 가능한 인과관계를 분석하라" 지시
  4. 반드시 "이것은 상관관계이며, 인과관계를 확정하려면 추가 데이터가 필요합니다" 면책 포함

Cypher 예시:
  # 리뷰 평점 vs 판매량 상관관계
  MATCH (r:Review)-[:REVIEWS]->(p:Product)<-[:CONTAINS]-(o:Order)
  WITH p.name AS product, avg(toFloat(r.rating)) AS avg_rating, count(DISTINCT o) AS order_count
  RETURN product, avg_rating, order_count
  ORDER BY avg_rating DESC

  # 쿠폰 사용 vs 주문금액 비교
  MATCH (o:Order)
  OPTIONAL MATCH (o)-[:APPLIED]->(coup:Coupon)
  WITH CASE WHEN coup IS NOT NULL THEN 'used' ELSE 'unused' END AS coupon_status,
       toFloat(o.total_amount) AS amt
  RETURN coupon_status, count(*) AS orders, avg(amt) AS avg_amount, sum(amt) AS total_revenue
```

#### Type W3: 추천 (Recommendation)
```
질문 예시:
  "김민수에게 어떤 상품을 추천하면 좋을까요?"
  "재고 관리에서 우선적으로 주의해야 할 상품은?"
  "어떤 공급사와의 관계를 강화해야 할까요?"

처리 방식:
  1. 대상 엔티티의 서브그래프 탐색 (2-3홉)
  2. 유사 고객/상품 패턴 분석 (Collaborative Filtering via Graph)
  3. LLM에게 "그래프 데이터 기반으로 구체적 추천과 근거를 제시하라" 지시

Cypher 예시:
  # 협업 필터링: 김민수와 비슷한 고객이 구매했지만 김민수는 안 산 상품
  MATCH (target:Customer {name: $name})-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product)
  WITH target, collect(p) AS bought
  MATCH (other:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(common:Product)
  WHERE common IN bought AND other <> target
  MATCH (other)-[:PLACED]->(:Order)-[:CONTAINS]->(rec:Product)
  WHERE NOT rec IN bought
  RETURN rec.name AS recommended_product, count(DISTINCT other) AS recommender_count,
         collect(DISTINCT other.name) AS similar_customers
  ORDER BY recommender_count DESC
  LIMIT 5

  # 공급사 의존도 분석
  MATCH (s:Supplier)<-[:SUPPLIED_BY]-(p:Product)<-[:CONTAINS]-(o:Order)
  WITH s.name AS supplier, count(DISTINCT p) AS product_count,
       count(DISTINCT o) AS order_count, sum(toFloat(o.total_amount)) AS revenue
  RETURN supplier, product_count, order_count, revenue,
         round(revenue * 100.0 / sum(revenue) OVER ()) / 100 AS revenue_share_pct
  ORDER BY revenue DESC
```

#### Type W4: What-If 시뮬레이션
```
질문 예시:
  "애플코리아 공급이 중단되면 어떤 상품과 고객이 영향받나요?"
  "노트북 카테고리를 제거하면 매출에 얼마나 영향이 있나요?"
  "김민수가 이탈하면 어떤 영향이 있나요?"

처리 방식:
  1. 제거 대상 엔티티 식별
  2. 해당 엔티티에 연결된 모든 경로 탐색 (Impact Graph)
  3. 영향받는 엔티티 수, 매출 영향, 대체 경로 존재 여부 계산
  4. LLM에게 "영향 범위를 정량화하고 리스크 완화 방안을 제시하라" 지시

Cypher 예시:
  # 공급사 제거 영향 분석
  MATCH (s:Supplier {name: $supplier_name})<-[:SUPPLIED_BY]-(p:Product)
  OPTIONAL MATCH (p)<-[:CONTAINS]-(o:Order)<-[:PLACED]-(c:Customer)
  WITH s, collect(DISTINCT p.name) AS affected_products,
       collect(DISTINCT c.name) AS affected_customers,
       count(DISTINCT o) AS affected_orders,
       sum(toFloat(o.total_amount)) AS at_risk_revenue
  // 대체 공급사 확인
  OPTIONAL MATCH (p2:Product)-[:BELONGS_TO]->(cat:Category)<-[:BELONGS_TO]-(alt:Product)-[:SUPPLIED_BY]->(alt_s:Supplier)
  WHERE alt_s <> s AND p2.name IN affected_products
  RETURN s.name AS removed_supplier,
         affected_products, affected_customers,
         affected_orders, at_risk_revenue,
         collect(DISTINCT alt_s.name) AS alternative_suppliers
```

#### Type W5: DIKW Trace (전 계층 추적 시각화)
```
질문 예시:
  "김민수에 대해 DIKW 전체 분석을 보여줘"
  "노트북 카테고리의 DIKW 보고서를 만들어줘"

처리 방식:
  모든 질문에 대해 4계층을 명시적으로 보여주는 종합 보고서 생성

  [D] Data    — 원시 데이터: customers 테이블의 row, orders 테이블의 rows...
  [I] Info    — 구조화: Customer(김민수) → ERD에서 5개 FK 관계 식별
  [K] Knowledge — 그래프: 2홉 서브그래프에서 3개 주문, 5개 상품, 3개 카테고리 연결 발견
  [W] Wisdom  — 인사이트:
    - 김민수는 VIP 세그먼트 (총 주문 700만원)
    - 노트북+오디오 카테고리 선호 → 다음 추천: 태블릿 악세서리
    - 애플코리아 의존도 67% → 공급 다변화 필요
    - 리뷰 평점 4.5 이상 상품만 구매 → 품질 민감 고객

  프론트엔드에서는 4단계를 시각적 타임라인/파이프라인으로 보여준다.
```

### 3. Wisdom Engine 시스템 프롬프트

아래는 Wisdom Engine이 LLM을 호출할 때 사용할 시스템 프롬프트입니다.

```python
WISDOM_SYSTEM_PROMPT = """\
당신은 Knowledge Graph 기반 비즈니스 인텔리전스 어드바이저입니다.
고객의 데이터에서 추출한 그래프 구조와 집계 결과를 분석하여 actionable insight를 제공합니다.

## 분석 원칙

1. **DIKW 프레임워크 준수**: 모든 답변에서 4계층을 명시적으로 구분합니다.
   - [Data] 사용된 원시 데이터 출처
   - [Information] 데이터에서 추출한 구조적 관계
   - [Knowledge] 그래프 탐색으로 발견한 패턴과 연결
   - [Wisdom] 비즈니스 의사결정에 활용 가능한 인사이트와 행동 제안

2. **근거 기반**: 모든 인사이트는 그래프 데이터에 근거해야 합니다. 추측은 명시적으로 표시합니다.

3. **정량화**: 가능한 경우 수치를 포함합니다 (비율, 건수, 금액 등).

4. **행동 제안**: 단순 관찰이 아닌, 구체적으로 "무엇을 해야 하는지"를 제안합니다.

5. **리스크 표시**: 불확실한 분석에는 신뢰 수준(높음/중간/낮음)을 표시합니다.

6. **한국어 답변**: 모든 답변은 한국어로 작성합니다.

## 답변 형식

### 패턴 발견 (Pattern)
[Data] 분석에 사용된 데이터: {데이터 출처}
[Information] 구조화된 관계: {FK/관계 설명}
[Knowledge] 발견된 패턴:
  - 패턴 1: {설명} (근거: {Cypher 결과})
  - 패턴 2: ...
[Wisdom] 비즈니스 인사이트:
  - 인사이트 1: {설명} → 권장 행동: {구체적 행동}
  - 인사이트 2: ...
  신뢰 수준: {높음/중간/낮음}

### 추천 (Recommendation)
[Data] 대상: {엔티티}, 분석 범위: {홉 수}
[Information] 관계 맵: {연결된 엔티티들}
[Knowledge] 유사 패턴: {협업 필터링 또는 컨텐츠 기반 결과}
[Wisdom] 추천:
  1. {추천 항목} — 근거: {why} (신뢰도: {%})
  2. ...

### What-If 시뮬레이션
[Data] 시뮬레이션 대상: {제거/변경할 엔티티}
[Information] 연결 구조: {직접 연결 N개, 간접 연결 M개}
[Knowledge] 영향 범위:
  - 직접 영향: {엔티티 목록}
  - 간접 영향: {2홉+ 엔티티}
  - 예상 매출 영향: {금액}
[Wisdom] 리스크 평가 및 완화 방안:
  - 리스크: {설명} (심각도: 높음/중간/낮음)
  - 완화 방안: {구체적 행동}
  - 대체 경로: {존재 여부 및 설명}
"""
```

### 4. Wisdom Router 구현 상세

```python
# backend/app/query/wisdom_router.py

import re
from enum import Enum

class WisdomIntent(str, Enum):
    LOOKUP = "lookup"           # 기존 Q&A (A안/B안)
    PATTERN = "pattern"         # W1: 패턴 발견
    CAUSAL = "causal"           # W2: 인과 분석
    RECOMMENDATION = "recommendation"  # W3: 추천
    WHAT_IF = "what_if"         # W4: What-If
    DIKW_TRACE = "dikw_trace"   # W5: DIKW 전체 추적

WISDOM_PATTERNS = {
    WisdomIntent.PATTERN: [
        r"(패턴|트렌드|경향|특징|분포|세그먼트|클러스터)",
        r"(자주|많이).*같이.*(구매|주문)",
        r"어떤.*(특징|차이|공통점)",
    ],
    WisdomIntent.CAUSAL: [
        r"왜\s",
        r"(원인|이유|영향|상관|인과)",
        r"(때문|덕분|영향.*미치)",
    ],
    WisdomIntent.RECOMMENDATION: [
        r"(추천|제안|권장|어떤.*좋을까|뭘.*해야)",
        r"(강화|개선|최적화).*해야",
        r"(주의|관리).*해야",
    ],
    WisdomIntent.WHAT_IF: [
        r"(만약|만일|가정|~면\s어떻게|~면\s어떤)",
        r"(중단|제거|이탈|없어지면|빠지면)",
        r"(영향|리스크|위험).*있나",
    ],
    WisdomIntent.DIKW_TRACE: [
        r"DIKW",
        r"(전체|종합).*(분석|보고서|리포트)",
        r"(데이터부터|처음부터).*(분석|추적)",
    ],
}

def classify_wisdom_intent(question: str) -> WisdomIntent:
    """질문의 Wisdom 의도를 분류한다."""
    for intent, patterns in WISDOM_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, question, re.IGNORECASE):
                return intent
    return WisdomIntent.LOOKUP  # 기본값: 기존 Q&A
```

### 5. 다중 Cypher 수집기 (Multi-Query Collector)

Wisdom 질문은 단일 Cypher로는 부족하다. 여러 관점의 데이터를 수집해야 한다.

```python
# backend/app/query/wisdom_collector.py

PATTERN_QUERIES = {
    "customer_segments": """
        MATCH (c:Customer)-[:PLACED]->(o:Order)
        WITH c.name AS customer, count(o) AS orders,
             sum(toFloat(o.total_amount)) AS total_spent
        RETURN customer, orders, total_spent,
          CASE WHEN total_spent > 5000000 THEN 'VIP'
               WHEN total_spent > 2000000 THEN 'Regular'
               ELSE 'Light' END AS segment
        ORDER BY total_spent DESC
    """,
    "category_distribution": """
        MATCH (o:Order)-[:CONTAINS]->(p:Product)-[:BELONGS_TO]->(cat:Category)
        RETURN cat.name AS category, count(DISTINCT o) AS order_count,
               count(DISTINCT p) AS product_count
        ORDER BY order_count DESC
    """,
    "co_purchase": """
        MATCH (o:Order)-[:CONTAINS]->(p1:Product),
              (o)-[:CONTAINS]->(p2:Product)
        WHERE id(p1) < id(p2)
        RETURN p1.name AS product_1, p2.name AS product_2,
               count(o) AS co_purchase_count
        ORDER BY co_purchase_count DESC LIMIT 10
    """,
    "supplier_dependency": """
        MATCH (s:Supplier)<-[:SUPPLIED_BY]-(p:Product)<-[:CONTAINS]-(o:Order)
        WITH s.name AS supplier, count(DISTINCT p) AS products,
             count(DISTINCT o) AS orders,
             sum(toFloat(o.total_amount)) AS revenue
        RETURN supplier, products, orders, revenue
        ORDER BY revenue DESC
    """,
    "review_quality_correlation": """
        MATCH (r:Review)-[:REVIEWS]->(p:Product)<-[:CONTAINS]-(o:Order)
        WITH p.name AS product,
             round(avg(toFloat(r.rating))*100)/100 AS avg_rating,
             count(DISTINCT o) AS order_count
        RETURN product, avg_rating, order_count
        ORDER BY avg_rating DESC
    """,
    "payment_analysis": """
        MATCH (pay:Payment)-[:PAID_FOR]->(o:Order)
        RETURN pay.method AS method, count(*) AS count,
               round(avg(toFloat(pay.amount))) AS avg_amount
        ORDER BY count DESC
    """,
    "coupon_impact": """
        MATCH (o:Order)
        OPTIONAL MATCH (o)-[:APPLIED]->(c:Coupon)
        WITH CASE WHEN c IS NOT NULL THEN 'used' ELSE 'unused' END AS status,
             toFloat(o.total_amount) AS amt
        RETURN status, count(*) AS orders, round(avg(amt)) AS avg_amount
    """,
}

# 의도별 실행할 쿼리 조합
INTENT_QUERY_MAP = {
    "pattern": ["customer_segments", "category_distribution", "co_purchase",
                "supplier_dependency", "review_quality_correlation"],
    "causal": ["review_quality_correlation", "coupon_impact", "category_distribution"],
    "recommendation": ["customer_segments", "co_purchase", "review_quality_correlation"],
    "what_if": ["supplier_dependency", "category_distribution", "customer_segments"],
    "dikw_trace": list(PATTERN_QUERIES.keys()),  # 전부 실행
}
```

### 6. DIKW Trace 응답 구조

```python
# backend/app/models/schemas.py에 추가

class DIKWLayer(BaseModel):
    level: str               # "data" | "information" | "knowledge" | "wisdom"
    title: str               # "원시 데이터" 등
    content: str             # 마크다운 텍스트
    evidence: list[str] = [] # 근거 데이터 포인트

class WisdomResponse(BaseModel):
    question: str
    intent: str              # pattern | causal | recommendation | what_if | dikw_trace
    dikw_layers: list[DIKWLayer]  # 4개 계층 분석 결과
    summary: str             # 핵심 한 줄 요약
    confidence: str          # high | medium | low
    action_items: list[str]  # 구체적 행동 제안
    related_queries: list[str]  # 추가 탐색 제안 질문
    cypher_queries_used: list[str]  # 사용된 Cypher 목록
    latency_ms: int
    llm_tokens_used: int
```

### 7. 프론트엔드 DIKW 대시보드

```
QueryPage에 "W Wisdom" 모드 추가 (기존 A/B에 이어 세 번째)

┌──────────────────────────────────────────────────┐
│  [A 템플릿]  [B 로컬]  [W 위즈덤]                  │
├──────────────────────────────────────────────────┤
│                                                  │
│  데모 질문 버튼:                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │ W1 "고객 구매 패턴에서 어떤 트렌드가 보이나요?"   │ │
│  │ W2 "리뷰 평점이 높은 상품이 실제로 더 팔리나요?"  │ │
│  │ W3 "김민수에게 어떤 상품을 추천할까요?"          │ │
│  │ W4 "애플코리아 공급 중단 시 영향은?"             │ │
│  │ W5 "김민수에 대한 DIKW 종합 분석"               │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌── 답변 영역 ──────────────────────────────────┐│
│  │                                              ││
│  │  ┌─ D ─────────────────────────────────────┐ ││
│  │  │ customers, orders, products 테이블에서   │ ││
│  │  │ 5명 고객, 8개 주문, 8개 상품 데이터 수집   │ ││
│  │  └─────────────────────────────────────────┘ ││
│  │       │                                      ││
│  │       ▼                                      ││
│  │  ┌─ I ─────────────────────────────────────┐ ││
│  │  │ 12개 FK 관계로 9개 노드 타입,            │ ││
│  │  │ 12개 관계 타입 구조화                     │ ││
│  │  └─────────────────────────────────────────┘ ││
│  │       │                                      ││
│  │       ▼                                      ││
│  │  ┌─ K ─────────────────────────────────────┐ ││
│  │  │ 김민수의 2홉 서브그래프:                  │ ││
│  │  │ 3개 주문 → 5개 상품 → 3개 카테고리 연결   │ ││
│  │  │ 동시구매 패턴: 맥북프로+에어팟프로 (2회)   │ ││
│  │  └─────────────────────────────────────────┘ ││
│  │       │                                      ││
│  │       ▼                                      ││
│  │  ┌─ W ─────────────────────────────────────┐ ││
│  │  │ [인사이트]                               │ ││
│  │  │ - VIP 세그먼트 (총 700만원, 상위 20%)     │ ││
│  │  │ - 애플 제품 선호도 67% → 공급 리스크       │ ││
│  │  │                                         │ ││
│  │  │ [추천 행동]                               │ ││
│  │  │ 1. 갤럭시탭 악세서리 번들 제안            │ ││
│  │  │ 2. 애플 대안 (LG그램) 프로모션            │ ││
│  │  │ 3. VIP 전용 쿠폰 발행                    │ ││
│  │  │                                         │ ││
│  │  │ 신뢰도: ████████░░ 80% (medium-high)    │ ││
│  │  └─────────────────────────────────────────┘ ││
│  │                                              ││
│  │  📊 사용된 Cypher 5개  ⏱ 1,250ms  🔤 890 tokens ││
│  └──────────────────────────────────────────────┘│
│                                                  │
└──────────────────────────────────────────────────┘
```

### 8. 데모 시나리오 (고객 프레젠테이션용)

```
[시나리오: B2B 고객사 CTO에게 3분 데모]

1분 — Data → Information (기존 기능)
  "이 DDL을 업로드하면, 12개 테이블에서 자동으로 9개 엔티티 타입과
   12개 관계를 추출합니다. 사람이 수동으로 하면 반나절, 우리 도구는 10초."

1분 — Information → Knowledge (기존 기능)
  "CSV 데이터를 올리면 Neo4j 그래프가 자동 생성됩니다.
   기존 Q&A로 '김민수가 주문한 상품은?' 같은 질문에 즉시 답합니다."

1분 — Knowledge → Wisdom (NEW)
  "이제 진짜 가치입니다. '고객 패턴 분석'을 누르면..."
  → DIKW 4단계가 시각적으로 펼쳐지며
  → "김민수는 VIP지만 애플 의존도가 67%입니다.
     공급 리스크를 줄이려면 LG그램 프로모션을 고려하세요."
  → "이런 인사이트를 수동으로 뽑으려면 데이터 분석가가 SQL 10개를
     짜야 합니다. 우리는 그래프 구조 덕분에 자연어 한 줄로 됩니다."

핵심 메시지:
  "귀사의 DB 스키마만 넣으면, 데이터가 정보가 되고,
   정보가 지식이 되고, 지식이 의사결정을 돕는 지혜가 됩니다.
   이것이 DIKW 피라미드이고, 이것이 우리 서비스의 가치입니다."
```

### 9. 구현 파일 목록

```
신규 생성:
  backend/app/query/wisdom_router.py    — Wisdom 의도 분류기
  backend/app/query/wisdom_collector.py — 다중 Cypher 수집기
  backend/app/query/wisdom_engine.py    — Wisdom LLM 파이프라인 (orchestrator)
  backend/app/query/wisdom_prompts.py   — Wisdom 시스템 프롬프트 + 직렬화
  backend/app/routers/wisdom.py         — POST /api/v1/wisdom/query
  backend/tests/test_wisdom.py          — Wisdom 테스트 (15+)
  frontend/src/components/wisdom/DIKWTimeline.tsx — 4계층 시각화 컴포넌트
  frontend/src/components/wisdom/WisdomCard.tsx   — 인사이트/추천 카드

수정:
  backend/app/models/schemas.py         — DIKWLayer, WisdomResponse 모델 추가
  backend/app/config.py                 — wisdom_model, wisdom_max_tokens 설정
  backend/app/main.py                   — wisdom router 등록
  frontend/src/pages/QueryPage.tsx      — W 모드 탭 + Wisdom 데모 질문 추가
  frontend/src/api/client.ts            — sendWisdomQuery() 함수 추가
  frontend/src/types/ontology.ts        — WisdomResponse TS 타입 추가
  frontend/src/constants.ts             — WISDOM_DEMO_QUESTIONS 추가
```

### 10. 구현 우선순위

```
Phase 1 (MVP — 빠르게 데모 가능한 것부터):
  ✅ WisdomResponse 모델
  ✅ Wisdom Router (regex 기반)
  ✅ Multi-Query Collector (PATTERN_QUERIES)
  ✅ Wisdom Engine (LLM 호출 + DIKW 파싱)
  ✅ POST /api/v1/wisdom/query 엔드포인트
  ✅ QueryPage W 모드 + 5개 데모 질문
  ✅ DIKWTimeline 컴포넌트 (D→I→K→W 시각적 카드)

Phase 2 (완성도):
  ○ What-If 시뮬레이션 전용 Cypher 생성기
  ○ 추천 엔진 (협업 필터링 Cypher)
  ○ 신뢰도 점수 계산 로직
  ○ DIKW 보고서 PDF 내보내기
  ○ Wisdom 답변 캐싱 (데모 안정성)
```

### 11. 테스트 골든 데이터

```python
WISDOM_GOLDEN = [
    {
        "id": "W1-01",
        "question": "고객 구매 패턴에서 어떤 트렌드가 보이나요?",
        "intent": "pattern",
        "expected_keywords": ["VIP", "세그먼트", "카테고리", "노트북", "오디오"],
        "expected_layers": ["data", "information", "knowledge", "wisdom"],
    },
    {
        "id": "W2-01",
        "question": "리뷰 평점이 높은 상품이 더 많이 팔리나요?",
        "intent": "causal",
        "expected_keywords": ["상관", "평점", "판매", "맥북"],
    },
    {
        "id": "W3-01",
        "question": "김민수에게 어떤 상품을 추천하면 좋을까요?",
        "intent": "recommendation",
        "expected_keywords": ["추천", "김민수"],
    },
    {
        "id": "W4-01",
        "question": "애플코리아 공급이 중단되면 어떤 영향이 있나요?",
        "intent": "what_if",
        "expected_keywords": ["애플코리아", "영향", "맥북", "에어팟"],
    },
    {
        "id": "W5-01",
        "question": "김민수에 대한 DIKW 종합 분석을 해줘",
        "intent": "dikw_trace",
        "expected_keywords": ["Data", "Information", "Knowledge", "Wisdom", "김민수"],
        "expected_layers": ["data", "information", "knowledge", "wisdom"],
    },
]
```

---

## 핵심 가치 제안 (왜 고객이 이것을 원하는가)

| 현재 (Knowledge까지) | Wisdom 추가 후 |
|---------------------|---------------|
| "김민수 주문 상품: 맥북프로, 에어팟프로" | "김민수는 VIP(700만원)이며 애플 의존도 67%. LG그램 번들 제안 시 cross-sell 가능성 높음" |
| "가장 많이 팔린 카테고리: 노트북" | "노트북이 1위지만 성장률 둔화. 태블릿 카테고리가 신규 고객 유입 채널로 부상 중. 태블릿 라인업 확대 권장" |
| "쿠폰 사용 58%, 미사용 42%" | "쿠폰 사용 고객의 평균 주문금액이 23% 높음. 신규 고객 첫 구매에 쿠폰 제공 시 LTV 증가 예상" |
| (질문 불가) | "애플코리아 공급 중단 시 매출의 45%가 위험. 대안: LG전자 노트북 라인업으로 대체 가능하나 오디오는 대체재 없음 → 소니 공급계약 검토 필요" |

**한 문장 요약**: Data를 넣으면 Wisdom이 나오는 서비스. 그것이 GraphRAG의 가치입니다.
