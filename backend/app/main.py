from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import keywords

app = FastAPI(
    title="Team08-E26 - Yonnov'IA Scientific Scraping Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(keywords.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
