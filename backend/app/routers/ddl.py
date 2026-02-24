"""DDL upload endpoint."""

from __future__ import annotations

from fastapi import APIRouter, UploadFile

from app.config import settings
from app.exceptions import DDLParseError, FileTooLargeError
from app.ddl_parser.parser import parse_ddl
from app.models.schemas import ERDSchema

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
