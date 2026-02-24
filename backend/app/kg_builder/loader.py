"""Neo4j graph loader: OntologySpec + data → Neo4j MERGE.

Pipeline: clean → constraints → nodes (9 types) → relationships (12 types).
"""

from __future__ import annotations

import time

from neo4j import GraphDatabase

from app.models.schemas import OntologySpec, RelationshipType


def _wait_for_neo4j(uri: str, user: str, password: str, timeout: int = 30):
    """Wait until Neo4j is reachable (retry every 2s)."""
    deadline = time.time() + timeout
    driver = GraphDatabase.driver(uri, auth=(user, password))
    while time.time() < deadline:
        try:
            driver.verify_connectivity()
            driver.close()
            return
        except Exception:
            time.sleep(2)
    driver.close()
    raise ConnectionError(f"Neo4j not reachable at {uri} after {timeout}s")


def _clean_db(tx):
    tx.run("MATCH (n) DETACH DELETE n")


def _create_constraint(tx, label: str):
    tx.run(
        f"CREATE CONSTRAINT IF NOT EXISTS "
        f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
    )


def _load_nodes(tx, label: str, props: list[str], rows: list[dict]):
    """UNWIND + MERGE batch for one node type."""
    set_parts = ", ".join(f"n.{p} = row.{p}" for p in props if p != "id")
    query = (
        f"UNWIND $rows AS row "
        f"MERGE (n:{label} {{id: row.id}}) "
    )
    if set_parts:
        query += f"SET {set_parts}"
    tx.run(query, rows=rows)


def _load_relationships(
    tx,
    rel: RelationshipType,
    rows: list[dict],
):
    """UNWIND + MERGE batch for one relationship type."""
    prop_set = ""
    if rel.properties:
        parts = ", ".join(
            f"r.{p.name} = row.{p.source_column}" for p in rel.properties
        )
        prop_set = f"SET {parts}"

    query = (
        f"UNWIND $rows AS row "
        f"MATCH (src:{rel.source_node} {{id: row.__src}}) "
        f"MATCH (tgt:{rel.target_node} {{id: row.__tgt}}) "
        f"MERGE (src)-[r:{rel.name}]->(tgt) "
        f"{prop_set}"
    )
    tx.run(query, rows=rows)


def load_to_neo4j(
    ontology: OntologySpec,
    data: dict[str, list[dict]],
    uri: str,
    user: str,
    password: str,
) -> dict[str, int]:
    """Full load pipeline. Returns counts dict."""
    _wait_for_neo4j(uri, user, password)
    driver = GraphDatabase.driver(uri, auth=(user, password))
    stats: dict[str, int] = {"nodes": 0, "relationships": 0}

    with driver.session() as session:
        # ── 1. Clean ───────────────────────────────────────────────
        session.execute_write(_clean_db)

        # ── 2. Constraints ─────────────────────────────────────────
        for nt in ontology.node_types:
            session.execute_write(_create_constraint, nt.name)

        # ── 3. Nodes ──────────────────────────────────────────────
        for nt in ontology.node_types:
            rows = data.get(nt.source_table, [])
            prop_names = [p.name for p in nt.properties]
            session.execute_write(_load_nodes, nt.name, prop_names, rows)
            stats["nodes"] += len(rows)

        # ── 4. Relationships ──────────────────────────────────────
        for rel in ontology.relationship_types:
            table_rows = data.get(rel.data_table, [])
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
                session.execute_write(_load_relationships, rel, loader_rows)
            stats["relationships"] += len(loader_rows)

    # ── 5. Verify counts ──────────────────────────────────────────
    with driver.session() as session:
        node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        stats["neo4j_nodes"] = node_count
        stats["neo4j_relationships"] = rel_count

    driver.close()
    return stats
