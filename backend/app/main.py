"""FastAPI application factory."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import APIKeyMiddleware
from app.logging_config import setup_logging
from app.rate_limit import RateLimitMiddleware

# Initialize structured logging before anything else
setup_logging(env=os.getenv("APP_ENV", "development"))

from app.exceptions import (
    BuildJobNotFoundError,
    CSVValidationError,
    CypherExecutionError,
    DDLParseError,
    DocumentNotFoundError,
    DocumentValidationError,
    EmbeddingError,
    FileTooLargeError,
    LLMEnrichmentError,
    LocalSearchError,
    MappingValidationError,
    OntologyGenerationError,
    QueryRoutingError,
    VersionConflictError,
    VersionNotFoundError,
    WisdomError,
    build_job_not_found_handler,
    csv_validation_error_handler,
    cypher_execution_error_handler,
    ddl_parse_error_handler,
    document_not_found_handler,
    document_validation_error_handler,
    embedding_error_handler,
    file_too_large_handler,
    llm_enrichment_error_handler,
    local_search_error_handler,
    mapping_validation_error_handler,
    ontology_generation_error_handler,
    query_routing_error_handler,
    version_conflict_handler,
    version_not_found_handler,
    wisdom_error_handler,
)
from app.routers import csv_upload, ddl, documents, evaluation, graph, health, kg_build, mapping, ontology, ontology_versions, query, sse, wisdom

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    application = FastAPI(
        title="GraphRAG API",
        version="1.0.0",
        description="ERD → Knowledge Graph → GraphRAG",
    )

    # Rate limiting (production only, outermost → checked first)
    if os.getenv("APP_ENV", "development") == "production":
        application.add_middleware(RateLimitMiddleware, rate=60, window=60)

    # Auth middleware (must be added before CORS)
    application.add_middleware(APIKeyMiddleware)

    # CORS
    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
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
    application.add_exception_handler(LLMEnrichmentError, llm_enrichment_error_handler)
    application.add_exception_handler(LocalSearchError, local_search_error_handler)
    application.add_exception_handler(CSVValidationError, csv_validation_error_handler)
    application.add_exception_handler(MappingValidationError, mapping_validation_error_handler)
    application.add_exception_handler(WisdomError, wisdom_error_handler)
    application.add_exception_handler(DocumentValidationError, document_validation_error_handler)
    application.add_exception_handler(DocumentNotFoundError, document_not_found_handler)
    application.add_exception_handler(EmbeddingError, embedding_error_handler)

    # Routers
    application.include_router(health.router)
    application.include_router(ddl.router)
    application.include_router(ontology.router)
    application.include_router(ontology_versions.router)
    application.include_router(kg_build.router)
    application.include_router(query.router)
    application.include_router(evaluation.router)
    application.include_router(csv_upload.router)
    application.include_router(graph.router)
    application.include_router(mapping.router)
    application.include_router(wisdom.router)
    application.include_router(sse.router)
    application.include_router(documents.router)

    # Startup: ensure PG table + run migrations
    @application.on_event("startup")
    def _startup_ensure_pg_table() -> None:
        try:
            from app.db.pg_client import ensure_table

            ensure_table()
        except Exception:
            logger.error(
                "PG table setup failed at startup — version persistence disabled",
                exc_info=True,
            )

        try:
            from app.db.migrations import run_migrations

            run_migrations()
        except Exception:
            logger.error(
                "PG migrations failed at startup — some features may be unavailable",
                exc_info=True,
            )

    @application.on_event("shutdown")
    def _shutdown_close_connections() -> None:
        # Wait for active KG builds before closing connections
        try:
            from app.kg_builder.service import wait_for_active_builds

            wait_for_active_builds()
        except Exception:
            logger.warning("Failed to wait for active builds", exc_info=True)

        try:
            from app.db.neo4j_client import close_driver

            close_driver()
        except Exception:
            logger.warning("Neo4j driver close failed at shutdown", exc_info=True)

        try:
            from app.db.pg_client import close_pool

            close_pool()
        except Exception:
            logger.warning("PG pool close failed at shutdown", exc_info=True)

    return application


app = create_app()
