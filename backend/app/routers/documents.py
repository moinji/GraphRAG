"""Document upload and management API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.exceptions import DocumentNotFoundError, DocumentValidationError
from app.models.schemas import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from app.tenant import get_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".markdown", ".html", ".htm", ".txt"}
_MAX_FILE_SIZE = getattr(settings, "doc_max_file_size_mb", 50) * 1024 * 1024


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_documents(
    request: Request,
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
) -> DocumentUploadResponse:
    """Upload one or more documents for processing.

    Files are validated, then processed asynchronously (parse -> chunk -> embed -> store).
    """
    tenant_id = get_tenant_id(request)
    max_files = getattr(settings, "doc_max_files", 10)

    if len(files) > max_files:
        raise DocumentValidationError(
            detail=f"Too many files (max {max_files})",
            errors=[f"Received {len(files)} files, maximum is {max_files}"],
        )

    accepted: list[dict] = []
    errors: list[str] = []

    for file in files:
        # Validate extension
        filename = file.filename or "unknown"
        ext = _get_extension(filename)
        if ext not in _SUPPORTED_EXTENSIONS:
            errors.append(f"{filename}: unsupported file type '{ext}' (supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))})")
            continue

        # Read content
        content = await file.read()

        # Validate size
        if len(content) > _MAX_FILE_SIZE:
            max_mb = getattr(settings, "doc_max_file_size_mb", 50)
            errors.append(f"{filename}: file too large ({len(content) // (1024*1024)}MB, max {max_mb}MB)")
            continue

        if not content:
            errors.append(f"{filename}: empty file")
            continue

        # Schedule background processing
        background_tasks.add_task(
            _process_document_task,
            filename=filename,
            content=content,
            tenant_id=tenant_id,
        )

        accepted.append({
            "filename": filename,
            "size": len(content),
            "status": "queued",
        })

    return DocumentUploadResponse(
        accepted=accepted,
        errors=errors,
        total_queued=len(accepted),
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(request: Request) -> DocumentListResponse:
    """List all documents for the current tenant."""
    tenant_id = get_tenant_id(request)
    from app.db.vector_store import list_documents as db_list_documents

    docs = db_list_documents(tenant_id=tenant_id)

    items = []
    for doc in docs:
        items.append(DocumentResponse(
            document_id=doc["id"],
            filename=doc["filename"],
            file_type=doc["file_type"],
            file_size=doc["file_size"],
            page_count=doc.get("page_count", 0),
            chunk_count=doc.get("chunk_count", 0),
            status=doc["status"],
            created_at=str(doc.get("created_at", "")),
        ))

    return DocumentListResponse(documents=items, total=len(items))


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int, request: Request) -> DocumentResponse:
    """Get a single document by ID."""
    tenant_id = get_tenant_id(request)
    from app.db.vector_store import get_document as db_get_document

    doc = db_get_document(document_id, tenant_id=tenant_id)
    if doc is None:
        raise DocumentNotFoundError(document_id)

    return DocumentResponse(
        document_id=doc["id"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        file_size=doc["file_size"],
        page_count=doc.get("page_count", 0),
        chunk_count=doc.get("chunk_count", 0),
        status=doc["status"],
        created_at=str(doc.get("created_at", "")),
    )


@router.delete("/{document_id}")
async def delete_document(document_id: int, request: Request) -> JSONResponse:
    """Delete a document and all its chunks."""
    tenant_id = get_tenant_id(request)
    from app.db.vector_store import delete_document as db_delete_document

    deleted = db_delete_document(document_id, tenant_id=tenant_id)
    if not deleted:
        raise DocumentNotFoundError(document_id)

    return JSONResponse(
        status_code=200,
        content={"detail": f"Document {document_id} deleted", "document_id": document_id},
    )


def _process_document_task(
    filename: str,
    content: bytes,
    tenant_id: str | None,
) -> None:
    """Background task: process a single document."""
    from app.document.pipeline import process_document

    chunk_size = getattr(settings, "doc_chunk_size", 1000)
    chunk_overlap = getattr(settings, "doc_chunk_overlap", 200)
    chunk_strategy = getattr(settings, "doc_chunk_strategy", "recursive")

    result = process_document(
        filename=filename,
        content=content,
        tenant_id=tenant_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        chunk_strategy=chunk_strategy,
    )

    if result.status == "failed":
        logger.error("Document processing failed for %s: %s", filename, result.errors)
    else:
        logger.info("Document processed: %s (%d chunks)", filename, result.chunk_count)


def _get_extension(filename: str) -> str:
    """Get lowercase file extension including the dot."""
    from pathlib import Path
    return Path(filename).suffix.lower()
