"""CSV upload endpoint — parse, validate, and store CSV data in-memory."""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, UploadFile

from app.config import settings
from app.csv_import.parser import create_session, parse_csv_files
from app.exceptions import CSVValidationError
from app.models.schemas import CSVUploadResponse, ERDSchema

router = APIRouter(prefix="/api/v1/csv", tags=["csv-import"])


@router.post("/upload", response_model=CSVUploadResponse)
async def upload_csv(
    files: list[UploadFile] = File(...),
    erd_json: str = Form(...),
) -> CSVUploadResponse:
    """Upload CSV files for KG build.

    - files: one .csv per table (filename = table_name.csv)
    - erd_json: JSON string of ERDSchema (Form field since multipart)
    """
    # Parse ERD from JSON string
    try:
        erd_dict = json.loads(erd_json)
        erd = ERDSchema(**erd_dict)
    except (json.JSONDecodeError, Exception) as e:
        raise CSVValidationError(
            detail="Invalid ERD JSON",
            errors=[str(e)],
        )

    # Validate file count
    if len(files) > settings.csv_max_files:
        raise CSVValidationError(
            detail=f"Too many files (max {settings.csv_max_files})",
            errors=[f"Uploaded {len(files)} files, maximum is {settings.csv_max_files}"],
        )

    # Read all files
    files_data: list[tuple[str, bytes]] = []
    for f in files:
        content = await f.read()

        # Validate file size
        size_mb = len(content) / (1024 * 1024)
        if size_mb > settings.csv_max_file_size_mb:
            raise CSVValidationError(
                detail=f"File '{f.filename}' exceeds {settings.csv_max_file_size_mb}MB limit",
                errors=[f"{f.filename}: {size_mb:.1f}MB exceeds {settings.csv_max_file_size_mb}MB limit"],
            )

        files_data.append((f.filename or "unknown.csv", content))

    # Parse and validate
    data, summaries, errors = parse_csv_files(files_data, erd)

    if errors:
        raise CSVValidationError(
            detail="CSV validation failed",
            errors=errors,
        )

    # Store in session
    session_id = create_session(data)

    return CSVUploadResponse(
        csv_session_id=session_id,
        tables=summaries,
    )
