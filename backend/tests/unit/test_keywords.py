from io import BytesIO

import openpyxl
from fastapi.testclient import TestClient

from app.domain.cleaning import clean_keywords, split_raw_keyword_string
from app.main import app

client = TestClient(app)


def test_clean_keywords_dedup_and_strip():
    result = clean_keywords(["  AI  ", "ai", "Machine Learning", "", "  "])
    assert result == ["AI", "Machine Learning"]


def test_split_raw_keyword_string_multiple_separators():
    result = split_raw_keyword_string("AI\nmachine learning; NLP, ai")
    assert result == ["AI", "machine learning", "NLP"]


def test_parse_endpoint():
    response = client.post("/api/v1/keywords/parse", json={"raw_text": "AI\nAI\nrobotics"})
    assert response.status_code == 200
    body = response.json()
    assert body["keywords"] == ["AI", "robotics"]
    assert body["count"] == 2


def _build_test_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Term", "Notes"])
    ws.append(["machine learning", "x"])
    ws.append(["AI", "y"])
    ws.append(["ai", "dup"])
    ws.append([None, "empty term"])
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_preview_excel_returns_sheets_and_headers():
    content = _build_test_xlsx()
    response = client.post(
        "/api/v1/keywords/import-excel/preview",
        files={"file": ("keywords.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sheet_names"] == ["Sheet1"]
    assert body["columns"]["Sheet1"] == ["Term", "Notes"]


def test_extract_excel_cleans_and_reports():
    content = _build_test_xlsx()
    response = client.post(
        "/api/v1/keywords/import-excel/extract",
        files={"file": ("keywords.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"sheet_name": "Sheet1", "column_name": "Term"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["keywords"] == ["machine learning", "AI"]
    assert body["report"]["rows_read"] == 4
    assert body["report"]["rows_kept"] == 2
    assert body["report"]["skipped_reasons"]["empty_or_missing"] == 1
    assert body["report"]["skipped_reasons"]["duplicate"] == 1


def test_extract_excel_rejects_non_xlsx():
    response = client.post(
        "/api/v1/keywords/import-excel/extract",
        files={"file": ("keywords.txt", b"not an excel file", "text/plain")},
        data={"sheet_name": "Sheet1", "column_name": "Term"},
    )
    assert response.status_code == 400


def test_extract_excel_rejects_unknown_column():
    content = _build_test_xlsx()
    response = client.post(
        "/api/v1/keywords/import-excel/extract",
        files={"file": ("keywords.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"sheet_name": "Sheet1", "column_name": "NotAColumn"},
    )
    assert response.status_code == 400
