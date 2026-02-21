"""
app/core/settings.py
--------------------
Centralised, validated configuration via pydantic-settings.
A single source of truth for all environment variables.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the .env file (or OS environment)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Supabase
    supabase_url: str
    supabase_key: str

    # OpenAI
    openai_api_key: str

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # Model identifiers (override via .env if needed)
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 384
    llm_model: str = "gpt-4o"

    # Search tuning
    candidate_pool_size: int = 10   # rows retrieved from DB before LLM re-ranks
    top_k_results: int = 4          # final results returned to caller


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (reads .env once at startup)."""
    return Settings()  # type: ignore[call-arg]
