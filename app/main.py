from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.documents import router as documents_router
from app.api.ingest import router as ingest_router
from app.api.query import router as query_router
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Multimodal RAG API for the Bank Mandiri 2025 technical test, "
        "including PDF ingestion, vector retrieval, and source-aware QA."
    ),
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(documents_router)

# Serve monolithic static web application
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

