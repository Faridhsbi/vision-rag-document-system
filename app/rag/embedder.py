"""Embedding provider using LangChain's GoogleGenerativeAIEmbeddings.

Falls back to a deterministic hash-based local embedder when no API key
is configured (useful for offline development and unit testing).
"""

import hashlib
import logging
import math
import re

from langchain_core.embeddings import Embeddings

from app.core.config import Settings

logger = logging.getLogger(__name__)


class GeminiEmbedder(Embeddings):
    """LangChain-compatible embedder backed by Gemini or a local fallback."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._langchain_embedder: Embeddings | None = None
        self._initialised = False

    def _ensure_init(self) -> None:
        if self._initialised:
            return
        self._initialised = True
        if not self.settings.gemini_api_key:
            logger.info("GEMINI_API_KEY not set; using local fallback embeddings.")
            return
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            self._langchain_embedder = GoogleGenerativeAIEmbeddings(
                model=f"models/{self.settings.gemini_embedding_model}",
                google_api_key=self.settings.gemini_api_key,
            )
            logger.info(
                "Gemini embeddings initialised (model=%s).",
                self.settings.gemini_embedding_model,
            )
        except Exception as exc:
            logger.warning("Failed to initialise Gemini embeddings: %s", exc)

    # ── LangChain Embeddings interface ───────────────────────────────

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._ensure_init()
        if self._langchain_embedder is not None:
            try:
                return self._langchain_embedder.embed_documents(texts)
            except Exception as exc:
                if not self.settings.local_fallback_embeddings:
                    raise
                logger.warning("Gemini embed_documents failed; falling back: %s", exc)
        return [self._fallback_embedding(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self._ensure_init()
        if self._langchain_embedder is not None:
            try:
                return self._langchain_embedder.embed_query(text)
            except Exception as exc:
                if not self.settings.local_fallback_embeddings:
                    raise
                logger.warning("Gemini embed_query failed; falling back: %s", exc)
        return self._fallback_embedding(text)

    # ── Local deterministic fallback ─────────────────────────────────

    def _fallback_embedding(self, text: str) -> list[float]:
        if not self.settings.local_fallback_embeddings:
            raise RuntimeError(
                "GEMINI_API_KEY is missing and LOCAL_FALLBACK_EMBEDDINGS=false."
            )

        dimension = self.settings.embedding_dim
        vector = [0.0] * dimension
        tokens = re.findall(r"[\w%.,@+-]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimension
            sign = 1.0 if digest[4] % 2 else -1.0
            weight = 1.0 + (digest[5] % 7) / 10.0
            vector[index] += sign * weight

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]
