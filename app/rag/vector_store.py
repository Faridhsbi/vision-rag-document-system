import json
from collections import defaultdict
from typing import Any

from app.core.config import Settings
from app.rag.schemas import DocumentChunk, DocumentSummary


def _metadata_value(value: Any) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def chunk_to_metadata(chunk: DocumentChunk) -> dict[str, str | int | float | bool]:
    metadata: dict[str, str | int | float | bool] = {
        "document_id": chunk.document_id,
        "page": chunk.page,
        "type": chunk.type,
        "source": chunk.source,
        "title": chunk.title or "",
    }
    for key, value in chunk.metadata.items():
        metadata[key] = _metadata_value(value)
    return metadata


class ChromaVectorStore:
    def __init__(self, settings: Settings):
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("chromadb is required for vector storage.") from exc

        settings.ensure_directories()
        self.client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(
        self, chunks: list[DocumentChunk], embeddings: list[list[float]]
    ) -> None:
        if not chunks:
            return
        self.delete_document(chunks[0].document_id)
        self.collection.add(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.content for chunk in chunks],
            metadatas=[chunk_to_metadata(chunk) for chunk in chunks],
            embeddings=embeddings,
        )

    def query(
        self,
        document_id: str,
        query_embedding: list[float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"document_id": document_id},
            include=["documents", "metadatas", "distances"],
        )

        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        retrieved: list[dict[str, Any]] = []
        for chunk_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            score = 1.0 - float(distance) if distance is not None else None
            retrieved.append(
                {
                    "chunk_id": chunk_id,
                    "content": document,
                    "metadata": metadata or {},
                    "score": score,
                }
            )
        return retrieved

    def list_documents(self) -> list[DocumentSummary]:
        records = self.collection.get(include=["metadatas"])
        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"filename": None, "chunks": 0, "pages": set()}
        )

        for metadata in records.get("metadatas", []):
            if not metadata:
                continue
            document_id = str(metadata.get("document_id", ""))
            if not document_id:
                continue
            grouped[document_id]["filename"] = metadata.get("source")
            grouped[document_id]["chunks"] += 1
            grouped[document_id]["pages"].add(int(metadata.get("page", 0)))

        return [
            DocumentSummary(
                document_id=document_id,
                filename=data["filename"],
                chunks=data["chunks"],
                pages=sorted(page for page in data["pages"] if page),
            )
            for document_id, data in sorted(grouped.items())
        ]

    def get_chunks(self, document_id: str) -> list[DocumentChunk]:
        records = self.collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
        chunks: list[DocumentChunk] = []
        for chunk_id, content, metadata in zip(
            records.get("ids", []),
            records.get("documents", []),
            records.get("metadatas", []),
            strict=False,
        ):
            metadata = metadata or {}
            reserved = {"document_id", "page", "type", "source", "title"}
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    document_id=str(metadata.get("document_id", document_id)),
                    page=int(metadata.get("page", 0)),
                    type=metadata.get("type", "text"),
                    source=str(metadata.get("source", "")),
                    title=str(metadata.get("title") or "") or None,
                    content=content or "",
                    metadata={k: v for k, v in metadata.items() if k not in reserved},
                )
            )
        return chunks

    def delete_document(self, document_id: str) -> None:
        try:
            self.collection.delete(where={"document_id": document_id})
        except Exception:
            records = self.collection.get(where={"document_id": document_id})
            ids = records.get("ids", [])
            if ids:
                self.collection.delete(ids=ids)

