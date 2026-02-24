"""Ontology evaluation: compare generated ontology against golden data."""

from __future__ import annotations

from app.models.schemas import EvalMetrics, OntologySpec


def evaluate(
    generated: OntologySpec,
    golden_nodes: set[str],
    golden_rels: list[tuple[str, str, str, str]],
) -> EvalMetrics:
    """Compare generated ontology against golden node/relationship sets.

    Args:
        generated: The generated OntologySpec to evaluate.
        golden_nodes: Set of expected node type names.
        golden_rels: List of (name, source, target, derivation) tuples.

    Returns:
        EvalMetrics with coverage and accuracy scores.
    """
    gen_node_names = {n.name for n in generated.node_types}
    gen_rel_tuples = {
        (r.name, r.source_node, r.target_node)
        for r in generated.relationship_types
    }
    golden_rel_tuples = {(name, src, tgt) for name, src, tgt, _ in golden_rels}

    # Missing items (in golden but not generated)
    missing_nodes = golden_nodes - gen_node_names
    missing_rels = golden_rel_tuples - gen_rel_tuples
    total_golden = len(golden_nodes) + len(golden_rels)
    missing_count = len(missing_nodes) + len(missing_rels)

    critical_error_rate = missing_count / total_golden if total_golden > 0 else 0.0

    # FK relationship coverage
    matched_rels = golden_rel_tuples & gen_rel_tuples
    fk_relationship_coverage = (
        len(matched_rels) / len(golden_rels) if golden_rels else 1.0
    )

    # Direction accuracy — for matched relationships, check source/target
    # Build lookup from generated relationships
    gen_rel_map = {
        r.name: (r.source_node, r.target_node)
        for r in generated.relationship_types
    }
    direction_correct = 0
    direction_total = 0
    for name, src, tgt, _ in golden_rels:
        if name in gen_rel_map:
            direction_total += 1
            gen_src, gen_tgt = gen_rel_map[name]
            if gen_src == src and gen_tgt == tgt:
                direction_correct += 1

    direction_accuracy = (
        direction_correct / direction_total if direction_total > 0 else 1.0
    )

    # LLM adoption rate
    llm_count = sum(
        1 for r in generated.relationship_types
        if r.derivation == "llm_suggested"
    )
    total_rels = len(generated.relationship_types)
    llm_adoption_rate = llm_count / total_rels if total_rels > 0 and llm_count > 0 else None

    return EvalMetrics(
        critical_error_rate=round(critical_error_rate, 4),
        fk_relationship_coverage=round(fk_relationship_coverage, 4),
        direction_accuracy=round(direction_accuracy, 4),
        llm_adoption_rate=round(llm_adoption_rate, 4) if llm_adoption_rate is not None else None,
        node_count_generated=len(gen_node_names),
        node_count_golden=len(golden_nodes),
        relationship_count_generated=len(generated.relationship_types),
        relationship_count_golden=len(golden_rels),
    )
