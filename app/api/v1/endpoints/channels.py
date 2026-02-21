"""
app/api/v1/endpoints/channels.py
---------------------------------
FastAPI router for Service 1 — Channel Search.

Responsibilities (router only):
  1. Accept and validate HTTP request.
  2. Instantiate `ChannelService` via injected dependencies.
  3. Call the service and return the result.
  4. Map domain exceptions to appropriate HTTP status codes.

Zero business logic lives here (Single Responsibility Principle).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI
from supabase import Client

from app.core.dependencies import get_openai_client, get_supabase_client
from app.schemas.channel import ChannelResponseItem, ChannelSearchRequest, ChannelSearchResponse
from app.services.channel_service import ChannelService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channels", tags=["Channels — Service 1"])


@router.post(
    "/search",
    response_model=ChannelSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Find Top-4 Healthcare Channels",
    description=(
        "Accepts a district, demographic type (rural/urban), and a free-text "
        "outreach need. Performs a hybrid pgvector similarity search against the "
        "Supabase `entities` table, then uses GPT-4o to select and comparatively "
        "rank the best 4 healthcare channels. Returns exactly 4 items, each with "
        "a `rank_position` (1–4), a `relevance_score`, and a `comparative_reasoning` "
        "that explicitly references the other ranked items."
    ),
)
async def search_channels(
    request: ChannelSearchRequest,
    supabase: Client = Depends(get_supabase_client),
    openai_client: AsyncOpenAI = Depends(get_openai_client),
) -> ChannelSearchResponse:
    """
    POST /api/v1/channels/search

    Returns the Top-4 healthcare channels ranked by the LLM.

    Raises
    ------
    HTTP 503 Service Unavailable
        When the database returns no matching rows, or when the
        OpenAI / Supabase API calls fail.
    HTTP 500 Internal Server Error
        For any unexpected unhandled exception (detail is NOT leaked).
    """
    service = ChannelService(
        supabase_client=supabase,
        openai_client=openai_client,
    )

    try:
        ranked_channels: list[ChannelResponseItem] = await service.find_top_channels(request)
    except RuntimeError as exc:
        # Expected domain failures: no DB rows, API connectivity issues
        logger.warning("Service error for request %s: %s", request.model_dump(), exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        # Structural failures: LLM returned malformed JSON
        logger.warning("LLM response validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI reasoning service returned an unexpected response: {exc}",
        ) from exc
    except Exception as exc:
        # Catch-all — log the real error, return generic 500
        logger.exception("Unexpected error in /channels/search: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred. Please try again.",
        ) from exc

    return ChannelSearchResponse(
        results=ranked_channels,
        district=request.district,
        demographic=request.demographic,
    )
