"""Graph visualization API: stats, full graph, neighbor expansion."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.db.neo4j_client import get_driver
from app.models.schemas import GraphData, GraphEdge, GraphNode, GraphResetResponse, GraphStats

logger = logging.getLogger(__name__)

def _pick_display_name(props: dict, label: str, fallback_id: object) -> str:
    """Choose the best human-readable display name for a node.

    1. Generic candidates: name, code, title.
    2. Label-specific rules for known types.
    3. Fallback: ``{Label} #{id}``.
    """
    for key in ("name", "code", "title"):
        val = props.get(key)
        if val is not None and str(val).strip():
            return str(val)

    node_id = props.get("id", fallback_id)

    if label == "JournalEntry":
        entry_no = props.get("entry_number", "")
        desc = props.get("description", "")
        if entry_no and desc:
            short = desc[:20] + ("…" if len(str(desc)) > 20 else "")
            return f"{entry_no}: {short}"
        if entry_no:
            return str(entry_no)
        if desc:
            return str(desc)[:30]
    elif label == "JournalLine":
        desc = props.get("description", "")
        if desc:
            return str(desc)[:30] + ("…" if len(str(desc)) > 30 else "")
    elif label == "Invoice":
        inv_no = props.get("invoice_number", "")
        status = props.get("status", "")
        if inv_no:
            return f"{inv_no} ({status})" if status else str(inv_no)
    elif label == "FiscalPeriod":
        year = props.get("year", "")
        month = props.get("month", "")
        quarter = props.get("quarter", "")
        if year and month:
            return f"{year}-{str(month).zfill(2)}" + (f" (Q{quarter})" if quarter else "")
    elif label == "Budget":
        amount = props.get("budget_amount")
        if amount is not None:
            return f"예산 #{node_id} ({amount:,.0f})"
    elif label == "Payment":
        method = props.get("method", "")
        if method:
            return f"결제 #{node_id} ({method})"

    return f"{label} #{node_id}"

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


# ── GET /stats ───────────────────────────────────────────────────

@router.get("/stats", response_model=GraphStats)
def graph_stats() -> GraphStats:
    """Return node/edge type counts."""
    driver = get_driver()
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


# ── DELETE /reset ────────────────────────────────────────────────

@router.delete("/reset", response_model=GraphResetResponse)
def graph_reset() -> GraphResetResponse:
    """Delete all nodes and edges from Neo4j."""
    driver = get_driver()
    try:
        with driver.session() as session:
            counts = session.run(
                "MATCH (n) "
                "WITH count(n) AS node_cnt "
                "OPTIONAL MATCH ()-[r]->() "
                "WITH node_cnt, count(r) AS edge_cnt "
                "RETURN node_cnt, edge_cnt"
            ).single()
            deleted_nodes = counts["node_cnt"]
            deleted_edges = counts["edge_cnt"]

            session.run("MATCH (n) DETACH DELETE n")

        logger.info("Graph reset: %d nodes, %d edges deleted", deleted_nodes, deleted_edges)
        return GraphResetResponse(
            deleted_nodes=deleted_nodes,
            deleted_edges=deleted_edges,
        )
    except Exception as exc:
        logger.error("graph_reset failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}")


# ── GET /full ────────────────────────────────────────────────────

@router.get("/full", response_model=GraphData)
def graph_full(limit: int = Query(500, ge=1, le=5000)) -> GraphData:
    """Return the full graph (up to *limit* nodes) with all connecting edges."""
    driver = get_driver()
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

                eid_to_composite[rec["eid"]] = composite_id
                node_ids_set.add(rec["eid"])
                nodes.append(GraphNode(
                    id=composite_id,
                    label=label,
                    properties=props,
                    display_name=_pick_display_name(props, label, node_id_val),
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


# ── GET /neighbors/{node_id} ─────────────────────────────────────

@router.get("/neighbors/{node_id}", response_model=GraphData)
def graph_neighbors(node_id: str, depth: int = Query(1, ge=1, le=3)) -> GraphData:
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

    driver = get_driver()
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

                if rec["eid"] not in node_eids:
                    node_eids.add(rec["eid"])
                    eid_to_composite[rec["eid"]] = composite
                    nodes.append(GraphNode(
                        id=composite,
                        label=nlabel,
                        properties=props,
                        display_name=_pick_display_name(props, nlabel, nid),
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
