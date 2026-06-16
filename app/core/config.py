from functools import lru_cache
from pathlib import Path

# pyrefly: ignore [missing-import]
from pydantic import Field
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "AI Engineer Intern Technical Test"
    app_version: str = "0.1.0"

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_generation_model: str = Field(
        default="gemini-3-flash-preview", alias="GEMINI_GENERATION_MODEL"
    )
    gemini_embedding_model: str = Field(
        default="gemini-embedding-2", alias="GEMINI_EMBEDDING_MODEL"
    )
    embedding_dim: int = Field(default=768, alias="EMBEDDING_DIM")

    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    chroma_collection: str = Field(
        default="bank_mandiri_multimodal_rag", alias="CHROMA_COLLECTION"
    )

    enable_visual_captioning: bool = Field(
        default=True, alias="ENABLE_VISUAL_CAPTIONING"
    )
    visual_caption_pages: str = Field(default="4,6,8,9", alias="VISUAL_CAPTION_PAGES")
    top_k_default: int = Field(default=5, alias="TOP_K_DEFAULT")
    max_chunk_chars: int = Field(default=1400, alias="MAX_CHUNK_CHARS")
    chunk_overlap_chars: int = Field(default=180, alias="CHUNK_OVERLAP_CHARS")
    local_fallback_embeddings: bool = Field(
        default=True, alias="LOCAL_FALLBACK_EMBEDDINGS"
    )

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def visual_caption_page_numbers(self) -> set[int] | None:
        value = self.visual_caption_pages.strip()
        if not value or value.lower() in {"all", "*"}:
            return None
        pages: set[int] = set()
        for item in value.split(","):
            item = item.strip()
            if item:
                pages.add(int(item))
        return pages

    def ensure_directories(self) -> None:
        for path in (self.raw_dir, self.processed_dir, self.chroma_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings

