"""Application configuration via pydantic-settings."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings

# Fix SSL cert path for Anaconda/Windows (needed for neo4j+s:// AuraDB)
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"
    neo4j_connect_timeout: int = 10

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "graphrag"
    postgres_password: str = "graphrag123"
    postgres_db: str = "graphrag_meta"

    # OpenAI
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    openai_router_model: str = "gpt-4o-mini"

    # Anthropic (fallback)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"

    # B안 Local Search
    local_search_model: str = "gpt-4o"
    local_search_max_tokens: int = 2048
    local_search_default_depth: int = 2
    local_search_max_nodes: int = 50

    # Wisdom Engine
    wisdom_model: str = "gpt-4o"
    wisdom_max_tokens: int = 4096

    # CSV Import
    csv_max_file_size_mb: int = 50
    csv_max_files: int = 50

    # OWL Reasoner
    enable_owl: bool = False
    owl_base_uri: str = "http://graphrag.io/ontology#"
    owl_max_inferred_triples: int = 500
    owl_reasoning_timeout_sec: int = 30

    # Document Processing (v5.0)
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 100
    doc_max_file_size_mb: int = 50
    doc_max_files: int = 10
    doc_chunk_size: int = 1000       # characters
    doc_chunk_overlap: int = 200     # characters
    doc_chunk_strategy: str = "recursive"  # recursive | fixed | sentence

    # Redis (optional — in-memory fallback when unset)
    redis_url: str | None = None  # e.g. redis://localhost:6379/0

    # Rate limiting
    rate_limit_enabled: bool = True  # Set False to disable
    rate_limit_rate: int = 60  # requests per window
    rate_limit_window: int = 60  # window in seconds

    # App
    port: int = 8080  # Cloud Run uses PORT env var
    app_env: str = "development"
    ddl_max_size_mb: int = 10
    app_api_key: str | None = None  # Set to enable API key auth (single-tenant)
    tenant_keys: str | None = None  # JSON: {"api_key_1": "tenant_a", ...} (multi-tenant)

    model_config = {
        "env_file": (str(_PROJECT_ROOT / ".env.example"), str(_PROJECT_ROOT / ".env")),
        "extra": "ignore",
    }


settings = Settings()
