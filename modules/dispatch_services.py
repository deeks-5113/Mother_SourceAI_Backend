"""
modules/dispatch_services.py
------------------------------
Business logic for Service 4: Dispatch Brainstorm.

Manages persistent brainstorm sessions backed by Supabase and GPT-4o.
Sessions are pre-seeded with the outreach draft context so the team
can immediately start planning strategy.
"""

import json
import logging
from typing import Any, Dict, List

from openai import AsyncOpenAI
from supabase import Client

from .dispatch_schemas import (
    ChatMessage,
    DispatchChatResponse,
    DispatchCreateRequest,
    DispatchCreateResponse,
    DispatchSessionResponse,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# System prompt for the brainstorm assistant
# ═══════════════════════════════════════════════════════════════════════
_SYSTEM_PROMPT = """\
You are an expert outreach strategy advisor for MotherSource AI, \
a maternal healthcare initiative in India.

You are embedded in a brainstorm session. The team has already:
1. Identified a healthcare entity to partner with.
2. Generated an outreach draft for that entity.

Your job is to help the team **plan, refine, and brainstorm** their \
outreach strategy. Be collaborative, suggest improvements, anticipate \
questions the recipient might have, propose follow-up actions, and \
help the team think through logistics.

Keep responses concise, actionable, and structured with bullet points \
where appropriate. Ask clarifying questions when the team's intent is unclear.
"""


class DispatchService:
    """Manages brainstorm sessions: create, chat, resume, delete."""

    def __init__(
        self,
        supabase_client: Client,
        openai_client: AsyncOpenAI,
        model: str = "gpt-4o",
    ) -> None:
        self._db = supabase_client
        self._llm = openai_client
        self._model = model

    # ── Create Session ────────────────────────────────────────────────

    async def create_session(
        self, request: DispatchCreateRequest
    ) -> DispatchCreateResponse:
        """Insert a new session and generate a seed message from GPT-4o."""

        outreach_draft = {
            "subject": request.outreach_subject,
            "body": request.outreach_body,
        }

        # Build a seed prompt that summarises the outreach context
        context_summary = (
            f"Entity: {request.entity_name}\n"
            f"Channel: {request.channel}\n"
            f"Pilot: {request.pilot_description}\n"
            f"Draft subject: {request.outreach_subject}\n"
            f"Draft body:\n{request.outreach_body}"
        )

        seed_user_msg = (
            "Here is the outreach draft we just generated. "
            "Please summarise what we have so far and suggest how the team "
            "should approach the next steps for this outreach strategy."
        )

        # Call GPT-4o for the seed message
        completion = await self._llm.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "system", "content": f"--- OUTREACH CONTEXT ---\n{context_summary}"},
                {"role": "user", "content": seed_user_msg},
            ],
            temperature=0.7,
            max_tokens=800,
        )
        seed_reply = completion.choices[0].message.content or ""

        # Persist to Supabase
        messages: List[Dict[str, str]] = [
            {"role": "user", "content": seed_user_msg},
            {"role": "assistant", "content": seed_reply},
        ]

        row = {
            "entity_id": request.entity_id,
            "entity_name": request.entity_name,
            "pilot_description": request.pilot_description,
            "channel": request.channel,
            "outreach_draft": json.dumps(outreach_draft),
            "messages": json.dumps(messages),
        }

        response = self._db.table("dispatch_sessions").insert(row).execute()

        if not response.data:
            raise RuntimeError("Failed to create dispatch session in Supabase.")

        session_id = response.data[0]["id"]
        logger.info("Created dispatch session %s for entity %s", session_id, request.entity_name)

        return DispatchCreateResponse(
            session_id=session_id,
            seed_message=seed_reply,
        )

    # ── Chat ──────────────────────────────────────────────────────────

    async def chat(
        self, session_id: str, user_message: str
    ) -> DispatchChatResponse:
        """Append a user message, call GPT-4o, append the reply, persist."""

        # Load session
        session = self._fetch_session(session_id)
        outreach_draft = session["outreach_draft"]
        if isinstance(outreach_draft, str):
            outreach_draft = json.loads(outreach_draft)

        messages_history: List[Dict[str, str]] = session["messages"]
        if isinstance(messages_history, str):
            messages_history = json.loads(messages_history)

        # Build context summary from session metadata
        context_summary = (
            f"Entity: {session['entity_name']}\n"
            f"Channel: {session['channel']}\n"
            f"Pilot: {session['pilot_description']}\n"
            f"Draft subject: {outreach_draft.get('subject', '')}\n"
            f"Draft body:\n{outreach_draft.get('body', '')}"
        )

        # Build LLM message list
        llm_messages: List[Dict[str, str]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "system", "content": f"--- OUTREACH CONTEXT ---\n{context_summary}"},
        ]
        # Add conversation history
        for msg in messages_history:
            llm_messages.append({"role": msg["role"], "content": msg["content"]})
        # Add new user message
        llm_messages.append({"role": "user", "content": user_message})

        # Call GPT-4o
        completion = await self._llm.chat.completions.create(
            model=self._model,
            messages=llm_messages,
            temperature=0.7,
            max_tokens=800,
        )
        reply = completion.choices[0].message.content or ""

        # Append both messages to history
        messages_history.append({"role": "user", "content": user_message})
        messages_history.append({"role": "assistant", "content": reply})

        # Persist updated history
        self._db.table("dispatch_sessions").update(
            {"messages": json.dumps(messages_history)}
        ).eq("id", session_id).execute()

        logger.info("Chat turn completed for session %s", session_id)

        return DispatchChatResponse(session_id=session_id, reply=reply)

    # ── Get Session (Resume) ─────────────────────────────────────────

    def get_session(self, session_id: str) -> DispatchSessionResponse:
        """Retrieve a full session for resuming the brainstorm."""
        session = self._fetch_session(session_id)

        outreach_draft = session["outreach_draft"]
        if isinstance(outreach_draft, str):
            outreach_draft = json.loads(outreach_draft)

        messages_raw = session["messages"]
        if isinstance(messages_raw, str):
            messages_raw = json.loads(messages_raw)

        return DispatchSessionResponse(
            session_id=session["id"],
            entity_id=session["entity_id"],
            entity_name=session["entity_name"],
            pilot_description=session["pilot_description"],
            channel=session["channel"],
            outreach_draft=outreach_draft,
            messages=[ChatMessage(**m) for m in messages_raw],
            created_at=session["created_at"],
            updated_at=session["updated_at"],
        )

    # ── Delete Session ────────────────────────────────────────────────

    def delete_session(self, session_id: str) -> None:
        """Delete a brainstorm thread permanently."""
        # Verify it exists first
        self._fetch_session(session_id)

        self._db.table("dispatch_sessions").delete().eq("id", session_id).execute()
        logger.info("Deleted dispatch session %s", session_id)

    # ── List Sessions ─────────────────────────────────────────────────

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return all dispatch sessions (summary view for the Outreach section)."""
        response = (
            self._db.table("dispatch_sessions")
            .select("id, entity_id, entity_name, channel, created_at, updated_at")
            .order("updated_at", desc=True)
            .execute()
        )
        return response.data or []

    # ── Private helpers ───────────────────────────────────────────────

    def _fetch_session(self, session_id: str) -> Dict[str, Any]:
        """Fetch a single session row or raise ValueError."""
        response = (
            self._db.table("dispatch_sessions")
            .select("*")
            .eq("id", session_id)
            .execute()
        )
        if not response.data:
            raise ValueError(f"Dispatch session '{session_id}' not found.")
        return response.data[0]
