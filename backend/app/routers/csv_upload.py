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
    except json.JSONDecodeError as e:
        raise CSVValidationError(
            detail="Invalid ERD JSON",
            errors=[str(e)],
        )
    try:
        erd = ERDSchema(**erd_dict)
    except (ValueError, TypeError) as e:
        raise CSVValidationError(
            detail="Invalid ERD schema",
            errors=[str(e)],
        )

    # Validate file count
    if len(files) > settings.csv_max_files:
        raise CSVValidationError(
            detail=f"파일이 너무 많습니다 (최대 {settings.csv_max_files}개)",
            errors=[f"업로드된 파일 {len(files)}개, 최대 {settings.csv_max_files}개"],
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
    data, summaries, errors, warnings = parse_csv_files(files_data, erd)

    # 유효한 파일이 0개 → 진짜 실패
    if not data:
        raise CSVValidationError(
            detail="CSV validation failed",
            errors=errors,
        )

    # 유효한 파일이 1개라도 있으면 부분 성공 (errors + warnings를 응답에 포함)
    session_id = create_session(data)

    return CSVUploadResponse(
        csv_session_id=session_id,
        tables=summaries,
        errors=errors,
        warnings=warnings,
    )
