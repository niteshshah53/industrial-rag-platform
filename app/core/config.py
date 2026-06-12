"""
Application configuration.

All settings are read from environment variables or a .env file.
Import the `get_settings` function and call it to access settings anywhere
in the application. The result is cached — settings are parsed once.

Usage:
    from app.core.config import get_settings

    settings = get_settings()
    print(settings.llm_model)
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration for the Industrial RAG Platform.

    Every field maps directly to an environment variable of the same name
    (case-insensitive). See .env.example for documentation on each variable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Extra env vars are silently ignored (don't raise errors for
        # variables set by Docker or CI that we don't care about).
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    log_format: str = "text"  # "json" in production

    # ── Ollama ────────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_collection_name: str = "documents"
    qdrant_distance_metric: str = "Cosine"

    # ── Chunking ──────────────────────────────────────────────────────────────
    # IMPORTANT: these are CHARACTER counts, not token counts.
    # RecursiveCharacterTextSplitter uses character-based splitting.
    # 1024 chars ≈ 256 tokens at ~4 chars/token.
    chunk_size_chars: int = 1024
    chunk_overlap_chars: int = 128

    # ── Retrieval ─────────────────────────────────────────────────────────────
    default_top_k: int = 5
    # score_threshold is a hyperparameter — tune via the evaluation pipeline.
    # 0.6 is a starting point for cosine similarity with nomic-embed-text.
    relevance_score_threshold: float = 0.6
    max_context_chars: int = 8192  # ≈ 2048 tokens

    # ── Embedding ─────────────────────────────────────────────────────────────
    embedding_batch_size: int = 32

    # ── Ingestion ─────────────────────────────────────────────────────────────
    max_upload_size_mb: int = 50
    upload_dir: str = "./uploads"
    ingestion_concurrency: int = 2

    # ── Derived properties ────────────────────────────────────────────────────

    @property
    def max_upload_size_bytes(self) -> int:
        """Upload size limit in bytes, derived from max_upload_size_mb."""
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        """True when running in production environment."""
        return self.app_env == "production"

    @property
    def qdrant_url(self) -> str:
        """Full Qdrant REST URL."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}, got '{v}'")
        return upper

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        valid = {"json", "text"}
        lower = v.lower()
        if lower not in valid:
            raise ValueError(f"log_format must be one of {valid}, got '{v}'")
        return lower

    @field_validator("qdrant_distance_metric")
    @classmethod
    def validate_distance_metric(cls, v: str) -> str:
        valid = {"Cosine", "Dot", "Euclidean"}
        if v not in valid:
            raise ValueError(f"qdrant_distance_metric must be one of {valid}, got '{v}'")
        return v

    @field_validator("relevance_score_threshold")
    @classmethod
    def validate_score_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"relevance_score_threshold must be between 0.0 and 1.0, got {v}")
        return v


@lru_cache
def get_settings() -> Settings:
    """
    Return the cached application settings instance.

    The settings are parsed once on first call and cached for the lifetime
    of the process. In tests, override with:

        app.dependency_overrides[get_settings] = lambda: test_settings
    """
    return Settings()
