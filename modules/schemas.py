"""
modules/schemas.py
------------------
Pydantic models for the Channel Search API.
"""

from typing import Optional, List
from pydantic import BaseModel, Field

class ChannelSearchRequest(BaseModel):
    """Request payload for the channel search."""
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
        examples=["Urban", "Rural", "General"],
        description="Environment/Demographic segment (Urban, Rural, or General).",
    )
    specific_need: str = Field(
        ...,
        min_length=5,
        max_length=500,
        examples=["maternal vaccination outreach for first-time mothers"],
        description="Free-text description of the healthcare outreach need.",
    )

class ChannelResponseItem(BaseModel):
    """A single ranked healthcare channel returned by the service."""
    entity_id: str = Field(..., description="UUID of the entity in Supabase.")
    name: str = Field(..., description="Title of the healthcare chunk/channel.")
    type: str = Field(..., description="Environment type (Urban/Rural/General).")
    content: Optional[str] = Field(None, description="The actual text content of the chunk.")
    semantic_summary: Optional[str] = Field(None, description="Semantic summary of the chunk's parent section.")
    rank_position: int = Field(..., ge=1, le=10, description="Rank within the result set.")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="LLM-assigned relevance score.")
    comparative_reasoning: str = Field(
        ...,
        description="Explanation of rank placement relative to the other top-4 results.",
    )

class ChannelSearchResponse(BaseModel):
    """Envelope wrapping the ordered list of top-4 channel results."""
    results: List[ChannelResponseItem] = Field(..., description="Top-4 ranked healthcare channels.")
    district: str
    demographic: str
