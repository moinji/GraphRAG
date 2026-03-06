"""DDL upload + NL→DDL generation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, UploadFile

from app.config import settings
from app.exceptions import DDLParseError, FileTooLargeError
from app.ddl_parser.parser import parse_ddl
from app.models.schemas import ERDSchema, NLToDDLRequest, NLToDDLResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ddl", tags=["ddl"])


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
