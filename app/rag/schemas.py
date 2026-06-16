from typing import Any, Literal

from pydantic import BaseModel, Field


ChunkType = Literal["text", "table", "visual", "image_caption", "chart"]


class DocumentChunk(BaseModel):
    id: str
    document_id: str
    page: int
    type: ChunkType
    content: str
    source: str
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    document_id: str
    filename: str
    pages_processed: int
    chunks_created: int
    tables_extracted: int
    visual_chunks_extracted: int
    status: str = "success"


class QueryRequest(BaseModel):
    document_id: str
    question: str
    top_k: int | None = Field(default=None, ge=1, le=20)


class SourceMetadata(BaseModel):
    chunk_id: str
    page: int
    type: str
    score: float | None = None
    excerpt: str
    title: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceMetadata]


class DocumentSummary(BaseModel):
    document_id: str
    filename: str | None = None
    chunks: int
    pages: list[int]

