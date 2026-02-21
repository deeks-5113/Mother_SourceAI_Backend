"""
modules/config.py
-----------------
Consolidated configuration and dependency injection.
"""

import logging
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from fastapi import Depends
from openai import AsyncOpenAI
from supabase import Client, create_client

logger = logging.getLogger(__name__)

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
    embedding_dimensions: int = 1536
    llm_model: str = "gpt-4o"

    # Search tuning
    candidate_pool_size: int = 10   # rows retrieved from DB before LLM re-ranks
    top_k_results: int = 4          # final results returned to caller

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()  # type: ignore[call-arg]

# --- Dependencies ---

@lru_cache(maxsize=1)
def _create_supabase_client(url: str, key: str) -> Client:
    logger.info("Initialising Supabase client for URL: %s", url[:40])
    return create_client(url, key)

def get_supabase_client(
    settings: Settings = Depends(get_settings),
) -> Client:
    return _create_supabase_client(settings.supabase_url, settings.supabase_key)

@lru_cache(maxsize=1)
def _create_openai_client(api_key: str) -> AsyncOpenAI:
    logger.info("Initialising AsyncOpenAI client.")
    return AsyncOpenAI(api_key=api_key)

def get_openai_client(
    settings: Settings = Depends(get_settings),
) -> AsyncOpenAI:
    return _create_openai_client(settings.openai_api_key)
