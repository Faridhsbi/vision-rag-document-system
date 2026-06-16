"""LangChain-compatible retriever wrapping the vector store.

Implements LangChain's BaseRetriever so the component can be used in
any LangChain chain or agent if needed in the future.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.rag.embedder import GeminiEmbedder
from app.rag.vector_store import ChromaVectorStore


class DocumentRetriever(BaseRetriever):
    """Vector similarity retriever that filters by document_id.

    Wraps the custom ChromaVectorStore and GeminiEmbedder to provide both
    the LangChain Retriever interface and a raw ``retrieve()`` method that
    returns dicts with scores (used by the QA pipeline).
    """

    embedder: Any  # GeminiEmbedder (typed as Any for Pydantic v2 compat)
    vector_store: Any  # ChromaVectorStore
    document_id: str = ""
    top_k: int = 5

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # ── LangChain Retriever interface ────────────────────────────────

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        raw = self.retrieve(self.document_id, query, self.top_k)
        return [
            Document(
                page_content=item.get("content", ""),
                metadata=item.get("metadata", {}),
            )
            for item in raw
        ]

    # ── Raw dict interface (used by pipeline) ────────────────────────

    def retrieve(
        self, document_id: str, question: str, top_k: int
    ) -> list[dict[str, object]]:
        embedding = self.embedder.embed_query(question)
        return self.vector_store.query(
            document_id=document_id,
            query_embedding=embedding,
            top_k=top_k,
        )
