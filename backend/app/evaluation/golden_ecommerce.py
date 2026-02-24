"""Golden data for e-commerce ontology evaluation.

9 node types + 12 relationship types matching the FK rule engine output
for the demo_ecommerce.sql DDL.
"""

from __future__ import annotations

# ── Golden node names (9) ──────────────────────────────────────────

GOLDEN_NODE_NAMES: set[str] = {
    "Address",
    "Category",
    "Supplier",
    "Coupon",
    "Customer",
    "Product",
    "Order",
    "Payment",
    "Review",
}

# ── Golden relationship specs (12) ─────────────────────────────────
# Each tuple: (name, source_node, target_node, derivation)

GOLDEN_RELATIONSHIP_SPECS: list[tuple[str, str, str, str]] = [
    # 9 direct FK relationships
    ("LIVES_AT",    "Customer", "Address",  "fk_direct"),
    ("BELONGS_TO",  "Product",  "Category", "fk_direct"),
    ("SUPPLIED_BY", "Product",  "Supplier", "fk_direct"),
    ("USED_COUPON", "Order",    "Coupon",   "fk_direct"),
    ("REVIEWS",     "Review",   "Product",  "fk_direct"),
    ("PLACED",      "Customer", "Order",    "fk_direct"),
    ("PAID_BY",     "Order",    "Payment",  "fk_direct"),
    ("WROTE",       "Customer", "Review",   "fk_direct"),
    ("PARENT_OF",   "Category", "Category", "fk_direct"),
    # 3 join-table relationships
    ("CONTAINS",    "Order",    "Product",  "fk_join_table"),
    ("WISHLISTED",  "Customer", "Product",  "fk_join_table"),
    ("SHIPPED_TO",  "Order",    "Address",  "fk_join_table"),
]
