"""Document processing pipeline: parse -> chunk -> embed -> store.

Orchestrates the full document ingestion flow, similar to kg_builder/service.py pattern.
Designed to run as a BackgroundTask.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.document.chunker import chunk_pages, chunk_text
from app.document.embedder import embed_texts
from app.document.parser import ParsedDocument, parse_document
from app.db import vector_store

logger = logging.getLogger(__name__)


@dataclass
class DocumentProcessingResult:
    """Result of processing a single document."""
    document_id: int
    filename: str
    status: str  # "ready" | "failed"
    chunk_count: int = 0
    page_count: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


def process_document(
    filename: str,
    content: bytes,
    tenant_id: str | None = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    chunk_strategy: str = "recursive",
) -> DocumentProcessingResult:
    """Run the full document processing pipeline.

    Steps:
        1. Insert document record (status=processing)
        2. Parse document -> extract text
        3. Chunk text
        4. Embed chunks
        5. Store chunks in pgvector
        6. Update document status (ready/failed)
    """
    start = time.time()

    # Step 1: Create document record
    doc_id = vector_store.insert_document(
        filename=filename,
        file_type=_guess_type(filename),
        file_size=len(content),
        tenant_id=tenant_id,
    )

    if doc_id is None:
        return DocumentProcessingResult(
            document_id=-1,
            filename=filename,
            status="failed",
            errors=["Failed to create document record in database"],
        )

    try:
        # Step 2: Parse
        parsed = parse_document(filename, content)
        if parsed.errors:
            _fail_document(doc_id, tenant_id)
            return DocumentProcessingResult(
                document_id=doc_id,
                filename=filename,
                status="failed",
                errors=parsed.errors,
            )

        if not parsed.full_text.strip():
            _fail_document(doc_id, tenant_id)
            return DocumentProcessingResult(
                document_id=doc_id,
                filename=filename,
                status="failed",
                errors=["Document contains no extractable text"],
            )

        # Step 3: Chunk
        if parsed.pages:
            page_dicts = [
                {"page_num": p.page_num, "text": p.text}
                for p in parsed.pages
            ]
            chunks = chunk_pages(
                page_dicts,
                strategy=chunk_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        else:
            chunks = chunk_text(
                parsed.full_text,
                strategy=chunk_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

        if not chunks:
            _fail_document(doc_id, tenant_id)
            return DocumentProcessingResult(
                document_id=doc_id,
                filename=filename,
                status="failed",
                errors=["Chunking produced no chunks"],
            )

        # Step 4: Embed
        chunk_texts = [c.text for c in chunks]
        embeddings = embed_texts(chunk_texts)

        # Step 5: Store chunks
        chunk_dicts = []
        for i, chunk in enumerate(chunks):
            chunk_dicts.append({
                "text": chunk.text,
                "chunk_index": chunk.index,
                "embedding": embeddings[i] if i < len(embeddings) else None,
                "char_count": chunk.char_count,
                "metadata": chunk.metadata,
            })

        inserted = vector_store.upsert_chunks(
            document_id=doc_id,
            chunks=chunk_dicts,
            tenant_id=tenant_id,
        )

        # Step 6: Link to KG (best-effort, non-fatal)
        try:
            from app.document.linker import link_document_to_kg
            link_chunks = [
                {
                    "text": c.text,
                    "chunk_index": c.index,
                    "metadata": c.metadata,
                }
                for c in chunks
            ]
            link_result = link_document_to_kg(
                document_id=doc_id,
                chunks=link_chunks,
                tenant_id=tenant_id,
            )
            if link_result.errors:
                logger.warning("KG linking warnings: %s", link_result.errors)
            else:
                logger.info(
                    "KG linked: doc=%d, chunks=%d, mentions=%d",
                    doc_id, link_result.chunk_nodes_created, link_result.mentions_created,
                )
        except Exception as e:
            logger.debug("KG linking failed (non-fatal): %s", e)

        # Step 7: Update status
        vector_store.update_document_status(
            document_id=doc_id,
            status="ready",
            chunk_count=inserted,
            tenant_id=tenant_id,
        )

        duration = time.time() - start
        logger.info(
            "Document processed: %s -> %d chunks in %.1fs",
            filename, inserted, duration,
        )

        return DocumentProcessingResult(
            document_id=doc_id,
            filename=filename,
            status="ready",
            chunk_count=inserted,
            page_count=parsed.page_count,
            duration_seconds=round(duration, 2),
        )

    except Exception as e:
        logger.error("Document processing failed: %s", e, exc_info=True)
        _fail_document(doc_id, tenant_id)
        return DocumentProcessingResult(
            document_id=doc_id,
            filename=filename,
            status="failed",
            errors=[f"Processing error: {e}"],
            duration_seconds=round(time.time() - start, 2),
        )


def _fail_document(doc_id: int, tenant_id: str | None) -> None:
    """Mark document as failed."""
    vector_store.update_document_status(
        document_id=doc_id,
        status="failed",
        tenant_id=tenant_id,
    )


def _guess_type(filename: str) -> str:
    """Guess file type from filename."""
    from app.document.parser import detect_file_type
    return detect_file_type(filename) or "unknown"
