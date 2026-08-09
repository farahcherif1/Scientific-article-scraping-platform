from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import articles, collections, custom_connectors, exports, history, keywords
from app.config import settings
from app.db.session import init_db
from app.infra.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    init_db()
    yield


app = FastAPI(
    title="Team08-E26 - Yonnov'IA Scientific Scraping Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(keywords.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")
app.include_router(collections.router, prefix="/api/v1")
app.include_router(custom_connectors.router, prefix="/api/v1")
app.include_router(articles.router, prefix="/api/v1")
app.include_router(exports.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
