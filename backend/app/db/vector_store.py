"""pgvector-based vector store for document chunks.

Uses the existing PostgreSQL connection pool from pg_client.
Tables: documents, chunks (with vector(1536) embedding column).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.tenant import tenant_db_id

logger = logging.getLogger(__name__)

# ── Table creation SQL ────────────────────────────────────────────────

_CREATE_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector;"

_CREATE_DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    tenant_id   VARCHAR(64) DEFAULT '_default_' NOT NULL,
    filename    VARCHAR(512) NOT NULL,
    file_type   VARCHAR(20) NOT NULL,
    file_size   BIGINT NOT NULL,
    page_count  INT DEFAULT 0,
    chunk_count INT DEFAULT 0,
    status      VARCHAR(20) DEFAULT 'processing' NOT NULL,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);
"""

_CREATE_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id   VARCHAR(64) DEFAULT '_default_' NOT NULL,
    chunk_index INT NOT NULL,
    text        TEXT NOT NULL,
    embedding   vector({dim}),
    char_count  INT DEFAULT 0,
    metadata    JSONB DEFAULT '{{}}'
);
"""

_CREATE_HNSW_INDEX = """
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
ON chunks USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
"""

_CREATE_SUPPORTING_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON chunks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id);
"""


def ensure_vector_tables(dimension: int = 1536) -> None:
    """Create pgvector extension and tables if they don't exist."""
    try:
        from app.db.pg_client import _get_conn

        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_EXTENSION_SQL)
                    cur.execute(_CREATE_DOCUMENTS_TABLE)
                    cur.execute(_CREATE_CHUNKS_TABLE.format(dim=dimension))
                    try:
                        cur.execute(_CREATE_HNSW_INDEX)
                    except Exception:
                        logger.warning("HNSW index creation failed (may need more data)")
                    cur.execute(_CREATE_SUPPORTING_INDEXES)
        logger.info("Vector tables ensured (dimension=%d)", dimension)
    except Exception:
        logger.warning("Failed to ensure vector tables", exc_info=True)


# ── Document CRUD ─────────────────────────────────────────────────────

def insert_document(
    filename: str,
    file_type: str,
    file_size: int,
    page_count: int = 0,
    metadata: dict | None = None,
    tenant_id: str | None = None,
) -> int | None:
    """Insert a document record. Returns document_id or None on failure."""
    tid = tenant_db_id(tenant_id)
    try:
        from app.db.pg_client import _get_conn

        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO documents (tenant_id, filename, file_type, file_size, page_count, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (tid, filename, file_type, file_size, page_count,
                         json.dumps(metadata or {})),
                    )
                    row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        logger.warning("Failed to insert document", exc_info=True)
        return None


def update_document_status(
    document_id: int,
    status: str,
    chunk_count: int | None = None,
    tenant_id: str | None = None,
) -> bool:
    """Update document status and optionally chunk_count."""
    tid = tenant_db_id(tenant_id)
    try:
        from app.db.pg_client import _get_conn

        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    if chunk_count is not None:
                        cur.execute(
                            """
                            UPDATE documents
                            SET status = %s, chunk_count = %s, updated_at = NOW()
                            WHERE id = %s AND tenant_id = %s
                            """,
                            (status, chunk_count, document_id, tid),
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE documents
                            SET status = %s, updated_at = NOW()
                            WHERE id = %s AND tenant_id = %s
                            """,
                            (status, document_id, tid),
                        )
                    return cur.rowcount > 0
    except Exception:
        logger.warning("Failed to update document status", exc_info=True)
        return False


def get_document(document_id: int, tenant_id: str | None = None) -> dict | None:
    """Get a single document by ID."""
    tid = tenant_db_id(tenant_id)
    try:
        from app.db.pg_client import _get_conn
        import psycopg2.extras

        with _get_conn() as conn:
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT * FROM documents WHERE id = %s AND tenant_id = %s",
                        (document_id, tid),
                    )
                    row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        logger.warning("Failed to get document", exc_info=True)
        return None


def list_documents(tenant_id: str | None = None) -> list[dict]:
    """List all documents for a tenant."""
    tid = tenant_db_id(tenant_id)
    try:
        from app.db.pg_client import _get_conn
        import psycopg2.extras

        with _get_conn() as conn:
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT * FROM documents WHERE tenant_id = %s ORDER BY created_at DESC",
                        (tid,),
                    )
                    rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception:
        logger.warning("Failed to list documents", exc_info=True)
        return []


def delete_document(document_id: int, tenant_id: str | None = None) -> bool:
    """Delete a document and its chunks (CASCADE)."""
    tid = tenant_db_id(tenant_id)
    try:
        from app.db.pg_client import _get_conn

        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM documents WHERE id = %s AND tenant_id = %s",
                        (document_id, tid),
                    )
                    return cur.rowcount > 0
    except Exception:
        logger.warning("Failed to delete document", exc_info=True)
        return False


# ── Chunk CRUD ────────────────────────────────────────────────────────

def upsert_chunks(
    document_id: int,
    chunks: list[dict[str, Any]],
    tenant_id: str | None = None,
) -> int:
    """Insert chunk records with embeddings. Returns count inserted.

    Each chunk dict: {text, chunk_index, embedding, char_count, metadata}
    """
    tid = tenant_db_id(tenant_id)
    if not chunks:
        return 0

    try:
        from app.db.pg_client import _get_conn

        inserted = 0
        with _get_conn() as conn:
            with conn:
                with conn.cursor() as cur:
                    for chunk in chunks:
                        embedding = chunk.get("embedding")
                        # Convert list to pgvector string format
                        embedding_str = (
                            f"[{','.join(str(x) for x in embedding)}]"
                            if embedding
                            else None
                        )
                        cur.execute(
                            """
                            INSERT INTO chunks
                                (document_id, tenant_id, chunk_index, text, embedding, char_count, metadata)
                            VALUES (%s, %s, %s, %s, %s::vector, %s, %s)
                            """,
                            (
                                document_id,
                                tid,
                                chunk.get("chunk_index", 0),
                                chunk["text"],
                                embedding_str,
                                chunk.get("char_count", len(chunk["text"])),
                                json.dumps(chunk.get("metadata", {})),
                            ),
                        )
                        inserted += 1
        return inserted
    except Exception:
        logger.warning("Failed to upsert chunks", exc_info=True)
        return 0


# ── Vector Similarity Search ─────────────────────────────────────────

def similarity_search(
    query_embedding: list[float],
    tenant_id: str | None = None,
    top_k: int = 10,
    score_threshold: float = 0.0,
) -> list[dict]:
    """Search for similar chunks using cosine similarity.

    Returns list of {chunk_id, document_id, text, score, metadata, filename}.
    """
    tid = tenant_db_id(tenant_id)
    if not query_embedding:
        return []

    embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

    try:
        from app.db.pg_client import _get_conn
        import psycopg2.extras

        with _get_conn() as conn:
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT
                            c.id AS chunk_id,
                            c.document_id,
                            c.text,
                            c.chunk_index,
                            c.metadata AS chunk_metadata,
                            d.filename,
                            d.file_type,
                            1 - (c.embedding <=> %s::vector) AS score
                        FROM chunks c
                        JOIN documents d ON d.id = c.document_id
                        WHERE c.tenant_id = %s
                          AND c.embedding IS NOT NULL
                          AND d.status = 'ready'
                        ORDER BY c.embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (embedding_str, tid, embedding_str, top_k),
                    )
                    rows = cur.fetchall()

        results = []
        for row in rows:
            score = float(row["score"])
            if score >= score_threshold:
                results.append({
                    "chunk_id": row["chunk_id"],
                    "document_id": row["document_id"],
                    "text": row["text"],
                    "chunk_index": row["chunk_index"],
                    "score": score,
                    "metadata": row["chunk_metadata"] if isinstance(row["chunk_metadata"], dict) else json.loads(row["chunk_metadata"] or "{}"),
                    "filename": row["filename"],
                    "file_type": row["file_type"],
                })
        return results

    except Exception:
        logger.warning("Similarity search failed", exc_info=True)
        return []
