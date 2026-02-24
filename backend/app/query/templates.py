"""Cypher query templates for the v0 demo.

Three template types:
  1. two_hop       – 2-hop traversal (e.g. Customer→Order→Product)
  2. three_hop_top_n – 3-hop with aggregation + Top N
  3. agg_with_rel  – aggregate counts through relationships
"""

# ── Template 1: two_hop ────────────────────────────────────────────
# Slots: start_label, start_prop, rel1, mid_label, rel2, end_label, return_prop
TWO_HOP = """
MATCH (a:{start_label} {{{start_prop}: $start_value}})
      -[:{rel1}]->(b:{mid_label})
      -[:{rel2}]->(c:{end_label})
RETURN DISTINCT c.{return_prop} AS result
""".strip()


# ── Template 2: three_hop_top_n (custom for Q2) ───────────────────
# Q2 requires: find categories of customer's products, then get
# top-N products by avg review rating in those categories.
# This can't be expressed as a simple template, so it's a fixed query.
Q2_CUSTOM = """
MATCH (c:Customer {name: $name})
      -[:PLACED]->(:Order)
      -[:CONTAINS]->(p:Product)
      -[:BELONGS_TO]->(cat:Category)
WITH collect(DISTINCT cat) AS cats
UNWIND cats AS cat
MATCH (p2:Product)-[:BELONGS_TO]->(cat)
MATCH (rev:Review)-[:REVIEWS]->(p2)
WITH p2.name AS product, cat.name AS category,
     round(avg(toFloat(rev.rating)) * 100) / 100 AS avg_rating
ORDER BY avg_rating DESC
LIMIT $limit
RETURN product, category, avg_rating
""".strip()


# ── Template 3: agg_with_rel ──────────────────────────────────────
# Slots: start_label, rel1, mid_label, rel2, end_label, group_prop, limit
AGG_WITH_REL = """
MATCH (a:{start_label})-[:{rel1}]->(b:{mid_label})-[:{rel2}]->(c:{end_label})
RETURN c.{group_prop} AS category, count(DISTINCT a) AS order_count
ORDER BY order_count DESC
LIMIT $limit
""".strip()
