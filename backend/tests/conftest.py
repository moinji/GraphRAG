"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure backend is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402
from app.ddl_parser.parser import parse_ddl  # noqa: E402
from app.models.schemas import ERDSchema  # noqa: E402

_SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent / "examples" / "schemas"

ECOMMERCE_DDL_PATH = _SCHEMAS_DIR / "demo_ecommerce.sql"
ECOMMERCE_DDL = ECOMMERCE_DDL_PATH.read_text(encoding="utf-8")


@pytest.fixture
def ecommerce_ddl() -> str:
    """Full 12-table e-commerce DDL text."""
    return ECOMMERCE_DDL


@pytest.fixture
def ecommerce_erd(ecommerce_ddl) -> ERDSchema:
    """Parsed ERDSchema from the 12-table e-commerce DDL."""
    return parse_ddl(ecommerce_ddl)


def _load_domain_ddl(name: str) -> str:
    return (_SCHEMAS_DIR / name).read_text(encoding="utf-8")


@pytest.fixture
def accounting_ddl() -> str:
    return _load_domain_ddl("demo_accounting.sql")


@pytest.fixture
def hr_ddl() -> str:
    return _load_domain_ddl("demo_hr.sql")


@pytest.fixture
def hospital_ddl() -> str:
    return _load_domain_ddl("demo_hospital.sql")


@pytest.fixture
def app():
    """FastAPI test application."""
    return create_app()


@pytest.fixture
async def client(app):
    """Async test client for API tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
