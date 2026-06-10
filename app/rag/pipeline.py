"""RAG pipeline orchestrating LangChain components.

Coordinates:
  PDFParser → DocumentChunker → GeminiEmbedder (LangChain Embeddings)
  → ChromaVectorStore → DocumentRetriever (LangChain BaseRetriever)
  → LangChainQAGenerator (LCEL chain)
"""

from functools import lru_cache
from pathlib import Path

from app.core.config import Settings, get_settings
from app.rag.chunker import DocumentChunker
from app.rag.embedder import GeminiEmbedder
from app.rag.generator import GeminiVisionInterpreter, LangChainQAGenerator
from app.rag.parser import PDFParser, make_document_id
from app.rag.retriever import DocumentRetriever
from app.rag.schemas import (
    DocumentChunk,
    DocumentSummary,
    IngestResponse,
    QueryResponse,
    SourceMetadata,
)
from app.rag.vector_store import ChromaVectorStore


def _excerpt(text: str, limit: int = 360) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0] + "..."


class RAGPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.parser = PDFParser(settings.processed_dir)
        self.chunker = DocumentChunker(settings)
        self.embedder = GeminiEmbedder(settings)
        self.vector_store = ChromaVectorStore(settings)
        self.retriever = DocumentRetriever(
            embedder=self.embedder,
            vector_store=self.vector_store,
        )
        self.answer_generator = LangChainQAGenerator(settings)
        self.vision_interpreter = GeminiVisionInterpreter(settings)

    # ── Ingestion ────────────────────────────────────────────────────

    def ingest_pdf(self, pdf_path: Path, filename: str) -> IngestResponse:
        document_id = make_document_id(filename)
        visual_describer = (
            self.vision_interpreter.describe_image
            if self.settings.enable_visual_captioning
            else None
        )
        parsed_chunks, page_count, table_count, visual_count = self.parser.parse(
            pdf_path=pdf_path,
            document_id=document_id,
            source_filename=filename,
            visual_page_numbers=self.settings.visual_caption_page_numbers,
            visual_describer=visual_describer,
        )
        chunks = self.chunker.chunk(parsed_chunks)
        embeddings = self.embedder.embed_documents([chunk.content for chunk in chunks])
        self.vector_store.upsert_chunks(chunks, embeddings)

        return IngestResponse(
            document_id=document_id,
            filename=filename,
            pages_processed=page_count,
            chunks_created=len(chunks),
            tables_extracted=table_count,
            visual_chunks_extracted=visual_count,
        )

    # ── Query ────────────────────────────────────────────────────────

    def query(self, document_id: str, question: str, top_k: int | None) -> QueryResponse:
        selected_top_k = top_k or self.settings.top_k_default
        retrieved = self.retriever.retrieve(document_id, question, selected_top_k)
        answer = self.answer_generator.answer(question, retrieved)
        sources = [
            SourceMetadata(
                chunk_id=str(chunk.get("chunk_id", "")),
                page=int((chunk.get("metadata", {}) or {}).get("page", 0)),
                type=str((chunk.get("metadata", {}) or {}).get("type", "")),
                score=chunk.get("score"),
                title=str((chunk.get("metadata", {}) or {}).get("title") or "") or None,
                excerpt=_excerpt(str(chunk.get("content", ""))),
            )
            for chunk in retrieved
        ]
        return QueryResponse(answer=answer, sources=sources)

    # ── Document management ──────────────────────────────────────────

    def list_documents(self) -> list[DocumentSummary]:
        return self.vector_store.list_documents()

    def get_chunks(self, document_id: str) -> list[DocumentChunk]:
        return self.vector_store.get_chunks(document_id)

    def delete_document(self, document_id: str) -> dict[str, str]:
        self.vector_store.delete_document(document_id)
        return {"document_id": document_id, "status": "deleted"}


@lru_cache
def get_pipeline() -> RAGPipeline:
    return RAGPipeline(get_settings())
