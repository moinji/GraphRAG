"""Cypher template registry — 10 generic + 3 custom templates.

Each template has named slots (e.g. {start_label}) for node labels / rel types,
and $-prefixed Neo4j parameters (e.g. $val) for runtime values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TemplateSpec:
    template_id: str
    category: str           # traverse | aggregate
    description: str
    cypher: str
    slots: list[str]        # label/rel slots to fill via str.format()
    params: list[str]       # Neo4j $params expected at runtime
    example_question: str = ""


# ── Generic templates ────────────────────────────────────────────

_ONE_HOP_OUT = """
MATCH (a:{start_label} {{{start_prop}: $val}})
      -[:{rel1}]->(b:{end_label})
RETURN DISTINCT b.{return_prop} AS result
""".strip()

_ONE_HOP_IN = """
MATCH (a:{end_label})-[:{rel1}]->(b:{start_label} {{{start_prop}: $val}})
RETURN DISTINCT a.{return_prop} AS result
""".strip()

_TWO_HOP = """
MATCH (a:{start_label} {{{start_prop}: $val}})
      -[:{rel1}]->(b:{mid_label})
      -[:{rel2}]->(c:{end_label})
RETURN DISTINCT c.{return_prop} AS result
""".strip()

_THREE_HOP = """
MATCH (a:{start_label} {{{start_prop}: $val}})
      -[:{rel1}]->(b:{mid1_label})
      -[:{rel2}]->(c:{mid2_label})
      -[:{rel3}]->(d:{end_label})
RETURN DISTINCT d.{return_prop} AS result
""".strip()

_TOP_N = """
MATCH (a:{start_label})-[:{rel1}]->(b:{end_label})
RETURN b.{group_prop} AS category, count(a) AS cnt
ORDER BY cnt DESC
LIMIT $limit
""".strip()

_FILTERED = """
MATCH (a:{start_label} {{{filter_prop}: $filter_val}})
      -[:{rel1}]->(b:{end_label})
RETURN DISTINCT b.{return_prop} AS result
""".strip()

_COMMON_NEIGHBOR = """
MATCH (a:{start_label} {{{start_prop}: $val1}})-[:{rel1}]->(c:{mid_label})<-[:{rel1}]-(b:{start_label} {{{start_prop}: $val2}})
RETURN DISTINCT c.{return_prop} AS result
""".strip()

_SHORTEST_PATH = """
MATCH p = shortestPath(
  (a:{start_label} {{{start_prop}: $val1}})-[*..{max_depth}]-(b:{end_label} {{{end_prop}: $val2}})
)
RETURN [n IN nodes(p) | labels(n)[0] + '(' + coalesce(n.name, n.id, '') + ')'] AS path_nodes
""".strip()

_AGG_WITH_REL = """
MATCH (a:{start_label})-[:{rel1}]->(b:{mid_label})-[:{rel2}]->(c:{end_label})
RETURN c.{group_prop} AS category, count(DISTINCT a) AS order_count
ORDER BY order_count DESC
LIMIT $limit
""".strip()

_STATUS_FILTER = """
MATCH (a:{start_label})-[:{rel1}]->(b:{end_label})
WHERE a.{status_prop} {op} $status_val
RETURN DISTINCT b.{return_prop} AS result
""".strip()

# ── Custom templates (domain-specific) ───────────────────────────

_CUSTOM_Q2 = """
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

_CUSTOM_Q4 = """
MATCH (c1:Customer {name: $name1})-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product)
WHERE EXISTS {{
  MATCH (c2:Customer {{name: $name2}})-[:PLACED]->(:Order)-[:CONTAINS]->(p)
}}
RETURN DISTINCT p.name AS product
""".strip()

_CUSTOM_Q5 = """
MATCH (o:Order)
OPTIONAL MATCH (o)-[:APPLIED]->(coup:Coupon)
WITH
  CASE WHEN coup IS NOT NULL THEN 'used' ELSE 'unused' END AS coupon_status,
  toFloat(o.total_amount) AS amt
RETURN coupon_status, count(*) AS order_count,
       round(avg(amt) * 100) / 100 AS avg_amount
""".strip()


# ── Registry ─────────────────────────────────────────────────────

REGISTRY: dict[str, TemplateSpec] = {
    "one_hop_out": TemplateSpec(
        template_id="one_hop_out",
        category="traverse",
        description="1-hop outgoing traversal",
        cypher=_ONE_HOP_OUT,
        slots=["start_label", "start_prop", "rel1", "end_label", "return_prop"],
        params=["val"],
        example_question="고객 김민수의 주소는?",
    ),
    "one_hop_in": TemplateSpec(
        template_id="one_hop_in",
        category="traverse",
        description="1-hop incoming traversal",
        cypher=_ONE_HOP_IN,
        slots=["end_label", "start_label", "start_prop", "rel1", "return_prop"],
        params=["val"],
        example_question="Product X를 공급하는 업체는?",
    ),
    "two_hop": TemplateSpec(
        template_id="two_hop",
        category="traverse",
        description="2-hop chain traversal",
        cypher=_TWO_HOP,
        slots=["start_label", "start_prop", "rel1", "mid_label", "rel2", "end_label", "return_prop"],
        params=["val"],
        example_question="김민수가 주문한 상품은?",
    ),
    "three_hop": TemplateSpec(
        template_id="three_hop",
        category="traverse",
        description="3-hop chain traversal",
        cypher=_THREE_HOP,
        slots=["start_label", "start_prop", "rel1", "mid1_label", "rel2", "mid2_label", "rel3", "end_label", "return_prop"],
        params=["val"],
        example_question="김민수가 주문한 상품의 카테고리는?",
    ),
    "top_n": TemplateSpec(
        template_id="top_n",
        category="aggregate",
        description="Top N aggregation",
        cypher=_TOP_N,
        slots=["start_label", "rel1", "end_label", "group_prop"],
        params=["limit"],
        example_question="가장 주문이 많은 고객 Top 5는?",
    ),
    "filtered": TemplateSpec(
        template_id="filtered",
        category="traverse",
        description="Property-filtered traversal",
        cypher=_FILTERED,
        slots=["start_label", "filter_prop", "rel1", "end_label", "return_prop"],
        params=["filter_val"],
        example_question="서울시 고객이 주문한 상품은?",
    ),
    "common_neighbor": TemplateSpec(
        template_id="common_neighbor",
        category="traverse",
        description="Common neighbor (shared connection)",
        cypher=_COMMON_NEIGHBOR,
        slots=["start_label", "start_prop", "rel1", "mid_label", "return_prop"],
        params=["val1", "val2"],
        example_question="김민수와 이영희가 공통으로 주문한 상품은?",
    ),
    "shortest_path": TemplateSpec(
        template_id="shortest_path",
        category="traverse",
        description="Shortest path between two nodes",
        cypher=_SHORTEST_PATH,
        slots=["start_label", "start_prop", "end_label", "end_prop", "max_depth"],
        params=["val1", "val2"],
        example_question="김민수에서 노트북 카테고리까지 최단 경로는?",
    ),
    "agg_with_rel": TemplateSpec(
        template_id="agg_with_rel",
        category="aggregate",
        description="Aggregation through relationships",
        cypher=_AGG_WITH_REL,
        slots=["start_label", "rel1", "mid_label", "rel2", "end_label", "group_prop"],
        params=["limit"],
        example_question="가장 많이 팔린 카테고리 Top 3는?",
    ),
    "status_filter": TemplateSpec(
        template_id="status_filter",
        category="traverse",
        description="Status/condition filtered traversal",
        cypher=_STATUS_FILTER,
        slots=["start_label", "rel1", "end_label", "status_prop", "op", "return_prop"],
        params=["status_val"],
        example_question="배송완료된 주문의 상품은?",
    ),
    "custom_q2": TemplateSpec(
        template_id="custom_q2",
        category="aggregate",
        description="Customer's category-filtered review Top N (Q2 specific)",
        cypher=_CUSTOM_Q2,
        slots=[],
        params=["name", "limit"],
        example_question="김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?",
    ),
    "custom_q4": TemplateSpec(
        template_id="custom_q4",
        category="traverse",
        description="Common products purchased by two customers (Q4 specific)",
        cypher=_CUSTOM_Q4,
        slots=[],
        params=["name1", "name2"],
        example_question="김민수와 이영희가 공통으로 구매한 상품은?",
    ),
    "custom_q5": TemplateSpec(
        template_id="custom_q5",
        category="aggregate",
        description="Coupon used vs unused order comparison (Q5 specific)",
        cypher=_CUSTOM_Q5,
        slots=[],
        params=[],
        example_question="쿠폰 사용 주문과 미사용 주문의 평균 금액 비교",
    ),
}


# ── Public API ───────────────────────────────────────────────────

def get_template(template_id: str) -> TemplateSpec | None:
    """Look up a template by ID."""
    return REGISTRY.get(template_id)


def render_cypher(template_id: str, slots: dict[str, str]) -> str:
    """Fill label/rel slots in a template. Returns the formatted Cypher string."""
    spec = REGISTRY.get(template_id)
    if spec is None:
        raise KeyError(f"Unknown template: {template_id}")
    if not spec.slots:
        # Custom templates have no slots to fill
        return spec.cypher
    return spec.cypher.format(**slots)


def list_templates_for_prompt() -> str:
    """Build a text summary of all templates for the LLM router prompt."""
    lines = []
    for tid, spec in REGISTRY.items():
        slots_str = ", ".join(spec.slots) if spec.slots else "(none)"
        params_str = ", ".join(f"${p}" for p in spec.params) if spec.params else "(none)"
        lines.append(
            f"- {tid} [{spec.category}]: {spec.description}\n"
            f"  slots: {slots_str}\n"
            f"  params: {params_str}\n"
            f"  example: {spec.example_question}"
        )
    return "\n".join(lines)


def get_all_template_ids() -> list[str]:
    """Return all registered template IDs."""
    return list(REGISTRY.keys())
