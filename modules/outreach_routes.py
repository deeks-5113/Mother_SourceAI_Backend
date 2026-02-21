"""
modules/outreach_routes.py
--------------------------
FastAPI router for Service 3: Smart Outreach Generator.
Mounted in main.py under prefix /api/v1.
Completely independent of Service 1 routes.py.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI
from supabase import Client

from .config import get_openai_client, get_supabase_client, get_settings
from .database import ChannelRepository
from .outreach_schemas import OutreachDraftRequest, OutreachDraftResponse
from .outreach_services import OutreachDraftingService, OutreachOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outreach", tags=["Outreach"])


@router.post(
    "/draft",
    response_model=OutreachDraftResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Multi-Channel Personalised Outreach Draft",
    description=(
        "Given a healthcare entity ID, pilot description, channel, and recipient "
        "role, fetches entity context from Supabase and uses GPT-4o to draft a "
        "personalised outreach in the specified channel format and persona tone."
    ),
)
async def draft_outreach(
    request: OutreachDraftRequest,
    supabase: Client = Depends(get_supabase_client),
    openai_client: AsyncOpenAI = Depends(get_openai_client),
) -> OutreachDraftResponse:
    """
    Returns a personalised outreach draft adapted to channel and recipient role.

    Error mapping:
    - ValueError  → 404 (entity not found in DB)
    - RuntimeError → 503 (Supabase or OpenAI API failure)
    - Exception   → 500 (unexpected internal error)
    """
    settings = get_settings()
    repository = ChannelRepository(supabase)
    drafting_service = OutreachDraftingService(
        openai_client=openai_client,
        model=settings.llm_model,
    )
    orchestrator = OutreachOrchestrator(
        repository=repository,
        drafting_service=drafting_service,
    )

    try:
        return await orchestrator.generate_draft(request)

    except ValueError as exc:
        logger.warning("Entity not found: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        logger.warning("External service error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Unexpected error in outreach draft: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred.",
        ) from exc
