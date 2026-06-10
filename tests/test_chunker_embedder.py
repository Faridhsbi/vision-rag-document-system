import math

from app.core.config import Settings
from app.rag.chunker import DocumentChunker
from app.rag.embedder import GeminiEmbedder
from app.rag.schemas import DocumentChunk


def test_chunker_preserves_page_and_parent_metadata(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        max_chunk_chars=80,
        chunk_overlap_chars=10,
        local_fallback_embeddings=True,
    )
    chunker = DocumentChunker(settings)
    document = DocumentChunk(
        id="doc_page_001_text",
        document_id="doc",
        page=1,
        type="text",
        source="doc.pdf",
        content="Kalimat panjang. " * 30,
    )

    chunks = chunker.chunk([document])

    assert len(chunks) > 1
    assert all(chunk.page == 1 for chunk in chunks)
    assert all(chunk.document_id == "doc" for chunk in chunks)
    assert chunks[0].metadata["parent_chunk_id"] == "doc_page_001_text"


def test_fallback_embedding_has_requested_dimension_and_norm(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        gemini_api_key=None,
        embedding_dim=32,
        local_fallback_embeddings=True,
    )
    embedder = GeminiEmbedder(settings)

    embedding = embedder.embed_query("penagihan jam 21.00")

    assert len(embedding) == 32
    norm = math.sqrt(sum(value * value for value in embedding))
    assert 0.99 <= norm <= 1.01


def test_embed_documents_returns_list_of_vectors(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        gemini_api_key=None,
        embedding_dim=16,
        local_fallback_embeddings=True,
    )
    embedder = GeminiEmbedder(settings)

    vectors = embedder.embed_documents(["hello world", "penagihan jam 21"])

    assert len(vectors) == 2
    assert all(len(v) == 16 for v in vectors)
