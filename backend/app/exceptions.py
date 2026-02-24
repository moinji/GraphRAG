"""Custom exceptions and FastAPI error handlers."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class DDLParseError(Exception):
    """Raised when DDL text cannot be parsed."""

    def __init__(self, detail: str = "Failed to parse DDL"):
        self.detail = detail
        super().__init__(detail)


class FileTooLargeError(Exception):
    """Raised when uploaded file exceeds size limit."""

    def __init__(self, max_mb: int):
        self.detail = f"File exceeds maximum size of {max_mb}MB"
        super().__init__(self.detail)


class OntologyGenerationError(Exception):
    """Raised when the ontology pipeline fails."""

    def __init__(self, detail: str = "Ontology generation failed"):
        self.detail = detail
        super().__init__(detail)


class LLMEnrichmentError(Exception):
    """Raised when Claude API call fails (non-fatal)."""

    def __init__(self, detail: str = "LLM enrichment failed"):
        self.detail = detail
        super().__init__(detail)


class DatabaseError(Exception):
    """Raised when PG operation fails (non-fatal)."""

    def __init__(self, detail: str = "Database operation failed"):
        self.detail = detail
        super().__init__(detail)


async def ddl_parse_error_handler(_request: Request, exc: DDLParseError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.detail})


async def file_too_large_handler(_request: Request, exc: FileTooLargeError) -> JSONResponse:
    return JSONResponse(status_code=413, content={"detail": exc.detail})


async def ontology_generation_error_handler(
    _request: Request, exc: OntologyGenerationError
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.detail})


async def llm_enrichment_error_handler(
    _request: Request, exc: LLMEnrichmentError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.detail})


async def database_error_handler(_request: Request, exc: DatabaseError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": exc.detail})
