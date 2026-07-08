from io import BytesIO

import openpyxl
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.domain.cleaning import clean_keywords, split_raw_keyword_string
from app.schemas.keywords import (
    ExcelExtractResponse,
    ExcelPreviewResponse,
    ImportReport,
    KeywordParseRequest,
    KeywordParseResponse,
)

router = APIRouter(prefix="/keywords", tags=["keywords"])

MAX_FILE_SIZE_MB = 10


@router.post("/parse", response_model=KeywordParseResponse)
def parse_keywords(payload: KeywordParseRequest) -> KeywordParseResponse:
    keywords = split_raw_keyword_string(payload.raw_text)
    return KeywordParseResponse(keywords=keywords, count=len(keywords))


def _load_workbook(file_bytes: bytes) -> openpyxl.Workbook:
    try:
        return openpyxl.load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read Excel file: {exc}") from exc


def _validate_upload(file: UploadFile, content: bytes) -> None:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported.")
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_FILE_SIZE_MB}MB limit.")


@router.post("/import-excel/preview", response_model=ExcelPreviewResponse)
async def preview_excel(file: UploadFile = File(...)) -> ExcelPreviewResponse:
    content = await file.read()
    _validate_upload(file, content)
    wb = _load_workbook(content)

    columns: dict[str, list[str]] = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        try:
            first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        except StopIteration:
            first_row = ()
        headers = [
            str(cell).strip() if cell is not None else f"Column {i + 1}"
            for i, cell in enumerate(first_row)
        ]
        columns[sheet_name] = headers

    return ExcelPreviewResponse(sheet_names=wb.sheetnames, columns=columns)


@router.post("/import-excel/extract", response_model=ExcelExtractResponse)
async def extract_excel(
    file: UploadFile = File(...),
    sheet_name: str = Form(...),
    column_name: str = Form(...),
) -> ExcelExtractResponse:
    content = await file.read()
    _validate_upload(file, content)
    wb = _load_workbook(content)

    if sheet_name not in wb.sheetnames:
        raise HTTPException(status_code=400, detail=f"Sheet '{sheet_name}' not found.")

    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="Sheet is empty.")

    header = [
        str(c).strip() if c is not None else f"Column {i + 1}" for i, c in enumerate(rows[0])
    ]
    if column_name not in header:
        raise HTTPException(status_code=400, detail=f"Column '{column_name}' not found in sheet header.")

    col_index = header.index(column_name)

    rows_read = 0
    raw_values: list[str] = []
    skipped_reasons: dict[str, int] = {}

    for row in rows[1:]:
        rows_read += 1
        if col_index >= len(row) or row[col_index] is None or str(row[col_index]).strip() == "":
            skipped_reasons["empty_or_missing"] = skipped_reasons.get("empty_or_missing", 0) + 1
            continue
        raw_values.append(str(row[col_index]))

    cleaned = clean_keywords(raw_values)
    duplicates_removed = len(raw_values) - len(cleaned)
    if duplicates_removed > 0:
        skipped_reasons["duplicate"] = duplicates_removed

    report = ImportReport(
        rows_read=rows_read,
        rows_kept=len(cleaned),
        rows_skipped=rows_read - len(cleaned),
        skipped_reasons=skipped_reasons,
    )

    return ExcelExtractResponse(keywords=cleaned, report=report)
