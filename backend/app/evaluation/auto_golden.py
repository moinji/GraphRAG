"""Auto-generate golden data from an OntologySpec for self-evaluation.

Used for non-ecommerce domains where no hand-curated golden data exists.
The generated golden data represents the ontology's own assertions,
enabling structural validation (node/rel counts, consistency checks).
"""

from __future__ import annotations

from app.models.schemas import OntologySpec


def generate_golden_from_ontology(
    ontology: OntologySpec,
) -> tuple[set[str], list[tuple[str, str, str, str]]]:
    """Extract golden node names and relationship specs from an OntologySpec.

    Returns:
        (golden_nodes, golden_rels) matching the evaluator's expected format.
    """
    golden_nodes = {nt.name for nt in ontology.node_types}

    golden_rels = [
        (rt.name, rt.source_node, rt.target_node, rt.derivation)
        for rt in ontology.relationship_types
    ]

    return golden_nodes, golden_rels


def is_ecommerce_domain(ontology: OntologySpec) -> bool:
    """Check if the ontology matches the known e-commerce domain.

    Returns True if >= 6 of the 9 e-commerce node types are present.
    """
    ecommerce_nodes = {
        "Address", "Category", "Supplier", "Coupon",
        "Customer", "Product", "Order", "Payment", "Review",
    }
    gen_nodes = {nt.name for nt in ontology.node_types}
    overlap = gen_nodes & ecommerce_nodes
    return len(overlap) >= 6
