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
    """Raised when OpenAI API call fails (non-fatal)."""

    def __init__(self, detail: str = "LLM enrichment failed"):
        self.detail = detail
        super().__init__(detail)


class VersionNotFoundError(Exception):
    """Raised when an ontology version is not found."""

    def __init__(self, version_id: int):
        self.detail = f"Version {version_id} not found"
        self.version_id = version_id
        super().__init__(self.detail)


class VersionConflictError(Exception):
    """Raised when modifying an already-approved version."""

    def __init__(self, detail: str = "Version conflict"):
        self.detail = detail
        super().__init__(detail)


class BuildJobNotFoundError(Exception):
    """Raised when a KG build job is not found."""

    def __init__(self, job_id: str):
        self.detail = f"Build job {job_id} not found"
        self.job_id = job_id
        super().__init__(self.detail)


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


async def version_not_found_handler(
    _request: Request, exc: VersionNotFoundError
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.detail})


async def version_conflict_handler(
    _request: Request, exc: VersionConflictError
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.detail})


async def build_job_not_found_handler(
    _request: Request, exc: BuildJobNotFoundError
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.detail})


class QueryRoutingError(Exception):
    """Raised when query routing fails (invalid input)."""

    def __init__(self, detail: str = "Query routing failed"):
        self.detail = detail
        super().__init__(detail)


class CypherExecutionError(Exception):
    """Raised when Neo4j Cypher execution fails."""

    def __init__(self, detail: str = "Cypher execution failed"):
        self.detail = detail
        super().__init__(detail)


async def query_routing_error_handler(
    _request: Request, exc: QueryRoutingError
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.detail})


async def cypher_execution_error_handler(
    _request: Request, exc: CypherExecutionError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.detail})


class CSVValidationError(Exception):
    """Raised when CSV upload validation fails."""

    def __init__(self, detail: str = "CSV validation failed", errors: list[str] | None = None):
        self.detail = detail
        self.errors = errors or []
        super().__init__(detail)


async def csv_validation_error_handler(
    _request: Request, exc: CSVValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": exc.detail, "errors": exc.errors},
    )


class MappingValidationError(Exception):
    """Raised when YAML mapping validation fails."""

    def __init__(self, detail: str = "Mapping validation failed", errors: list[str] | None = None):
        self.detail = detail
        self.errors = errors or []
        super().__init__(detail)


async def mapping_validation_error_handler(
    _request: Request, exc: MappingValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": exc.detail, "errors": exc.errors},
    )


class LocalSearchError(Exception):
    """Raised when B안 local search fails."""

    def __init__(self, detail: str = "Local search failed"):
        self.detail = detail
        super().__init__(detail)


async def local_search_error_handler(
    _request: Request, exc: LocalSearchError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.detail})


class WisdomError(Exception):
    """Raised when DIKW wisdom analysis fails."""

    def __init__(self, detail: str = "Wisdom analysis failed"):
        self.detail = detail
        super().__init__(detail)


async def wisdom_error_handler(
    _request: Request, exc: WisdomError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.detail})
