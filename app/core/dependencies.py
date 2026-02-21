"""
app/core/dependencies.py
------------------------
FastAPI dependency injection providers for external clients.

Implements the Dependency Inversion Principle (DIP):
  - Business logic layers receive injected clients rather than
    reading environment variables themselves.

Clients are cached at module level to avoid re-initialising
on every request (connection-pool friendly).
"""

import logging
from functools import lru_cache

from fastapi import Depends
from openai import AsyncOpenAI
from supabase import Client, create_client

from app.core.settings import get_settings, Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _create_supabase_client(url: str, key: str) -> Client:
    """Internal cached factory — never call this directly from route handlers."""
    logger.info("Initialising Supabase client for URL: %s", url[:40])
    return create_client(url, key)


def get_supabase_client(
    settings: Settings = Depends(get_settings),
) -> Client:
    """
    FastAPI dependency that returns a singleton Supabase client.

    Usage
    -----
    ::

        @router.post("/search")
        async def search(supabase: Client = Depends(get_supabase_client)):
            ...
    """
    return _create_supabase_client(settings.supabase_url, settings.supabase_key)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _create_openai_client(api_key: str) -> AsyncOpenAI:
    """Internal cached factory — never call this directly from route handlers."""
    logger.info("Initialising AsyncOpenAI client.")
    return AsyncOpenAI(api_key=api_key)


def get_openai_client(
    settings: Settings = Depends(get_settings),
) -> AsyncOpenAI:
    """
    FastAPI dependency that returns a singleton AsyncOpenAI client.

    Usage
    -----
    ::

        @router.post("/search")
        async def search(openai: AsyncOpenAI = Depends(get_openai_client)):
            ...
    """
    return _create_openai_client(settings.openai_api_key)
