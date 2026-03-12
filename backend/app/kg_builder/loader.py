"""Neo4j graph loader: OntologySpec + data → Neo4j MERGE.

Pipeline: clean → constraints → nodes (9 types) → relationships (12 types).
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict

from neo4j import GraphDatabase

from app.config import settings
from app.db.neo4j_client import get_driver
from app.models.schemas import NodeType, OntologySpec, RelationshipType

logger = logging.getLogger(__name__)


def _find_key_prop(nt: NodeType) -> str:
    """Return the key property name for a node type (is_key=True).

    Fallback order: first property (usually PK) → 'id'.
    """
    for p in nt.properties:
        if p.is_key:
            return p.name
    # No is_key flag set — use the first property (typically the PK column)
    if nt.properties:
        return nt.properties[0].name
    return "id"


def _wait_for_neo4j(uri: str, user: str, password: str, timeout: int | None = None):
    """Wait until Neo4j is reachable (retry every 2s)."""
    if timeout is None:
        timeout = settings.neo4j_connect_timeout
    deadline = time.time() + timeout
    driver = GraphDatabase.driver(uri, auth=(user, password))
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            driver.verify_connectivity()
            driver.close()
            return
        except Exception as e:
            last_err = e
            time.sleep(2)
    driver.close()
    msg = f"Neo4j not reachable at {uri} after {timeout}s"
    if last_err:
        msg += f" (last error: {last_err})"
    if uri.startswith("neo4j+s://"):
        msg += ". Hint: AuraDB instance may be paused — check console.neo4j.io"
    raise ConnectionError(msg)


def _clean_db(tx):
    tx.run("MATCH (n) DETACH DELETE n")


def _create_constraint(tx, label: str, key_prop: str):
    tx.run(
        f"CREATE CONSTRAINT IF NOT EXISTS "
        f"FOR (n:{label}) REQUIRE n.`{key_prop}` IS UNIQUE"
    )


def _create_index(tx, label: str, prop: str):
    """Create a property index for faster lookups (idempotent)."""
    tx.run(
        f"CREATE INDEX IF NOT EXISTS "
        f"FOR (n:{label}) ON (n.`{prop}`)"
    )


# Maximum rows per UNWIND batch to prevent Neo4j transaction OOM
_BATCH_SIZE = 5000


def _load_nodes(tx, label: str, key_prop: str, props: list[str], rows: list[dict]):
    """UNWIND + MERGE batch for one node type."""
    set_parts = ", ".join(f"n.`{p}` = row.`{p}`" for p in props if p != key_prop)
    query = (
        f"UNWIND $rows AS row "
        f"MERGE (n:{label} {{`{key_prop}`: row.`{key_prop}`}}) "
    )
    if set_parts:
        query += f"SET {set_parts}"
    tx.run(query, rows=rows)


def _load_relationships(
    tx,
    rel: RelationshipType,
    rows: list[dict],
    src_key_prop: str,
    tgt_key_prop: str,
):
    """UNWIND + MERGE batch for one relationship type."""
    prop_set = ""
    if rel.properties:
        parts = ", ".join(
            f"r.`{p.name}` = row.`{p.source_column}`" for p in rel.properties
        )
        prop_set = f"SET {parts}"

    query = (
        f"UNWIND $rows AS row "
        f"MATCH (src:{rel.source_node} {{`{src_key_prop}`: row.__src}}) "
        f"MATCH (tgt:{rel.target_node} {{`{tgt_key_prop}`: row.__tgt}}) "
        f"MERGE (src)-[r:{rel.name}]->(tgt) "
        f"{prop_set}"
    )
    tx.run(query, rows=rows)


def _build_name_prompt(label: str, sample: dict) -> str:
    return (
        "You are naming nodes in a knowledge graph.\n\n"
        f"Node type: {label}\n"
        f"Available properties and sample values:\n{json.dumps(sample, ensure_ascii=False, default=str)}\n\n"
        "Create a short, human-readable display name template using {property_name} placeholders.\n"
        "The name should help users identify each node at a glance in a graph visualization.\n\n"
        "Rules:\n"
        "- Use ONLY the available property names as placeholders.\n"
        "- Keep it concise — the rendered result should be under 30 characters.\n"
        "- If there is a 'name', 'title', or 'code' property, prefer that alone.\n"
        "- For entities without a natural name, combine the label with 1-2 key identifying properties.\n"
        "- Return ONLY the template string, nothing else. No quotes, no explanation.\n\n"
        "Examples:\n"
        '- Node "Order" with id, status, total_amount → 주문 #{id} ({status})\n'
        '- Node "Address" with id, city, district, street → {city} {district}\n'
        '- Node "Payment" with id, method, amount → 결제 #{id} ({method})\n'
        '- Node "Student" with id, 이름, 학번 → {이름} ({학번})\n'
    )


def _ask_llm_name_template(label: str, prop_names: list[str], sample_row: dict) -> str | None:
    """Ask LLM to generate a display name template for a node type.

    Uses unified provider (OpenAI → Anthropic fallback). Returns a Python
    format string like ``"{city} {district}"`` or *None* on failure.
    One call per node type (not per row).
    """
    from app.llm.provider import call_llm

    sample = {k: sample_row.get(k) for k in prop_names if k in sample_row}
    prompt = _build_name_prompt(label, sample)

    result = call_llm(
        messages=[{"role": "user", "content": prompt}],
        caller="name_template",
        max_tokens=100,
    )
    template = result.text.strip("\"'`") if result else None
    if not template:
        return None

    # Validate: try rendering with the sample row
    try:
        safe = defaultdict(str, {k: str(v) if v is not None else "" for k, v in sample.items()})
        template.format_map(safe)
        logger.info("LLM name template for %s: %s", label, template)
        return template
    except Exception:
        logger.warning("LLM template validation failed for %s: %s", label, template)
        return None


# ── Hardcoded display name templates (zero LLM calls) ─────────

_KNOWN_NAME_TEMPLATES: dict[str, str] = {
    "Order": "주문 #{id} ({status})",
    "Payment": "결제 #{id} ({method})",
    "Review": "리뷰 #{id} ({rating}점)",
    "Address": "{city} {district}",
    "Shipping": "배송 #{id} ({status})",
    "Coupon": "{code} ({discount_pct}%)",
}

# In-memory cache: survives across builds within the same process
_name_template_cache: dict[str, str] = {}


def _infer_name_template(label: str, prop_names: list[str]) -> str | None:
    """Rule-based display name inference — no LLM call, instant return."""
    for preferred in ("name", "title", "code"):
        if preferred in prop_names:
            return f"{{{preferred}}}"
    if "id" in prop_names:
        for extra in ("status", "type", "method", "category"):
            if extra in prop_names:
                return label + " #{id} ({" + extra + "})"
        return label + " #{id}"
    return None


def _ensure_name(label: str, rows: list[dict], prop_names: list[str]) -> list[dict]:
    """Add a human-readable ``name`` to rows that lack one.

    Waterfall: hardcoded → cache → rule inference → LLM (last resort) → fallback.
    """
    if not rows:
        return rows
    if "name" in rows[0] and rows[0]["name"] is not None:
        return rows

    # 1. Hardcoded templates (instant)
    template = _KNOWN_NAME_TEMPLATES.get(label)

    # 2. Cache from previous build
    if template is None:
        template = _name_template_cache.get(label)

    # 3. Rule-based inference (instant)
    if template is None:
        template = _infer_name_template(label, prop_names)

    # 4. LLM as last resort (only for truly unknown node types)
    if template is None:
        template = _ask_llm_name_template(label, prop_names, rows[0])
        if template:
            _name_template_cache[label] = template

    # 5. Fallback
    if template is None:
        template = label + " #{id}"

    enriched: list[dict] = []
    for row in rows:
        r = dict(row)
        try:
            safe = defaultdict(str, {k: str(v) if v is not None else "" for k, v in r.items()})
            r["name"] = template.format_map(safe)
        except Exception:
            r["name"] = f"{label} #{r.get('id', '?')}"
        enriched.append(r)
    return enriched


def load_from_mapping(
    mapping_config: "DomainMappingConfig",
    data: dict[str, list[dict]],
    uri: str,
    user: str,
    password: str,
    tenant_id: str | None = None,
) -> dict[str, int]:
    """Load to Neo4j using a YAML DomainMappingConfig.

    Converts the mapping config to OntologySpec and delegates to load_to_neo4j.
    Phase 1: conversion + delegation. Phase 2: direct Cypher from YAML.
    """
    from app.mapping.converter import mapping_to_ontology

    ontology = mapping_to_ontology(mapping_config)
    return load_to_neo4j(ontology, data, uri, user, password, tenant_id)


def load_to_neo4j(
    ontology: OntologySpec,
    data: dict[str, list[dict]],
    uri: str,
    user: str,
    password: str,
    tenant_id: str | None = None,
) -> dict[str, int]:
    """Full load pipeline. Returns counts dict."""
    from app.tenant import prefixed_label, tenant_label_prefix

    _wait_for_neo4j(uri, user, password)
    driver = get_driver()
    stats: dict[str, int] = {"nodes": 0, "relationships": 0}
    prefix = tenant_label_prefix(tenant_id)

    with driver.session() as session:
        # ── 1. Clean (tenant-scoped) ──────────────────────────────
        if prefix:
            # Delete only nodes with this tenant's prefixed labels
            all_labels = [prefixed_label(tenant_id, nt.name) for nt in ontology.node_types]
            for lbl in all_labels:
                session.run(f"MATCH (n:`{lbl}`) DETACH DELETE n")
        else:
            session.execute_write(_clean_db)

        # ── 2. Constraints + Indexes ────────────────────────────────
        # Index all non-key properties for fast local search & template queries
        for nt in ontology.node_types:
            key_prop = _find_key_prop(nt)
            lbl = prefixed_label(tenant_id, nt.name)
            session.execute_write(_create_constraint, lbl, key_prop)
            for prop in nt.properties:
                if prop.name != key_prop:
                    session.execute_write(_create_index, lbl, prop.name)

        # ── 3+4. Nodes + Relationships in a single transaction ────
        # Prepare all data before opening the transaction
        node_batches: list[tuple[str, str, list[str], list[dict]]] = []
        for nt in ontology.node_types:
            key_prop = _find_key_prop(nt)
            lbl = prefixed_label(tenant_id, nt.name)
            rows = data.get(nt.source_table, [])
            prop_names = [p.name for p in nt.properties]
            rows = _ensure_name(nt.name, rows, prop_names)
            if "name" not in prop_names:
                prop_names.append("name")
            for i in range(0, len(rows), _BATCH_SIZE):
                node_batches.append((lbl, key_prop, prop_names, rows[i : i + _BATCH_SIZE]))
            stats["nodes"] += len(rows)

        node_key_map = {nt.name: _find_key_prop(nt) for nt in ontology.node_types}
        rel_batches: list[tuple[RelationshipType, list[dict], str, str]] = []
        for rel in ontology.relationship_types:
            table_rows = data.get(rel.data_table, [])
            src_key = node_key_map.get(rel.source_node, "id")
            tgt_key = node_key_map.get(rel.target_node, "id")
            loader_rows: list[dict] = []
            for row in table_rows:
                src_val = row.get(rel.source_key_column)
                tgt_val = row.get(rel.target_key_column)
                if src_val is None or tgt_val is None:
                    continue
                lr = {"__src": src_val, "__tgt": tgt_val}
                for p in rel.properties:
                    lr[p.source_column] = row.get(p.source_column)
                loader_rows.append(lr)

            prefixed_rel = RelationshipType(
                name=rel.name,
                source_node=prefixed_label(tenant_id, rel.source_node),
                target_node=prefixed_label(tenant_id, rel.target_node),
                data_table=rel.data_table,
                source_key_column=rel.source_key_column,
                target_key_column=rel.target_key_column,
                properties=rel.properties,
                derivation=rel.derivation,
            )
            for i in range(0, len(loader_rows), _BATCH_SIZE):
                rel_batches.append((prefixed_rel, loader_rows[i : i + _BATCH_SIZE], src_key, tgt_key))
            stats["relationships"] += len(loader_rows)

        # Execute all node + relationship loads in one transaction (atomic)
        with session.begin_transaction() as tx:
            for lbl, key_prop, prop_names, batch in node_batches:
                _load_nodes(tx, lbl, key_prop, prop_names, batch)
            for prefixed_rel, batch, src_key, tgt_key in rel_batches:
                _load_relationships(tx, prefixed_rel, batch, src_key, tgt_key)
            tx.commit()

    # ── 5. Verify counts (tenant-scoped) ──────────────────────────
    with driver.session() as session:
        if prefix:
            all_labels = [prefixed_label(tenant_id, nt.name) for nt in ontology.node_types]
            total = 0
            for lbl in all_labels:
                total += session.run(f"MATCH (n:`{lbl}`) RETURN count(n) AS c").single()["c"]
            stats["neo4j_nodes"] = total
        else:
            stats["neo4j_nodes"] = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        stats["neo4j_relationships"] = session.run(
            "MATCH ()-[r]->() RETURN count(r) AS c"
        ).single()["c"]

    return stats
