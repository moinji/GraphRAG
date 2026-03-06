# R2RML 도입 타당성 분석

> 작성일: 2026-03-06
> 대상 프로젝트: GraphRAG (DDL → Knowledge Graph → Q&A, B2B SaaS)
> 현재 버전: v0.9.0 (185 tests passing)

---

## 1. 기술적 적합성 (Technical Fit)

### 근본적 불일치: RDF vs Property Graph

R2RML의 출력은 RDF 트리플 `(subject, predicate, object)`이다. 현재 프로젝트의 타겟은 Neo4j Property Graph로, 노드와 엣지에 **다중 속성(property)**을 직접 부여하는 모델이다. 이 둘은 구조적으로 다르다:

| 특성 | RDF 트리플 | Neo4j Property Graph |
|---|---|---|
| 속성 표현 | 별도 트리플 (reification 필요) | 노드/엣지에 key-value 직접 부착 |
| 관계 속성 | 매우 번거로움 (RDF-star 또는 중간 노드) | `CONTAINS {quantity: 3}` 자연스러움 |
| 쿼리 언어 | SPARQL | Cypher |
| 스키마 유연성 | OWL/RDFS 온톨로지 | 레이블 + 제약조건 |

현재 `RelationshipType.properties`(예: order_items의 quantity, unit_price)는 Property Graph에서 자연스럽지만 RDF에서는 reification이 필요하다. R2RML을 도입하면 **이미 잘 동작하는 관계 속성 매핑을 더 복잡하게 만드는** 역효과가 발생한다.

### 변환 경로 비교

```
현재:  DDL → fk_rule_engine → OntologySpec → Neo4j MERGE     (1단계 변환)
R2RML: DDL → R2RML 매핑 → RDF 트리플 → PG 변환 → Neo4j MERGE (3단계 변환)
```

중간에 RDF 직렬화/역직렬화가 추가되면 성능 저하가 불가피하다. Morph-KGC 등의 R2RML 실행기는 대량 데이터 변환에 최적화되어 있지만, 그 출력이 RDF이므로 다시 Property Graph로 변환하는 추가 레이어가 필요하다. 이는 **해결하는 문제보다 만드는 문제가 더 많은** 전형적 over-engineering이다.

### R2RML 표현력이 우수한 경우

- **조건부 매핑** (`rr:condition`): "status = 'active'인 행만 노드로 변환" — 현재 rule engine에는 없지만, 필요 시 Python if문 한 줄로 해결 가능
- **다대다 관계**: 현재 `JOIN_TABLE_CONFIG`으로 이미 처리 중 (order_items, wishlists, shipping)
- **자기참조 FK**: `DIRECTION_MAP`에 `("categories", "parent_id")` → `PARENT_OF`로 이미 처리
- **SQL 뷰 기반 매핑** (`rr:sqlQuery`): 복잡한 SQL로 가상 테이블을 정의 후 매핑 — 유일하게 현재 없는 기능이나, 현재 파이프라인에서 필요한 시나리오가 없음

### RDF 생태계의 실질적 가치

OWL 추론(상위 카테고리 자동 추론 등), SHACL 검증(온톨로지 제약 자동 검증)은 이론적으로 매력적이나, 현재 프로젝트의 가치 제안은 **"DDL → Q&A까지 10분"**이다. RDF 추론 엔진을 도입하면 파이프라인 복잡도가 급증하고, 타겟 사용자(B2B 데이터 엔지니어)에게 SPARQL/OWL 개념을 노출하게 된다. **현 단계에서 실질적 가치 없음.**

---

## 2. 범용화 기여도 (Generalization Impact)

### 핵심 질문: "도메인별 하드코딩" 문제를 R2RML이 해결하는가?

아니다. R2RML은 **매핑을 선언적으로 표현하는 형식**이지, 매핑을 자동으로 생성하는 엔진이 아니다.

```
현재:   새 도메인 → TABLE_TO_LABEL, DIRECTION_MAP 수동 추가
R2RML:  새 도메인 → R2RML .ttl 매핑 파일 수동 작성
```

문제의 본질은 **"누가 매핑 규칙을 만드는가"**인데, R2RML은 규칙의 **저장 형식**만 바꿀 뿐이다. 오히려 R2RML의 Turtle 문법은 Python 딕셔너리보다 학습 곡선이 높다:

```turtle
# R2RML로 customers → Customer 매핑
<#CustomerMapping>
    rr:logicalTable [ rr:tableName "customers" ];
    rr:subjectMap [ rr:template "http://example.com/customer/{id}"; rr:class ex:Customer ];
    rr:predicateObjectMap [ rr:predicate ex:name; rr:objectMap [ rr:column "name" ] ].
```

vs 현재:

```python
TABLE_TO_LABEL = {"customers": "Customer"}
```

### 대안별 ROI 비교

**(A) 자동 매핑 로직 강화** — 현재 미등록 테이블 자동 매핑(`_to_pascal_case`, `_auto_rel_name`)이 이미 있다. 이것을 강화하면:
- FK 방향 추론 휴리스틱 (1:N 관계에서 N쪽이 FK를 소유 → 방향 자동 결정)
- 조인 테이블 자동 감지 (PK 없이 FK 2개만 있는 테이블)
- 비용: 1~2주, 기존 코드 자연스러운 확장

**(B) R2RML 도입** — 매핑 자동 생성 문제를 해결하지 못하면서 변환 레이어만 추가. 비용: 3~5주, 기존 파이프라인 대규모 수정

**(C) LLM 매핑 자동 생성 강화** — 이미 Stage 2 LLM enrichment가 있다. DDL만으로 LLM이 `OntologySpec` JSON을 직접 생성하도록 확장하면:
- FK 없는 암묵적 관계도 추론 가능 (예: "products.brand_name → brands 테이블이 없어도 Brand 개념 추출")
- 비용: 1~2주, `llm_enricher.py` 확장

**결론: 범용화의 핵심 병목은 "매핑 형식"이 아니라 "매핑 자동 생성"이며, R2RML은 이 병목을 해결하지 못한다.**

---

## 3. 개발 비용 (Implementation Cost)

### R2RML 도입 시 작업량 (1인 개발자 기준)

| 작업 | 예상 기간 | 난이도 | 비고 |
|---|---|---|---|
| R2RML 파서 통합 (Morph-KGC/rdflib) | 1주 | 중 | Python 패키지 존재, 설정 학습 필요 |
| OntologySpec ↔ R2RML 변환 레이어 | 1.5주 | 상 | 양방향 변환, Property Graph 속성 매핑이 난관 |
| RDF → Neo4j PG 변환 로직 | 1주 | 상 | 관계 속성(reification) 역변환이 핵심 난이도 |
| loader.py 수정 | 0.5주 | 중 | 현재 UNWIND+MERGE 로직과 통합 |
| 기존 185 테스트 호환성 | 1주 | 중 | OntologySpec 인터페이스 변경 시 연쇄 수정 |
| 프론트엔드 Review UI 수정 | 0.5주 | 하 | R2RML을 숨기면 최소, 노출하면 대규모 |
| **합계** | **5.5~6주** | | |

### 자동 매핑 강화만 하는 경우

| 작업 | 예상 기간 |
|---|---|
| 조인 테이블 자동 감지 | 2일 |
| FK 방향 휴리스틱 개선 | 3일 |
| 미등록 도메인 통합 테스트 | 2일 |
| **합계** | **1.5주** |

**비용 차이: 약 4배.** R2RML 도입은 현재 v0.9.0의 안정성을 훼손할 리스크도 크다. 185개 테스트의 상당수가 `OntologySpec` 기반이므로 중간 표현 변경 시 연쇄 파급이 발생한다.

---

## 4. 사용자 경험 영향 (UX Impact)

### 타겟 사용자가 R2RML을 이해할 수 있는가?

타겟은 "DDL을 가진 B2B 기업의 데이터 엔지니어/PM"이다. DDL(SQL)은 이들의 모국어이지만, R2RML(Turtle/RDF)은 시맨틱 웹 전문가의 영역이다. R2RML을 사용자에게 노출하면 TTV가 10분에서 수 시간으로 폭증한다.

### 내부 구현으로 숨기는 경우

사용자에게 보이는 가치가 **전혀 없다**. 현재 UI(NodeTypeTable, RelationshipTable, DiffPanel)는 `OntologySpec` 기반이며, R2RML이 내부에서 쓰이든 Python 딕셔너리가 쓰이든 사용자 경험은 동일하다. 즉 6주를 투자해서 **사용자가 모르는 내부 복잡도만 증가**시키는 결과가 된다.

### TTV 영향

현재 파이프라인은 DDL 업로드 → FK rule engine (밀리초) → 즉시 Review UI 표시다. R2RML 경로를 추가하면 RDF 직렬화/역직렬화 오버헤드가 추가된다. 양 자체는 작지만 방향이 잘못되었다 — TTV를 줄여야 하는 시점에 파이프라인 단계를 늘리는 것은 역행이다.

---

## 5. 시장/경쟁 포지셔닝 (Market Positioning)

### R2RML 지원을 마케팅 포인트로 쓸 수 있는 시나리오

- 엔터프라이즈 RFP에서 "W3C 표준 준수" 체크박스가 요구되는 경우
- 기존 R2RML 매핑 파일을 가진 조직이 마이그레이션하려는 경우
- Linked Data / FAIR 데이터 원칙을 따르는 학술/공공 기관

그러나 현재 타겟 시장(B2B 이커머스, 향후 의료/금융/물류)에서 R2RML 매핑 파일을 이미 보유한 조직은 **극소수**다. 이들은 이미 Stardog, GraphDB 같은 RDF 네이티브 제품을 사용하고 있을 가능성이 높다.

### 경쟁 제품 현황

| 제품 | R2RML 지원 | 비고 |
|---|---|---|
| Stardog | 네이티브 지원 | RDF 전문 제품, 다른 시장 |
| GraphDB (Ontotext) | 네이티브 지원 | RDF 전문 제품 |
| Neo4j | 미지원 | Property Graph 전문, Neosemantics(n10s)로 RDF 임포트는 가능 |
| Amazon Neptune | RDF + PG 이중 지원 | 엔터프라이즈급, 직접 경쟁 아님 |
| 본 프로젝트 | 미지원 | DDL → PG 자동 변환이 차별점 |

### 핵심 인사이트

본 프로젝트의 차별점은 "R2RML 지원"이 아니라 **"DDL만 넣으면 KG가 자동 생성된다"**는 것이다. R2RML 지원은 이 메시지를 희석시킨다. "W3C 표준 준수"는 RDF 시장에서는 의미 있지만, Property Graph + RAG 시장에서는 **구매 결정 요인이 아니다.**

---

## 6. 대안 비교 매트릭스

| 평가 기준 | **(A) 현재 유지 + 자동매핑 강화** | **(B) R2RML 내부 도입** | **(C) LLM 매핑 자동생성 강화** | **(D) 하이브리드 (R2RML 형식 차용 + 자체 실행)** |
|---|---|---|---|---|
| **범용화 기여도** | 중 — 휴리스틱 한계 존재 | 하 — 형식만 바뀜, 자동생성 아님 | 상 — 도메인 무관 추론 가능 | 중 — 선언적 형식은 좋으나 자동생성 별도 |
| **개발 비용** | 1.5주 | 5.5~6주 | 1.5~2주 | 3~4주 |
| **유지보수 복잡도** | 하 — 기존 코드 자연 확장 | 상 — RDF 의존성, 변환 레이어 | 중 — LLM 프롬프트 관리 필요 | 중 — 커스텀 파서 유지 필요 |
| **사용자 가치** | 중 — 자동매핑 정확도 향상 체감 | 없음 — 내부에 숨기면 투명 | 상 — "DDL만 넣으면 끝" 완성 | 하 — 매핑 파일 편집 UI 필요 |
| **시장 차별점** | 하 — 현상 유지 | 중 — W3C 표준 마케팅 가능 | 상 — "AI 자동 매핑" 강력한 메시지 | 하 — 어중간한 포지션 |
| **기존 코드 호환성** | 최상 — OntologySpec 불변 | 하 — 중간 표현 변경 연쇄 파급 | 상 — OntologySpec 출력 동일 | 중 — 새 파서 + 기존 로더 통합 |
| **종합 추천도** | ★★★★☆ | ★★☆☆☆ | ★★★★★ | ★★★☆☆ |

---

## 최종 권고: 미도입

1. **R2RML은 RDF 생태계를 위한 표준이며, Property Graph 타겟인 이 프로젝트에는 근본적으로 맞지 않는다.** 6주를 투자해도 사용자에게 보이는 가치가 없고, 범용화 병목(매핑 자동 생성)을 해결하지 못한다.

2. **대신 (C) LLM 매핑 자동생성 강화를 권고한다.** 이미 Stage 2 LLM enrichment가 존재하므로, 이를 확장하여 DDL만으로 `OntologySpec`을 자동 생성하는 경로를 만드는 것이 1.5~2주 투자로 가장 높은 범용화 ROI를 달성한다.

3. **R2RML에서 빌려올 가치가 있는 유일한 개념은 "선언적 매핑 파일"이다.** 현재 Python 딕셔너리 하드코딩 대신 JSON/YAML 매핑 설정 파일로 외부화하는 것은 (A)의 일부로 0.5주면 가능하며, R2RML 전체를 도입할 필요 없이 이 이점만 취할 수 있다.
