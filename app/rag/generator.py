"""LLM answer generation using LangChain LCEL chain + Gemini Vision interpreter.

The QA chain is built with LangChain's ChatPromptTemplate → ChatGoogleGenerativeAI
→ StrOutputParser, following the LCEL (LangChain Expression Language) pattern.

The vision interpreter remains a thin wrapper around the google-genai SDK because
LangChain's multimodal support is not needed for single-image page captioning.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings

logger = logging.getLogger(__name__)

# ── Prompt templates ─────────────────────────────────────────────────

QA_SYSTEM_PROMPT = (
    "Kamu adalah asisten QA dokumen untuk technical test AI Engineer.\n"
    "Jawab pertanyaan hanya berdasarkan context yang diberikan. Jika jawaban "
    "tidak tersedia di context, jawab: Tidak ditemukan dalam dokumen.\n"
    "Gunakan bahasa Indonesia yang ringkas dan faktual. Sertakan rujukan "
    "halaman di dalam jawaban bila relevan."
)

QA_HUMAN_TEMPLATE = (
    "Context:\n{context}\n\n"
    "Pertanyaan:\n{question}\n\n"
    "Jawaban:"
)

VISUAL_PROMPT_TEMPLATE = (
    "You are extracting searchable facts from a Bank Mandiri annual report "
    "PDF page image. Page number: {page_number}.\n"
    "Return concise Indonesian notes that preserve exact numbers, percentages, "
    "labels, table/chart names, process flow steps, contact channels, and any "
    "text inside infographics. If there is a chart or table, rewrite it as "
    "structured bullet points. Do not invent information."
)


# ── QA Answer Generator (LangChain LCEL) ─────────────────────────────

class LangChainQAGenerator:
    """Builds an LCEL chain: ChatPromptTemplate → ChatGoogleGenerativeAI → StrOutputParser."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._chain = None
        self._initialised = False

    def _ensure_init(self) -> None:
        if self._initialised:
            return
        self._initialised = True
        if not self.settings.gemini_api_key:
            logger.info("GEMINI_API_KEY not set; QA chain will use extractive fallback.")
            return
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=self.settings.gemini_generation_model,
                google_api_key=self.settings.gemini_api_key,
                temperature=0.1,
            )
            prompt = ChatPromptTemplate.from_messages([
                ("system", QA_SYSTEM_PROMPT),
                ("human", QA_HUMAN_TEMPLATE),
            ])
            self._chain = prompt | llm | StrOutputParser()
            logger.info(
                "LangChain QA chain initialised (model=%s).",
                self.settings.gemini_generation_model,
            )
        except Exception as exc:
            logger.warning("Failed to initialise LangChain QA chain: %s", exc)

    def answer(self, question: str, retrieved_chunks: list[dict[str, Any]]) -> str:
        if not retrieved_chunks:
            return "Tidak ditemukan dalam dokumen."

        context = self._format_context(retrieved_chunks)
        self._ensure_init()

        if self._chain is not None:
            try:
                result = self._chain.invoke({
                    "context": context,
                    "question": question,
                })
                return (result or "").strip() or "Tidak ditemukan dalam dokumen."
            except Exception as exc:
                logger.warning("LangChain QA chain failed: %s", exc)

        return self._fallback_answer(question, retrieved_chunks)

    @staticmethod
    def _format_context(retrieved_chunks: list[dict[str, Any]]) -> str:
        blocks: list[str] = []
        for index, chunk in enumerate(retrieved_chunks, start=1):
            metadata = chunk.get("metadata", {}) or {}
            content = str(chunk.get("content", ""))
            blocks.append(
                "[Source {index}] page={page} type={type} title={title} score={score}\n"
                "{content}".format(
                    index=index,
                    page=metadata.get("page", ""),
                    type=metadata.get("type", ""),
                    title=metadata.get("title", ""),
                    score=chunk.get("score", ""),
                    content=content,
                )
            )
        return "\n\n---\n\n".join(blocks)

    @staticmethod
    def _fallback_answer(
        question: str, retrieved_chunks: list[dict[str, Any]]
    ) -> str:
        best = retrieved_chunks[0]
        metadata = best.get("metadata", {}) or {}
        excerpt = str(best.get("content", "")).strip()
        if len(excerpt) > 900:
            excerpt = excerpt[:900].rsplit(" ", 1)[0] + "..."
        page = metadata.get("page", "tidak diketahui")
        return (
            "GEMINI_API_KEY belum tersedia, jadi sistem mengembalikan konteks "
            f"teratas secara ekstraktif. Pertanyaan: {question}\n\n"
            f"Sumber halaman {page}:\n{excerpt}"
        )


# ── Vision Interpreter (google-genai SDK) ────────────────────────────

class GeminiVisionInterpreter:
    """Describes a rendered PDF page image using Gemini Vision.

    Uses the google-genai SDK directly because single-image captioning is
    simpler than setting up a full LangChain multimodal chain.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not self.settings.gemini_api_key:
                return None
            from google import genai

            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def describe_image(self, image_path: Path, page_number: int) -> str:
        client = self.client
        if client is None:
            logger.info("GEMINI_API_KEY missing; visual captioning skipped.")
            return ""

        from PIL import Image

        image = Image.open(image_path)
        prompt = VISUAL_PROMPT_TEMPLATE.format(page_number=page_number)
        response = client.models.generate_content(
            model=self.settings.gemini_generation_model,
            contents=[image, prompt],
        )
        return (response.text or "").strip()
