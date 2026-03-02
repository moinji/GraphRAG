"""Graph visualization API: stats, full graph, neighbor expansion."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from neo4j import GraphDatabase

from app.config import settings
from app.models.schemas import GraphData, GraphEdge, GraphNode, GraphStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


def _get_driver():
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


# ── GET /stats ───────────────────────────────────────────────────

@router.get("/stats", response_model=GraphStats)
def graph_stats():
    """Return node/edge type counts."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            # Node counts by label
            node_rows = session.run(
                "MATCH (n) "
                "UNWIND labels(n) AS lbl "
                "RETURN lbl, count(*) AS cnt "
                "ORDER BY cnt DESC"
            )
            node_counts: dict[str, int] = {}
            total_nodes = 0
            for rec in node_rows:
                node_counts[rec["lbl"]] = rec["cnt"]
                total_nodes += rec["cnt"]

            # Edge counts by type
            edge_rows = session.run(
                "MATCH ()-[r]->() "
                "RETURN type(r) AS t, count(*) AS cnt "
                "ORDER BY cnt DESC"
            )
            edge_counts: dict[str, int] = {}
            total_edges = 0
            for rec in edge_rows:
                edge_counts[rec["t"]] = rec["cnt"]
                total_edges += rec["cnt"]

        return GraphStats(
            node_counts=node_counts,
            edge_counts=edge_counts,
            total_nodes=total_nodes,
            total_edges=total_edges,
        )
    except Exception as exc:
        logger.error("graph_stats failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}")
    finally:
        driver.close()


# ── GET /full ────────────────────────────────────────────────────

@router.get("/full", response_model=GraphData)
def graph_full(limit: int = Query(500, ge=1, le=5000)):
    """Return the full graph (up to *limit* nodes) with all connecting edges."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            # Total counts
            total_nodes = session.run(
                "MATCH (n) RETURN count(n) AS c"
            ).single()["c"]
            total_edges = session.run(
                "MATCH ()-[r]->() RETURN count(r) AS c"
            ).single()["c"]

            # Fetch nodes (limited)
            node_records = session.run(
                "MATCH (n) RETURN n, labels(n) AS lbls, elementId(n) AS eid "
                "LIMIT $limit",
                limit=limit,
            )
            nodes: list[GraphNode] = []
            node_ids_set: set[str] = set()
            eid_to_composite: dict[str, str] = {}

            for rec in node_records:
                n = rec["n"]
                lbls = rec["lbls"]
                label = lbls[0] if lbls else "Unknown"
                props = dict(n)
                node_id_val = props.get("id", rec["eid"])
                composite_id = f"{label}_{node_id_val}"
                display = props.get("name", props.get("id", str(node_id_val)))

                eid_to_composite[rec["eid"]] = composite_id
                node_ids_set.add(rec["eid"])
                nodes.append(GraphNode(
                    id=composite_id,
                    label=label,
                    properties=props,
                    display_name=str(display),
                ))

            # Fetch edges between collected nodes
            edge_records = session.run(
                "MATCH (a)-[r]->(b) "
                "WHERE elementId(a) IN $eids AND elementId(b) IN $eids "
                "RETURN elementId(a) AS src_eid, elementId(b) AS tgt_eid, "
                "       type(r) AS rtype, properties(r) AS rprops, elementId(r) AS reid",
                eids=list(node_ids_set),
            )
            edges: list[GraphEdge] = []
            for rec in edge_records:
                src = eid_to_composite.get(rec["src_eid"])
                tgt = eid_to_composite.get(rec["tgt_eid"])
                if src and tgt:
                    edges.append(GraphEdge(
                        id=rec["reid"],
                        source=src,
                        target=tgt,
                        rel_type=rec["rtype"],
                        properties=rec["rprops"] or {},
                    ))

        return GraphData(
            nodes=nodes,
            edges=edges,
            total_nodes=total_nodes,
            total_edges=total_edges,
            truncated=total_nodes > limit,
        )
    except Exception as exc:
        logger.error("graph_full failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}")
    finally:
        driver.close()


# ── GET /neighbors/{node_id} ─────────────────────────────────────

@router.get("/neighbors/{node_id}", response_model=GraphData)
def graph_neighbors(node_id: str, depth: int = Query(1, ge=1, le=3)):
    """Return neighbors of a node up to *depth* hops.

    *node_id* uses the composite format ``{Label}_{id}`` (e.g. ``Customer_1``).
    """
    parts = node_id.split("_", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="node_id must be {Label}_{id}")
    label, id_val = parts

    # Try to parse id_val as int if possible
    try:
        id_val_parsed: int | str = int(id_val)
    except ValueError:
        id_val_parsed = id_val

    driver = _get_driver()
    try:
        with driver.session() as session:
            # Verify anchor node exists
            anchor = session.run(
                f"MATCH (n:{label} {{id: $id_val}}) RETURN n, elementId(n) AS eid",
                id_val=id_val_parsed,
            ).single()
            if not anchor:
                raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

            # Fetch neighborhood
            records = session.run(
                f"MATCH path = (start:{label} {{id: $id_val}})-[*1..{depth}]-(end) "
                "UNWIND nodes(path) AS n "
                "WITH DISTINCT n "
                "RETURN n, labels(n) AS lbls, elementId(n) AS eid",
                id_val=id_val_parsed,
            )

            nodes: list[GraphNode] = []
            node_eids: set[str] = set()
            eid_to_composite: dict[str, str] = {}

            for rec in records:
                n = rec["n"]
                lbls = rec["lbls"]
                nlabel = lbls[0] if lbls else "Unknown"
                props = dict(n)
                nid = props.get("id", rec["eid"])
                composite = f"{nlabel}_{nid}"
                display = props.get("name", props.get("id", str(nid)))

                if rec["eid"] not in node_eids:
                    node_eids.add(rec["eid"])
                    eid_to_composite[rec["eid"]] = composite
                    nodes.append(GraphNode(
                        id=composite,
                        label=nlabel,
                        properties=props,
                        display_name=str(display),
                    ))

            # Edges between neighborhood nodes
            edge_records = session.run(
                "MATCH (a)-[r]->(b) "
                "WHERE elementId(a) IN $eids AND elementId(b) IN $eids "
                "RETURN elementId(a) AS src_eid, elementId(b) AS tgt_eid, "
                "       type(r) AS rtype, properties(r) AS rprops, elementId(r) AS reid",
                eids=list(node_eids),
            )
            edges: list[GraphEdge] = []
            for rec in edge_records:
                src = eid_to_composite.get(rec["src_eid"])
                tgt = eid_to_composite.get(rec["tgt_eid"])
                if src and tgt:
                    edges.append(GraphEdge(
                        id=rec["reid"],
                        source=src,
                        target=tgt,
                        rel_type=rec["rtype"],
                        properties=rec["rprops"] or {},
                    ))

        return GraphData(
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            total_edges=len(edges),
            truncated=False,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("graph_neighbors failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}")
    finally:
        driver.close()
