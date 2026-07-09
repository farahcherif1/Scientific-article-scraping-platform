from pydantic import BaseModel


class KeywordParseRequest(BaseModel):
    raw_text: str


class KeywordParseResponse(BaseModel):
    keywords: list[str]
    count: int


class ExcelPreviewResponse(BaseModel):
    sheet_names: list[str]
    columns: dict[str, list[str]]


class ImportReport(BaseModel):
    rows_read: int
    rows_kept: int
    rows_skipped: int
    skipped_reasons: dict[str, int]


class ExcelExtractResponse(BaseModel):
    keywords: list[str]
    report: ImportReport
