from fastapi import APIRouter, HTTPException

from app.rag.pipeline import get_pipeline
from app.rag.schemas import QueryRequest, QueryResponse

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query_document(payload: QueryRequest) -> QueryResponse:
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    try:
        return get_pipeline().query(
            document_id=payload.document_id,
            question=payload.question,
            top_k=payload.top_k,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

