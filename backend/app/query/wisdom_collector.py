"""Multi-query Cypher collector for Wisdom engine.

Wisdom questions require multiple data perspectives — this module
defines query sets and maps intents to the right combination.
"""

from __future__ import annotations

import logging

from app.db.neo4j_client import get_driver
from app.exceptions import CypherExecutionError

logger = logging.getLogger(__name__)

# ── Reusable Cypher queries ────────────────────────────────────────

WISDOM_QUERIES: dict[str, str] = {
    "customer_segments": """
        MATCH (c:Customer)-[:PLACED]->(o:Order)
        WITH c.name AS customer, count(o) AS orders,
             sum(toFloat(o.total_amount)) AS total_spent
        RETURN customer, orders, round(total_spent) AS total_spent,
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
        RETURN supplier, products, orders, round(revenue) AS revenue
        ORDER BY revenue DESC
    """,
    "review_quality": """
        MATCH (r:Review)-[:REVIEWS]->(p:Product)<-[:CONTAINS]-(o:Order)
        WITH p.name AS product,
             round(avg(toFloat(r.rating))*100)/100 AS avg_rating,
             count(DISTINCT o) AS order_count
        RETURN product, avg_rating, order_count
        ORDER BY avg_rating DESC
    """,
    "coupon_impact": """
        MATCH (o:Order)
        OPTIONAL MATCH (o)-[:APPLIED]->(c:Coupon)
        WITH CASE WHEN c IS NOT NULL THEN 'used' ELSE 'unused' END AS status,
             toFloat(o.total_amount) AS amt
        RETURN status, count(*) AS orders, round(avg(amt)) AS avg_amount
    """,
    "payment_methods": """
        MATCH (pay:Payment)-[:PAID_FOR]->(o:Order)
        RETURN pay.method AS method, count(*) AS count,
               round(avg(toFloat(pay.amount))) AS avg_amount
        ORDER BY count DESC
    """,
}

# ── Entity-specific queries (parameterized) ────────────────────────

ENTITY_QUERIES: dict[str, str] = {
    "customer_orders": """
        MATCH (c:Customer {name: $entity_name})-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
        -[:BELONGS_TO]->(cat:Category)
        RETURN o.id AS order_id, round(toFloat(o.total_amount)) AS amount,
               collect(p.name) AS products, collect(DISTINCT cat.name) AS categories
    """,
    "customer_reviews": """
        MATCH (c:Customer {name: $entity_name})-[:WROTE]->(r:Review)-[:REVIEWS]->(p:Product)
        RETURN p.name AS product, r.rating AS rating, r.comment AS comment
    """,
    "customer_graph_2hop": """
        MATCH (c:Customer {name: $entity_name})-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
        OPTIONAL MATCH (p)-[:SUPPLIED_BY]->(s:Supplier)
        OPTIONAL MATCH (p)-[:BELONGS_TO]->(cat:Category)
        RETURN c.name AS customer, collect(DISTINCT p.name) AS products,
               collect(DISTINCT s.name) AS suppliers,
               collect(DISTINCT cat.name) AS categories,
               count(DISTINCT o) AS order_count,
               sum(toFloat(o.total_amount)) AS total_spent
    """,
    "supplier_impact": """
        MATCH (s:Supplier {name: $entity_name})<-[:SUPPLIED_BY]-(p:Product)
        OPTIONAL MATCH (p)<-[:CONTAINS]-(o:Order)<-[:PLACED]-(c:Customer)
        WITH s, collect(DISTINCT p.name) AS products,
             collect(DISTINCT c.name) AS affected_customers,
             count(DISTINCT o) AS affected_orders,
             sum(toFloat(o.total_amount)) AS at_risk_revenue
        RETURN s.name AS supplier, products, affected_customers,
               affected_orders, round(at_risk_revenue) AS at_risk_revenue
    """,
    "supplier_alternatives": """
        MATCH (s:Supplier {name: $entity_name})<-[:SUPPLIED_BY]-(p:Product)-[:BELONGS_TO]->(cat:Category)
        WITH collect(DISTINCT cat.name) AS categories
        UNWIND categories AS cat_name
        MATCH (alt_p:Product)-[:BELONGS_TO]->(cat2:Category {name: cat_name})
        MATCH (alt_p)-[:SUPPLIED_BY]->(alt_s:Supplier)
        WHERE alt_s.name <> $entity_name
        RETURN cat_name AS category, collect(DISTINCT alt_s.name) AS alternative_suppliers,
               collect(DISTINCT alt_p.name) AS alternative_products
    """,
    "recommendation_collab": """
        MATCH (target:Customer {name: $entity_name})-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product)
        WITH target, collect(p) AS bought
        MATCH (other:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(common:Product)
        WHERE common IN bought AND other <> target
        MATCH (other)-[:PLACED]->(:Order)-[:CONTAINS]->(rec:Product)
        WHERE NOT rec IN bought
        RETURN rec.name AS recommended_product, count(DISTINCT other) AS recommender_count,
               collect(DISTINCT other.name) AS similar_customers
        ORDER BY recommender_count DESC
        LIMIT 5
    """,
}

# ── Intent → query set mapping ─────────────────────────────────────

INTENT_QUERY_MAP: dict[str, list[str]] = {
    "pattern": [
        "customer_segments", "category_distribution", "co_purchase",
        "supplier_dependency", "review_quality",
    ],
    "causal": [
        "review_quality", "coupon_impact", "category_distribution",
        "customer_segments",
    ],
    "recommendation": [
        "customer_segments", "co_purchase", "review_quality",
    ],
    "what_if": [
        "supplier_dependency", "category_distribution", "customer_segments",
    ],
    "dikw_trace": list(WISDOM_QUERIES.keys()),
}


_KNOWN_LABELS = [
    "Customer", "Order", "Product", "Category", "Supplier",
    "Review", "Payment", "Coupon", "Shipping", "Address",
]


def collect_data(
    intent: str,
    entity_name: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, list[dict]]:
    """Execute multiple Cypher queries and return {query_key: records}."""
    from app.tenant import prefix_cypher_labels

    query_keys = INTENT_QUERY_MAP.get(intent, list(WISDOM_QUERIES.keys()))
    results: dict[str, list[dict]] = {}

    try:
        driver = get_driver()
        with driver.session() as session:
            # Global queries
            for key in query_keys:
                cypher = WISDOM_QUERIES.get(key)
                if cypher is None:
                    continue
                cypher = prefix_cypher_labels(cypher, tenant_id, _KNOWN_LABELS)
                try:
                    records = [dict(r) for r in session.run(cypher)]
                    results[key] = records
                except Exception as e:
                    logger.warning("Wisdom query '%s' failed: %s", key, e)
                    results[key] = []

            # Entity-specific queries
            if entity_name:
                entity_keys = _entity_queries_for_intent(intent)
                for key in entity_keys:
                    cypher = ENTITY_QUERIES.get(key)
                    if cypher is None:
                        continue
                    cypher = prefix_cypher_labels(cypher, tenant_id, _KNOWN_LABELS)
                    try:
                        records = [
                            dict(r)
                            for r in session.run(cypher, entity_name=entity_name)
                        ]
                        results[key] = records
                    except Exception as e:
                        logger.warning("Entity query '%s' failed: %s", key, e)
                        results[key] = []

    except Exception as e:
        raise CypherExecutionError(f"Wisdom data collection failed: {e}")

    return results


def _entity_queries_for_intent(intent: str) -> list[str]:
    """Select entity-specific queries based on intent."""
    if intent == "recommendation":
        return ["customer_graph_2hop", "customer_orders", "recommendation_collab"]
    if intent == "what_if":
        return ["supplier_impact", "supplier_alternatives"]
    if intent == "dikw_trace":
        return ["customer_graph_2hop", "customer_orders", "customer_reviews"]
    return ["customer_graph_2hop"]
