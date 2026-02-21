"""
modules/partner_routes.py
--------------------------
FastAPI router for Service 2: Funding & Partnership Scout.

Endpoint: POST /api/v1/partners/search

Completely isolated from routes.py (Service 1) and
outreach_routes.py (Service 3).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from supabase import Client

from modules.config import get_settings, get_supabase_client, get_openai_client
from modules.ngo_repository import NgoRepository
from modules.partner_schemas import PartnerSearchRequest, PartnerSearchResponse
from modules.partner_services import PartnerLLMReasoner, PartnerService

logger = logging.getLogger(__name__)

partner_router = APIRouter(tags=["Service 2 — Funding & Partnership Scout"])


# ── Dependency factories ──────────────────────────────────────────────

def get_partner_service(
    supabase: Client = Depends(get_supabase_client),
    openai_client: AsyncOpenAI = Depends(get_openai_client),
) -> PartnerService:
    """Build and return a fully wired PartnerService instance."""
    settings = get_settings()
    ngo_repo = NgoRepository(supabase)
    llm_reasoner = PartnerLLMReasoner(openai_client)
    return PartnerService(
        ngo_repository=ngo_repo,
        llm_reasoner=llm_reasoner,
        openai_client=openai_client,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        candidate_pool_size=settings.candidate_pool_size,
    )


# ── Route ─────────────────────────────────────────────────────────────

@partner_router.post(
    "/partners/search",
    response_model=PartnerSearchResponse,
    summary="Find Top-4 NGO Partners & Funders",
    description=(
        "Accepts a target region (city name) and a project goal. "
        "Performs semantic search on the HRAG `ngos` table, then uses "
        "GPT-4o to rank the best 4 partners with inferred capabilities "
        "and mission-alignment reasoning."
    ),
)
async def search_partners(
    request: PartnerSearchRequest,
    service: PartnerService = Depends(get_partner_service),
) -> PartnerSearchResponse:
    """
    POST /api/v1/partners/search

    Returns up to 4 ranked NGO partners for the given region and goal.

    Raises
    ------
    422 Unprocessable Entity — invalid request body (Pydantic validation)
    404 Not Found           — no NGOs found for the given region
    503 Service Unavailable — OpenAI API or Supabase failure
    """
    logger.info(
        "POST /partners/search — region=%r, goal=%r",
        request.target_region,
        request.project_goal[:80],
    )

    try:
        return await service.find_top_partners(request)

    except ValueError as exc:
        # No NGOs found for region, or LLM output validation failed
        logger.warning("ValueError in /partners/search: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except RuntimeError as exc:
        # OpenAI or Supabase infrastructure failure
        logger.error("RuntimeError in /partners/search: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable. Please try again.",
        ) from exc
