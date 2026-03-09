"""DDL upload + NL→DDL generation + example schema endpoints."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.exceptions import DDLParseError, FileTooLargeError
from app.ddl_parser.parser import parse_ddl
from app.models.schemas import ERDSchema, NLToDDLRequest, NLToDDLResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ddl", tags=["ddl"])

# ── Example schemas ──────────────────────────────────────────────

_EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "examples" / "schemas"

_DOMAIN_EXAMPLES = [
    {"key": "ecommerce", "file": "demo_ecommerce.sql", "name": "E-Commerce", "description": "고객, 상품, 주문, 리뷰, 카테고리, 배송 (12 tables)"},
    {"key": "accounting", "file": "demo_accounting.sql", "name": "회계 (Accounting)", "description": "계정과목, 전표, 분개, 예산, 부서, 거래처 (10 tables)"},
    {"key": "hr", "file": "demo_hr.sql", "name": "인사 (HR)", "description": "직원, 부서, 프로젝트, 스킬, 출결, 평가 (11 tables)"},
    {"key": "hospital", "file": "demo_hospital.sql", "name": "병원 (Hospital)", "description": "환자, 의사, 진료, 처방, 검사, 입원 (11 tables)"},
]


class DomainExampleSummary(BaseModel):
    key: str
    name: str
    description: str
    table_count: int
    fk_count: int


class DomainExampleDetail(BaseModel):
    key: str
    name: str
    ddl: str
    erd: ERDSchema


@router.post("/upload", response_model=ERDSchema)
async def upload_ddl(file: UploadFile) -> ERDSchema:
    raw = await file.read()

    # Size guard
    max_bytes = settings.ddl_max_size_mb * 1024 * 1024
    if len(raw) > max_bytes:
        raise FileTooLargeError(settings.ddl_max_size_mb)

    # Empty file guard
    if len(raw) == 0:
        raise DDLParseError("Uploaded file is empty")

    # UTF-8 decode
    try:
        ddl_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise DDLParseError("File is not valid UTF-8 text")

    # Parse
    try:
        erd = parse_ddl(ddl_text)
    except Exception as e:
        raise DDLParseError(f"DDL parsing failed: {e}")

    return erd


@router.post("/generate-from-nl", response_model=NLToDDLResponse)
def generate_from_nl(body: NLToDDLRequest) -> NLToDDLResponse:
    """Generate DDL SQL from natural language description using LLM."""
    from app.ddl_parser.nl_to_ddl import generate_ddl_from_nl

    try:
        ddl = generate_ddl_from_nl(body.description)
    except ValueError as e:
        raise DDLParseError(str(e))
    except Exception as e:
        logger.error("NL→DDL generation failed: %s", e, exc_info=True)
        raise DDLParseError(f"DDL generation failed: {e}")

    # Try to parse the generated DDL
    erd = None
    try:
        erd = parse_ddl(ddl)
    except Exception:
        logger.warning("Generated DDL could not be parsed — returning raw DDL only")

    return NLToDDLResponse(ddl=ddl, erd=erd)


@router.get("/examples", response_model=list[DomainExampleSummary])
def list_examples() -> list[DomainExampleSummary]:
    """List available domain example schemas."""
    result = []
    for ex in _DOMAIN_EXAMPLES:
        path = _EXAMPLES_DIR / ex["file"]
        if not path.exists():
            continue
        ddl = path.read_text(encoding="utf-8")
        try:
            erd = parse_ddl(ddl)
            result.append(DomainExampleSummary(
                key=ex["key"],
                name=ex["name"],
                description=ex["description"],
                table_count=len(erd.tables),
                fk_count=len(erd.foreign_keys),
            ))
        except Exception:
            logger.warning("Failed to parse example %s", ex["key"])
    return result


@router.get("/examples/{key}", response_model=DomainExampleDetail)
def get_example(key: str) -> DomainExampleDetail:
    """Load a specific domain example schema with parsed ERD."""
    for ex in _DOMAIN_EXAMPLES:
        if ex["key"] == key:
            path = _EXAMPLES_DIR / ex["file"]
            if not path.exists():
                raise DDLParseError(f"Example schema file not found: {ex['file']}")
            ddl = path.read_text(encoding="utf-8")
            try:
                erd = parse_ddl(ddl)
            except Exception as e:
                raise DDLParseError(f"Failed to parse example: {e}")
            return DomainExampleDetail(key=key, name=ex["name"], ddl=ddl, erd=erd)
    raise DDLParseError(f"Unknown example: {key}")
