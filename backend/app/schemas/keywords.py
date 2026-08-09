from pydantic import BaseModel, Field

# Generous ceiling on the pasted-text box (~7500 average-length keywords) -
# large enough that no real user hits it, small enough that a client can't
# use this endpoint to push a multi-MB payload through the parser (security
# review finding: DoS via unbounded input).
_MAX_RAW_TEXT_LEN = 50_000


class KeywordParseRequest(BaseModel):
    raw_text: str = Field(max_length=_MAX_RAW_TEXT_LEN)


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
