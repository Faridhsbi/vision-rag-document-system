from fastapi import APIRouter, HTTPException

from app.rag.pipeline import get_pipeline
from app.rag.schemas import DocumentChunk, DocumentSummary

router = APIRouter(tags=["documents"])


@router.get("/documents", response_model=list[DocumentSummary])
async def list_documents() -> list[DocumentSummary]:
    try:
        return get_pipeline().list_documents()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/documents/{document_id}/chunks", response_model=list[DocumentChunk])
async def get_document_chunks(document_id: str) -> list[DocumentChunk]:
    try:
        return get_pipeline().get_chunks(document_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str) -> dict[str, str]:
    try:
        return get_pipeline().delete_document(document_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

