"""
modules/dispatch_routes.py
--------------------------
FastAPI router for Service 4: Dispatch Brainstorm.
Mounted in main.py under prefix /api/v1.
"""

import logging
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI
from supabase import Client

from .config import get_openai_client, get_supabase_client, get_settings
from .dispatch_schemas import (
    DispatchChatRequest,
    DispatchChatResponse,
    DispatchCreateRequest,
    DispatchCreateResponse,
    DispatchSessionResponse,
)
from .dispatch_services import DispatchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dispatch", tags=["Dispatch Brainstorm"])


def _build_service(
    supabase: Client = Depends(get_supabase_client),
    openai_client: AsyncOpenAI = Depends(get_openai_client),
) -> DispatchService:
    settings = get_settings()
    return DispatchService(
        supabase_client=supabase,
        openai_client=openai_client,
        model=settings.llm_model,
    )


# ── Create Session ────────────────────────────────────────────────────

@router.post(
    "/create",
    response_model=DispatchCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Dispatch Brainstorm Session",
    description=(
        "Creates a new brainstorm session seeded with the outreach draft "
        "context. Returns a session ID and an AI-generated opening message."
    ),
)
async def create_dispatch_session(
    request: DispatchCreateRequest,
    service: DispatchService = Depends(_build_service),
) -> DispatchCreateResponse:
    try:
        return await service.create_session(request)
    except RuntimeError as exc:
        logger.warning("Failed to create dispatch session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error creating dispatch session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred.",
        ) from exc


# ── Chat ──────────────────────────────────────────────────────────────

@router.post(
    "/{session_id}/chat",
    response_model=DispatchChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a Brainstorm Message",
    description="Send a message in an existing session and receive an AI reply.",
)
async def dispatch_chat(
    session_id: str,
    request: DispatchChatRequest,
    service: DispatchService = Depends(_build_service),
) -> DispatchChatResponse:
    try:
        return await service.chat(session_id, request.message)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.warning("Chat error for session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected chat error for session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred.",
        ) from exc


# ── Get Session (Resume) ─────────────────────────────────────────────

@router.get(
    "/{session_id}",
    response_model=DispatchSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a Brainstorm Session",
    description="Fetch a session with its full conversation history to resume brainstorming.",
)
async def get_dispatch_session(
    session_id: str,
    service: DispatchService = Depends(_build_service),
) -> DispatchSessionResponse:
    try:
        return service.get_session(session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ── Delete Session ────────────────────────────────────────────────────

@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Brainstorm Session",
    description="Permanently delete a brainstorm thread.",
)
async def delete_dispatch_session(
    session_id: str,
    service: DispatchService = Depends(_build_service),
) -> None:
    try:
        service.delete_session(session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ── List Sessions ─────────────────────────────────────────────────────

@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    summary="List All Brainstorm Sessions",
    description="Returns all dispatch sessions (summary view for the Outreach section).",
)
async def list_dispatch_sessions(
    service: DispatchService = Depends(_build_service),
) -> List[Dict[str, Any]]:
    return service.list_sessions()
