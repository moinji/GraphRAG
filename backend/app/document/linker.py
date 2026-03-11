"""Document-to-KG linker: create MENTIONS relationships in Neo4j.

Links document chunks to KG entities via NER results.
Creates Document and Chunk nodes in Neo4j with HAS_CHUNK and MENTIONS relationships.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.db.neo4j_client import get_driver
from app.document.ner import ExtractedEntity, extract_entities
from app.tenant import prefixed_label

logger = logging.getLogger(__name__)


@dataclass
class LinkingResult:
    """Result of linking a document to KG."""
    document_id: int
    document_node_created: bool = False
    chunk_nodes_created: int = 0
    mentions_created: int = 0
    entities_found: int = 0
    errors: list[str] = field(default_factory=list)


def link_document_to_kg(
    document_id: int,
    chunks: list[dict],
    tenant_id: str | None = None,
    confidence_threshold: float = 0.5,
) -> LinkingResult:
    """Link document chunks to KG entities.

    Steps:
        1. Create Document node in Neo4j
        2. For each chunk: create Chunk node + HAS_CHUNK relationship
        3. Run NER on each chunk text
        4. For matched entities: create MENTIONS relationships

    Args:
        document_id: PG document ID
        chunks: list of {text, chunk_index, metadata} dicts
        tenant_id: for multi-tenant isolation
        confidence_threshold: minimum NER confidence for linking
    """
    result = LinkingResult(document_id=document_id)

    if not chunks:
        return result

    try:
        driver = get_driver()
    except Exception as e:
        result.errors.append(f"Neo4j connection failed: {e}")
        return result

    # Get document metadata from PG
    doc_meta = _get_document_meta(document_id, tenant_id)
    if doc_meta is None:
        result.errors.append(f"Document {document_id} not found in PG")
        return result

    doc_label = prefixed_label(tenant_id, "Document")
    chunk_label = prefixed_label(tenant_id, "Chunk")

    try:
        with driver.session() as session:
            # Step 1: Create Document node
            session.run(
                f"MERGE (d:{doc_label} {{doc_id: $doc_id}}) "
                f"SET d.filename = $filename, d.file_type = $file_type, "
                f"d.tenant_id = $tenant_id",
                doc_id=document_id,
                filename=doc_meta.get("filename", ""),
                file_type=doc_meta.get("file_type", ""),
                tenant_id=tenant_id or "_default_",
            )
            result.document_node_created = True

            # Step 2-4: Process each chunk
            all_entities: list[ExtractedEntity] = []

            for chunk in chunks:
                chunk_text = chunk.get("text", "")
                chunk_index = chunk.get("chunk_index", 0)
                metadata = chunk.get("metadata", {})

                # Create Chunk node + HAS_CHUNK
                session.run(
                    f"MERGE (c:{chunk_label} {{doc_id: $doc_id, chunk_index: $idx}}) "
                    f"SET c.text_preview = $preview, c.page_num = $page_num "
                    f"WITH c "
                    f"MATCH (d:{doc_label} {{doc_id: $doc_id}}) "
                    f"MERGE (d)-[:HAS_CHUNK]->(c)",
                    doc_id=document_id,
                    idx=chunk_index,
                    preview=chunk_text[:200],
                    page_num=metadata.get("page_num", 0),
                )
                result.chunk_nodes_created += 1

                # NER on chunk text
                entities = extract_entities(chunk_text, tenant_id=tenant_id)
                chunk_entities = [
                    e for e in entities if e.confidence >= confidence_threshold
                ]
                all_entities.extend(chunk_entities)

                # Create MENTIONS relationships
                for entity in chunk_entities:
                    entity_label = prefixed_label(tenant_id, entity.label)
                    try:
                        res = session.run(
                            f"MATCH (c:{chunk_label} {{doc_id: $doc_id, chunk_index: $idx}}) "
                            f"MATCH (e:{entity_label} {{name: $name}}) "
                            f"MERGE (c)-[r:MENTIONS]->(e) "
                            f"SET r.confidence = $conf, r.source = $source "
                            f"RETURN count(r) AS cnt",
                            doc_id=document_id,
                            idx=chunk_index,
                            name=entity.name,
                            conf=entity.confidence,
                            source=entity.source,
                        )
                        record = res.single()
                        if record and record["cnt"] > 0:
                            result.mentions_created += 1
                    except Exception as e:
                        logger.debug(
                            "Failed to create MENTIONS for %s->%s: %s",
                            entity.name, entity.label, e,
                        )

            result.entities_found = len(set((e.name, e.label) for e in all_entities))

    except Exception as e:
        result.errors.append(f"Neo4j linking failed: {e}")
        logger.error("Document-KG linking failed: %s", e, exc_info=True)

    return result


def _get_document_meta(document_id: int, tenant_id: str | None) -> dict | None:
    """Get document metadata from PG."""
    try:
        from app.db.vector_store import get_document
        return get_document(document_id, tenant_id=tenant_id)
    except Exception:
        return None


def unlink_document_from_kg(
    document_id: int,
    tenant_id: str | None = None,
) -> int:
    """Remove Document + Chunk nodes and their relationships from Neo4j.

    Returns count of nodes deleted.
    """
    doc_label = prefixed_label(tenant_id, "Document")
    chunk_label = prefixed_label(tenant_id, "Chunk")

    try:
        driver = get_driver()
        with driver.session() as session:
            # Delete chunks and their relationships
            result = session.run(
                f"MATCH (d:{doc_label} {{doc_id: $doc_id}}) "
                f"OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:{chunk_label}) "
                f"DETACH DELETE d, c "
                f"RETURN count(d) + count(c) AS deleted",
                doc_id=document_id,
            )
            record = result.single()
            return record["deleted"] if record else 0
    except Exception as e:
        logger.warning("Failed to unlink document %d from KG: %s", document_id, e)
        return 0
