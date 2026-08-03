from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.models import CollectionRun
from app.db.session import get_db
from app.exporters.csv_exporter import export_articles_to_csv
from app.exporters.json_exporter import export_articles_to_json
from app.exporters.xlsx_exporter import export_dataset_to_xlsx
from app.schemas.articles import SortField
from app.use_cases.export_dataset import build_export_dataset
from app.use_cases.list_articles import ArticleFilters

router = APIRouter(prefix="/collections/{collection_id}", tags=["exports"])

_MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
}


def _get_run_or_404(db: Session, collection_id: str) -> CollectionRun:
    try:
        numeric_id = CollectionRun.numeric_id(collection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown collection id.") from exc
    run = db.get(CollectionRun, numeric_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown collection id.")
    return run


@router.get("/export")
def export_collection(
    collection_id: str,
    format: Literal["xlsx", "csv", "json"] = Query(...),
    sort: SortField = "-relevance",
    year_from: int | None = Query(default=None, ge=1900),
    year_to: int | None = Query(default=None, ge=1900),
    source: list[str] | None = Query(default=None),
    has_doi: bool | None = None,
    has_abstract: bool | None = None,
    keyword: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
) -> Response:
    """
    US-06.1/US-06.2: same filter/sort query params as GET .../articles, so
    whatever the Results page currently has active gets carried into the
    exported file.
    """
    if year_from is not None and year_to is not None and year_from > year_to:
        raise HTTPException(status_code=422, detail="year_from must not be after year_to.")
    if source is not None and len(source) > 50:
        raise HTTPException(status_code=422, detail="Too many source filters.")

    run = _get_run_or_404(db, collection_id)
    filters = ArticleFilters(
        year_from=year_from,
        year_to=year_to,
        sources=source,
        has_doi=has_doi,
        has_abstract=has_abstract,
        keyword=keyword,
    )
    dataset = build_export_dataset(db, run, sort=sort, filters=filters)

    filename = f"{run.public_id}_export.{format}"
    if format == "xlsx":
        content: bytes | str = export_dataset_to_xlsx(dataset)
    elif format == "csv":
        content = export_articles_to_csv(dataset.articles)
    else:
        content = export_articles_to_json(dataset.articles)

    return Response(
        content=content,
        media_type=_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
