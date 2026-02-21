"""
app/schemas/channel.py
----------------------
Pydantic models for the Channel Search API (Service 1).

- ChannelSearchRequest  : inbound request body
- ChannelResponseItem   : single ranked result (1 of 4)
- ChannelSearchResponse : full response envelope
"""

from typing import Optional

from pydantic import BaseModel, Field


class ChannelSearchRequest(BaseModel):
    """
    Request payload for the POST /api/v1/channels/search endpoint.

    Attributes
    ----------
    district:
        Name of the Telangana district to search within (e.g. "Hyderabad").
    demographic:
        Target population segment — must be either "rural" or "urban".
    specific_need:
        Free-text description of the outreach objective
        (e.g. "maternal vaccination outreach for first-time mothers").
    """

    district: str = Field(
        ...,
        min_length=2,
        max_length=100,
        examples=["Hyderabad"],
        description="Target district name (case-insensitive match against DB).",
    )
    demographic: str = Field(
        ...,
        min_length=2,
        max_length=100,
        examples=["Women", "rural", "urban"],
        description="Demographic segment to filter by (must match demographic_type in DB).",
    )
    specific_need: str = Field(
        ...,
        min_length=5,
        max_length=500,
        examples=["maternal vaccination outreach for first-time mothers"],
        description="Free-text description of the healthcare outreach need.",
    )


class ChannelResponseItem(BaseModel):
    """
    A single ranked healthcare channel returned by the service.

    Attributes
    ----------
    entity_id:
        UUID of the entity row in Supabase.
    name:
        Human-readable name of the healthcare facility / centre.
    type:
        Demographic type as stored in DB — "rural" or "urban".
    rank_position:
        Final rank assigned by the LLM (1 = best match, 4 = lowest of top 4).
    relevance_score:
        Float between 0.0 and 1.0 representing match strength.
    comparative_reasoning:
        Narrative from the LLM explaining WHY this specific rank was assigned
        relative to the other items (e.g. "Ranked #1 because …; better than
        #2 because …").
    """

    entity_id: str = Field(..., description="UUID of the entity in Supabase.")
    name: str = Field(..., description="Name of the healthcare channel.")
    type: str = Field(..., description="Demographic type (rural/urban).")
    rank_position: int = Field(
        ..., ge=1, le=10, description="Rank within the result set."
    )
    relevance_score: float = Field(
        ..., ge=0.0, le=1.0, description="LLM-assigned relevance score."
    )
    comparative_reasoning: str = Field(
        ...,
        description=(
            "Explanation of rank placement relative to the other top-4 results."
        ),
    )


class ChannelSearchResponse(BaseModel):
    """
    Envelope wrapping the ordered list of top-4 channel results.

    Attributes
    ----------
    results:
        Exactly 4 ChannelResponseItem objects ordered by rank_position (1→4).
    district:
        Echo of the requested district.
    demographic:
        Echo of the requested demographic filter.
    """

    results: list[ChannelResponseItem] = Field(
        ..., description="Top-4 ranked healthcare channels."
    )
    district: str
    demographic: str
