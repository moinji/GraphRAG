"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.exceptions import (
    BuildJobNotFoundError,
    CSVValidationError,
    CypherExecutionError,
    DDLParseError,
    FileTooLargeError,
    LocalSearchError,
    OntologyGenerationError,
    QueryRoutingError,
    VersionConflictError,
    VersionNotFoundError,
    build_job_not_found_handler,
    csv_validation_error_handler,
    cypher_execution_error_handler,
    ddl_parse_error_handler,
    file_too_large_handler,
    local_search_error_handler,
    ontology_generation_error_handler,
    query_routing_error_handler,
    version_conflict_handler,
    version_not_found_handler,
)
from app.routers import csv_upload, ddl, evaluation, health, kg_build, ontology, ontology_versions, query

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    application = FastAPI(
        title="GraphRAG API",
        version="0.8.0",
        description="ERD → Knowledge Graph → GraphRAG",
    )

    # CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error handlers
    application.add_exception_handler(DDLParseError, ddl_parse_error_handler)
    application.add_exception_handler(FileTooLargeError, file_too_large_handler)
    application.add_exception_handler(
        OntologyGenerationError, ontology_generation_error_handler
    )
    application.add_exception_handler(VersionNotFoundError, version_not_found_handler)
    application.add_exception_handler(VersionConflictError, version_conflict_handler)
    application.add_exception_handler(BuildJobNotFoundError, build_job_not_found_handler)
    application.add_exception_handler(QueryRoutingError, query_routing_error_handler)
    application.add_exception_handler(CypherExecutionError, cypher_execution_error_handler)
    application.add_exception_handler(LocalSearchError, local_search_error_handler)
    application.add_exception_handler(CSVValidationError, csv_validation_error_handler)

    # Routers
    application.include_router(health.router)
    application.include_router(ddl.router)
    application.include_router(ontology.router)
    application.include_router(ontology_versions.router)
    application.include_router(kg_build.router)
    application.include_router(query.router)
    application.include_router(evaluation.router)
    application.include_router(csv_upload.router)

    # Startup: ensure PG table + run migrations
    @application.on_event("startup")
    def _startup_ensure_pg_table() -> None:
        try:
            from app.db.pg_client import ensure_table

            ensure_table()
        except Exception:
            logger.warning("PG table setup failed at startup", exc_info=True)

        try:
            from app.db.migrations import run_migrations

            run_migrations()
        except Exception:
            logger.warning("PG migrations failed at startup", exc_info=True)

    return application


app = create_app()
