"""
modules/routes.py
-----------------
FastAPI router for Channel Search.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI
from supabase import Client

from .config import get_openai_client, get_supabase_client
from .schemas import ChannelSearchRequest, ChannelSearchResponse, ChannelResponseItem
from .services import ChannelService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channels", tags=["Channels"])

@router.post(
    "/search",
    response_model=ChannelSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Find Top-4 Healthcare Channels",
)
async def search_channels(
    request: ChannelSearchRequest,
    supabase: Client = Depends(get_supabase_client),
    openai_client: AsyncOpenAI = Depends(get_openai_client),
) -> ChannelSearchResponse:
    """Returns the Top-4 healthcare channels ranked by the LLM."""
    service = ChannelService(
        supabase_client=supabase,
        openai_client=openai_client,
    )

    try:
        ranked_channels: list[ChannelResponseItem] = await service.find_top_channels(request)
    except RuntimeError as exc:
        logger.warning("Service error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred.",
        ) from exc

    return ChannelSearchResponse(
        results=ranked_channels,
        district=request.district,
        demographic=request.demographic,
    )
