"""
modules/partner_schemas.py
--------------------------
Pydantic models for Service 2: Funding & Partnership Scout.

Completely isolated from Service 1 (schemas.py) and Service 3
(outreach_schemas.py) models.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────────────────────

class PartnerSearchRequest(BaseModel):
    """
    Payload for POST /api/v1/partners/search.

    Attributes
    ----------
    target_region:
        City or region name to scope the NGO search.
        Matched against the `city` column via ILIKE — so "Tirupati"
        will match "Tirupati Region".
        Example: "Tirupati", "Kakinada", "Vijayawada"
    project_goal:
        Plain-text description of the maternal health initiative.
        Embedded and used for semantic search + LLM reasoning.
        Example: "AI-driven maternal nutrition pilot for rural mothers"
    """

    target_region: str = Field(
        ...,
        min_length=2,
        description="City or region to filter NGOs (matched via ILIKE).",
        examples=["Tirupati", "Kakinada", "Vijayawada"],
    )
    project_goal: str = Field(
        ...,
        min_length=10,
        description="Description of the maternal health project goal.",
        examples=["AI-driven maternal nutrition pilot for rural mothers"],
    )


# ── Response items ────────────────────────────────────────────────────

class PartnerResponseItem(BaseModel):
    """
    A single ranked NGO partner returned by Service 2.

    Attributes
    ----------
    ngo_id:
        UUID of the NGO row in the `ngos` table.
    title:
        NGO registration identifier (e.g. "Reg No: 1454 Of 1994").
    city:
        City / region this NGO operates in.
    rank_position:
        1-indexed rank (1 = strongest match).
    relevance_score:
        Cosine-similarity-inspired score between 0.0 and 1.0.
    inferred_capability:
        GPT-4o's inference of what specific operational or funding
        role this NGO can play, even if not explicitly stated.
    alignment_reasoning:
        GPT-4o's explanation of why this NGO's mission aligns with
        the supplied project_goal.
    """

    ngo_id: str = Field(..., description="UUID of the NGO in Supabase.")
    title: str = Field(..., description="Name or identifier of the partner/funder.")
    city: Optional[str] = Field(None, description="City / region the NGO operates in. null for global funders.")
    partner_type: Literal[
        "Global foundations",
        "AI for Social Good funds",
        "HNIs & philanthropists",
        "NGO",
        "Open grants"
    ] = Field(..., description="The specific classification of the partner.")
    rank_position: int = Field(..., ge=1, le=4, description="Rank (1 = best).")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Match score.")
    inferred_capability: str = Field(
        ..., description="Inferred operational or funding role for this project."
    )
    alignment_reasoning: str = Field(
        ..., description="A compelling explanation of WHY this specific partner/funder was chosen for the goal."
    )


# ── Response wrapper ──────────────────────────────────────────────────

class PartnerSearchResponse(BaseModel):
    """Top-4 ranked NGO partners for the given region and project goal."""

    results: list[PartnerResponseItem] = Field(
        ..., description="Ranked list of up to 4 NGO partners."
    )
