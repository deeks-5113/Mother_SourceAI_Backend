"""
modules/outreach_schemas.py
---------------------------
Pydantic models for Service 3: Smart Outreach Generator.

Supports multi-channel output (email, WhatsApp, phone script, LinkedIn,
concept note) and persona-driven personalization based on recipient role.

Isolated from Service 1 (schemas.py) and Service 2 (partner_schemas.py).
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────────────────────

class OutreachDraftRequest(BaseModel):
    """
    Payload for POST /api/v1/outreach/draft.

    Attributes
    ----------
    entity_id:
        UUID of the target entity in the Supabase `entities` table
        (hospital / healthcare channel to contact).
    pilot_description:
        Plain-text description of the maternal health pilot programme.
        Used by GPT-4o to contextualise the outreach message.
    sender_name:
        Name of the person or organisation sending the outreach.
    tone:
        Desired communication tone — warm or professional.
    channel:
        Target communication channel. Drives the output format:
        - email         → personalized professional email
        - whatsapp      → concise message with bullets & emojis
        - phone_script  → 30-second cold-call script with [Pause] cues
        - linkedin      → connection request (<300 chars) + follow-up DM
        - concept_note  → structured 1-page Markdown concept note
    recipient_name:
        Optional name of the person being contacted. Used to personalise
        the salutation (e.g. "Dear Dr. Reddy,").
    recipient_role:
        Role of the person being contacted. Drives the AI's psychological
        approach and vocabulary. Defaults to "Facility Administrator".
        Examples: "CSR Head", "Primary Medical Officer", "CMO", "ASHA Coordinator"
    """

    entity_id: str = Field(
        ...,
        description="UUID of the target entity in the `entities` table.",
    )
    pilot_description: str = Field(
        ...,
        min_length=10,
        description="Description of the maternal health pilot programme.",
        examples=["AI-driven maternal nutrition pilot for rural mothers"],
    )
    sender_name: str = Field(
        ...,
        min_length=2,
        description="Name of the sender / organisation.",
        examples=["MotherSource AI Team"],
    )
    tone: Literal["warm", "professional"] = Field(
        default="professional",
        description="Desired communication tone.",
    )
    channel: Literal[
        "email", "whatsapp", "phone_script", "linkedin", "concept_note"
    ] = Field(
        default="email",
        description="Target communication channel — shapes output format.",
    )
    recipient_name: Optional[str] = Field(
        default=None,
        description="Name of the recipient for personalised salutation.",
        examples=["Dr. Ravi Sharma"],
    )
    recipient_role: Optional[str] = Field(
        default="Facility Administrator",
        description="Role of the recipient — drives persona instructions.",
        examples=["CSR Head", "Primary Medical Officer", "CMO"],
    )


# ── Response ──────────────────────────────────────────────────────────

class OutreachDraftResponse(BaseModel):
    """
    GPT-4o generated outreach draft returned by Service 3.

    Attributes
    ----------
    subject_line:
        Subject line for email / LinkedIn. Empty string for channels
        where a subject is not applicable (WhatsApp, phone script).
    message_content:
        The main body of the outreach — format depends on `channel`:
        email body, WhatsApp message, call script, LinkedIn DMs,
        or a Markdown concept note.
    missing_variables:
        List of placeholders the LLM could not fill from entity data
        (e.g. ["Contact Person Name", "Budget Range"]).
    """

    subject_line: str = Field(
        ...,
        description=(
            "Email/LinkedIn subject line. Empty string for WhatsApp "
            "and phone_script channels."
        ),
    )
    message_content: str = Field(
        ...,
        description=(
            "Main outreach body — email, WhatsApp message, call script, "
            "LinkedIn request+DM, or Markdown concept note."
        ),
    )
    missing_variables: list[str] = Field(
        default_factory=list,
        description="Placeholders the LLM could not fill from entity data.",
    )
