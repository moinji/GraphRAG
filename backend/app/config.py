"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "graphrag"
    postgres_password: str = "graphrag123"
    postgres_db: str = "graphrag_meta"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_router_model: str = "claude-haiku-4-5-20251001"

    # B안 Local Search
    local_search_model: str = "claude-sonnet-4-20250514"
    local_search_max_tokens: int = 2048
    local_search_default_depth: int = 2
    local_search_max_nodes: int = 50

    # CSV Import
    csv_max_file_size_mb: int = 50
    csv_max_files: int = 20

    # App
    app_env: str = "development"
    ddl_max_size_mb: int = 10

    model_config = {"env_file": ".env.example", "extra": "ignore"}


settings = Settings()
