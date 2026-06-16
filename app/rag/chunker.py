from app.core.config import Settings
from app.rag.schemas import DocumentChunk


def _fallback_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


class DocumentChunker:
    def __init__(self, settings: Settings):
        self.settings = settings
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            self.splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.max_chunk_chars,
                chunk_overlap=settings.chunk_overlap_chars,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
        except ImportError:
            self.splitter = None

    def chunk(self, documents: list[DocumentChunk]) -> list[DocumentChunk]:
        chunked: list[DocumentChunk] = []
        for document in documents:
            if document.type in {"table", "visual", "chart", "image_caption"}:
                chunked.append(document)
                continue

            parts = self._split(document.content)
            if len(parts) == 1:
                chunked.append(document)
                continue

            for index, part in enumerate(parts, start=1):
                chunked.append(
                    document.model_copy(
                        update={
                            "id": f"{document.id}_part_{index:02d}",
                            "content": part,
                            "metadata": {
                                **document.metadata,
                                "parent_chunk_id": document.id,
                                "chunk_part": index,
                            },
                        }
                    )
                )
        return chunked

    def _split(self, text: str) -> list[str]:
        if self.splitter is not None:
            return [chunk.strip() for chunk in self.splitter.split_text(text) if chunk.strip()]
        return _fallback_split(
            text=text,
            chunk_size=self.settings.max_chunk_chars,
            overlap=self.settings.chunk_overlap_chars,
        )

