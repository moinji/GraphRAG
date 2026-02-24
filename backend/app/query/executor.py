"""Query executor: hardcoded Q→template mapping → Neo4j → formatted results.

v0 has 3 demo questions with fixed template slot filling (no LLM router).
"""

from __future__ import annotations

from neo4j import GraphDatabase

from app.models.schemas import QueryResult
from app.query.templates import AGG_WITH_REL, Q2_CUSTOM, TWO_HOP

# ── Demo questions ─────────────────────────────────────────────────

DEMO_QUESTIONS = [
    {
        "id": "Q1",
        "question": "고객 김민수가 주문한 상품은?",
        "template_id": "two_hop",
        "cypher": TWO_HOP.format(
            start_label="Customer",
            start_prop="name",
            rel1="PLACED",
            mid_label="Order",
            rel2="CONTAINS",
            end_label="Product",
            return_prop="name",
        ),
        "params": {"start_value": "김민수"},
    },
    {
        "id": "Q2",
        "question": "김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?",
        "template_id": "custom_q2",
        "cypher": Q2_CUSTOM,
        "params": {"name": "김민수", "limit": 3},
    },
    {
        "id": "Q3",
        "question": "가장 많이 팔린 카테고리 Top 3는?",
        "template_id": "agg_with_rel",
        "cypher": AGG_WITH_REL.format(
            start_label="Order",
            rel1="CONTAINS",
            mid_label="Product",
            rel2="BELONGS_TO",
            end_label="Category",
            group_prop="name",
        ),
        "params": {"limit": 3},
    },
]


def _format_paths_q1(records: list[dict], name: str) -> list[str]:
    """Format evidence paths for Q1 (two-hop)."""
    paths = []
    for rec in records:
        product = rec["result"]
        paths.append(
            f"Customer({name}) -> PLACED -> Order -> CONTAINS -> Product({product})"
        )
    return paths


def _format_paths_q2(records: list[dict], name: str) -> list[str]:
    paths = []
    for rec in records:
        product = rec["product"]
        category = rec["category"]
        rating = rec["avg_rating"]
        paths.append(
            f"Customer({name}) -> PLACED -> Order -> CONTAINS -> Product(*) "
            f"-> BELONGS_TO -> Category({category}) "
            f"<- BELONGS_TO <- Product({product}) "
            f"<- REVIEWS <- Review [avg={rating}]"
        )
    return paths


def _format_paths_q3(records: list[dict]) -> list[str]:
    paths = []
    for rec in records:
        cat = rec["category"]
        cnt = rec["order_count"]
        paths.append(
            f"Order(*) -> CONTAINS -> Product(*) "
            f"-> BELONGS_TO -> Category({cat}) [count={cnt}]"
        )
    return paths


def _build_answer_q1(records: list[dict]) -> str:
    products = [r["result"] for r in records]
    return f"김민수 고객이 주문한 상품: {', '.join(products)}"


def _build_answer_q2(records: list[dict]) -> str:
    lines = []
    for i, r in enumerate(records, 1):
        lines.append(f"{i}위 {r['product']}({r['category']}, 평점 {r['avg_rating']})")
    return "김민수가 주문한 상품 카테고리 내 리뷰 평점 Top 3: " + ", ".join(lines)


def _build_answer_q3(records: list[dict]) -> str:
    lines = []
    for i, r in enumerate(records, 1):
        lines.append(f"{i}위 {r['category']}({r['order_count']}건)")
    return "가장 많이 팔린 카테고리 Top 3: " + ", ".join(lines)


def execute_demo_queries(
    uri: str, user: str, password: str
) -> list[QueryResult]:
    """Run all 3 demo questions and return QueryResult list."""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    results: list[QueryResult] = []

    with driver.session() as session:
        for q in DEMO_QUESTIONS:
            records = [
                dict(r)
                for r in session.run(q["cypher"], **q["params"])
            ]

            qid = q["id"]
            if qid == "Q1":
                answer = _build_answer_q1(records)
                paths = _format_paths_q1(records, "김민수")
            elif qid == "Q2":
                answer = _build_answer_q2(records)
                paths = _format_paths_q2(records, "김민수")
            else:
                answer = _build_answer_q3(records)
                paths = _format_paths_q3(records)

            results.append(QueryResult(
                question=q["question"],
                answer=answer,
                cypher=q["cypher"],
                paths=paths,
                template_id=q["template_id"],
            ))

    driver.close()
    return results
