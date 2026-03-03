# Week 7 Demo Script (3 minutes)

## Prerequisites
```bash
docker-compose up -d          # Neo4j + PostgreSQL
cd backend && uvicorn app.main:app --reload
cd frontend && npm run dev
```

## Timeline

### [0:00 - 0:30] DDL Upload + Ontology Generation
1. Open http://localhost:3000
2. Upload `demo_ecommerce.sql` (12 tables)
3. Click **Generate Ontology** (skip_llm=true)
4. Confirm: **9 node types, 12 relationships**
5. Show derivation badges (blue FK badges)

### [0:30 - 1:00] Review + Approve
1. Switch to **Review** mode tab
2. Browse node/relationship tables
3. Click **Approve** -> status changes to "approved"

### [1:00 - 1:30] KG Build
1. Click **Build KG** button (appears after approve)
2. Watch progress polling (queued -> running -> succeeded)
3. Confirm nodes_created / relationships_created counts

### [1:30 - 3:00] Q&A Demo (5 questions)
Click each demo question button in order:

| # | Question | Expected Answer |
|---|----------|----------------|
| Q1 | 고객 김민수가 주문한 상품은? | 맥북프로, 에어팟프로, 갤럭시탭 |
| Q2 | 김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은? | 1위 맥북에어(5.0), 2위 에어팟프로(4.67), 3위 아이패드에어(4.5) |
| Q3 | 가장 많이 팔린 카테고리 Top 3는? | 1위 노트북(6건), 2위 오디오(4건), 3위 태블릿(2건) |
| Q4 | 김민수와 이영희가 공통으로 구매한 상품은? | 맥북프로 |
| Q5 | 쿠폰 사용 주문과 미사용 주문의 평균 금액 비교 | 사용 3건 avg 1793367원, 미사용 5건 avg 2622800원 |

**Key points to highlight per question:**
- Expand **Cypher** collapsible to show generated query
- Show **Evidence Paths** with graph traversal steps
- Point out **cached** green badge (mode A uses golden cache)
- Toggle to **B Local** mode for comparison (requires API key)

## Talking Points
- **5/5 demo questions** work with rule router only (no API key needed)
- **temperature=0** for deterministic LLM responses
- **Cached answers** enable offline demo without Neo4j dependency
- **A/B comparison**: Template (fast, deterministic) vs Local Search (flexible, LLM-powered)
- Full pipeline: DDL -> 9 nodes + 12 rels -> KG -> Q&A in under 3 minutes
