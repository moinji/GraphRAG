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


def _try_openai(prompt: str) -> str | None:
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model=settings.openai_router_model,
            max_tokens=100,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip().strip("\"'`")
    except Exception as exc:
        logger.warning("OpenAI name template failed: %s", exc)
        return None


def _try_anthropic(prompt: str) -> str | None:
    if not settings.anthropic_api_key:
        return None
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=100,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip().strip("\"'`")
    except Exception as exc:
        logger.warning("Anthropic name template failed: %s", exc)
        return None


def _ask_llm_name_template(label: str, prop_names: list[str], sample_row: dict) -> str | None:
    """Ask LLM to generate a display name template for a node type.

    Tries OpenAI first, falls back to Anthropic. Returns a Python format
    string like ``"{city} {district}"`` or *None* on failure.
    One call per node type (not per row).
    """
    sample = {k: sample_row.get(k) for k in prop_names if k in sample_row}
    prompt = _build_name_prompt(label, sample)

    template = _try_openai(prompt) or _try_anthropic(prompt)
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


def _ensure_name(label: str, rows: list[dict], prop_names: list[str]) -> list[dict]:
    """Add a human-readable ``name`` to rows that lack one.

    Calls the LLM once to decide the best display format for the node type,
    then applies the template to every row.  Falls back to ``{Label} #{id}``
    if the LLM is unavailable or fails.
    """
    if not rows:
        return rows
    if "name" in rows[0] and rows[0]["name"] is not None:
        return rows

    template = _ask_llm_name_template(label, prop_names, rows[0])
    if not template:
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


def load_to_neo4j(
    ontology: OntologySpec,
    data: dict[str, list[dict]],
    uri: str,
    user: str,
    password: str,
) -> dict[str, int]:
    """Full load pipeline. Returns counts dict."""
    _wait_for_neo4j(uri, user, password)
    driver = get_driver()
    stats: dict[str, int] = {"nodes": 0, "relationships": 0}

    with driver.session() as session:
        # ── 1. Clean ───────────────────────────────────────────────
        session.execute_write(_clean_db)

        # ── 2. Constraints ─────────────────────────────────────────
        for nt in ontology.node_types:
            key_prop = _find_key_prop(nt)
            session.execute_write(_create_constraint, nt.name, key_prop)

        # ── 3. Nodes ──────────────────────────────────────────────
        for nt in ontology.node_types:
            key_prop = _find_key_prop(nt)
            rows = data.get(nt.source_table, [])
            prop_names = [p.name for p in nt.properties]
            rows = _ensure_name(nt.name, rows, prop_names)
            if "name" not in prop_names:
                prop_names.append("name")
            session.execute_write(_load_nodes, nt.name, key_prop, prop_names, rows)
            stats["nodes"] += len(rows)

        # ── 4. Relationships ──────────────────────────────────────
        # Build lookup: node_name → key property
        node_key_map = {nt.name: _find_key_prop(nt) for nt in ontology.node_types}

        for rel in ontology.relationship_types:
            table_rows = data.get(rel.data_table, [])
            src_key = node_key_map.get(rel.source_node, "id")
            tgt_key = node_key_map.get(rel.target_node, "id")
            # Build loader rows with __src / __tgt keys
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

            if loader_rows:
                session.execute_write(_load_relationships, rel, loader_rows, src_key, tgt_key)
            stats["relationships"] += len(loader_rows)

    # ── 5. Verify counts ──────────────────────────────────────────
    with driver.session() as session:
        node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        stats["neo4j_nodes"] = node_count
        stats["neo4j_relationships"] = rel_count

    return stats
