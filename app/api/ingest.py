import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import get_settings
from app.rag.pipeline import get_pipeline
from app.rag.schemas import IngestResponse

router = APIRouter(tags=["ingestion"])


def _safe_upload_name(filename: str) -> str:
    name = Path(filename).name
    return name or "uploaded.pdf"


@router.post("/ingest", response_model=IngestResponse)
async def ingest_pdf(file: UploadFile = File(...)) -> IngestResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    settings = get_settings()
    filename = _safe_upload_name(file.filename)
    target_path = settings.raw_dir / filename

    with target_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        return get_pipeline().ingest_pdf(target_path, filename)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

