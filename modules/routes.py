"""
modules/routes.py
-----------------
FastAPI router for Channel Search.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from openai import AsyncOpenAI
from supabase import Client

from .config import get_openai_client, get_supabase_client
from .schemas import (
    ChannelResponseItem,
    ChannelSearchRequest,
    ChannelSearchResponse,
    DistrictEntityItem,
)
from .services import ChannelService, DistrictEntityService

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


@router.get(
    "/district-entities",
    response_model=list[DistrictEntityItem],
    status_code=status.HTTP_200_OK,
    summary="List Mappable District Entities",
)
async def get_district_entities(
    district: str = Query(..., min_length=2, max_length=100),
    source_type: Literal["hospital", "phc", "medical_college"] | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=20000),
    supabase: Client = Depends(get_supabase_client),
) -> list[DistrictEntityItem]:
    """Returns all geocoded entities in a district for map layers."""
    service = DistrictEntityService(supabase_client=supabase)
    try:
        return await service.list_entities(
            district=district,
            source_type=source_type,
            limit=limit,
        )
    except RuntimeError as exc:
        logger.warning("Map data service error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error in district-entities: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred.",
        ) from exc
