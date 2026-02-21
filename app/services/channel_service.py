"""
app/services/channel_service.py
--------------------------------
Channel Service — orchestrator (Interface Segregation + DIP).

`ChannelService` wires together the embedding step, the repository
search, and the LLM ranking. It owns NO DB or AI library calls
directly — those are delegated to injected collaborators.
"""

import logging

from openai import AsyncOpenAI
from supabase import Client

from app.core.settings import get_settings
from app.db.repository import ChannelRepository
from app.schemas.channel import ChannelResponseItem, ChannelSearchRequest
from app.services.llm_reasoner import LLMReasoningService

logger = logging.getLogger(__name__)


class ChannelService:
    """
    Orchestrates the end-to-end flow for finding and ranking the
    Top-4 healthcare channels for a given outreach request.

    Parameters
    ----------
    supabase_client:
        Injected Supabase client (from `get_supabase_client`).
    openai_client:
        Injected AsyncOpenAI client (from `get_openai_client`).
    """

    def __init__(self, supabase_client: Client, openai_client: AsyncOpenAI) -> None:
        _settings = get_settings()          # deferred — evaluated after .env is loaded
        self._settings = _settings
        self._repository = ChannelRepository(supabase_client)
        self._llm_service = LLMReasoningService(
            openai_client=openai_client,
            model=_settings.llm_model,
        )
        self._openai = openai_client

    async def find_top_channels(
        self, request: ChannelSearchRequest
    ) -> list[ChannelResponseItem]:
        """
        Full pipeline: embed → vector search → LLM rank → Pydantic map.

        Parameters
        ----------
        request:
            Validated inbound request containing district, demographic,
            and specific_need.

        Returns
        -------
        list[ChannelResponseItem]
            Exactly 4 items ordered by rank_position (1 → 4).

        Raises
        ------
        RuntimeError
            Propagated from the repository (no DB results) or LLM service.
        ValueError
            Propagated from the LLM service (malformed response).
        """
        # ── Step A: Embed the user's specific_need ────────────────────────
        logger.info(
            "Embedding specific_need for district=%r, demographic=%r",
            request.district,
            request.demographic,
        )
        query_vector = await self._embed_text(request.specific_need)

        # ── Step B: Retrieve candidate channels from Supabase ─────────────
        candidates = self._repository.search_similar_channels(
            query_vector=query_vector,
            district=request.district,
            demographic=request.demographic,
            limit=self._settings.candidate_pool_size,
        )

        # ── Step C: Ask LLM to rank and explain the Top 4 ─────────────────
        ranked_raw = await self._llm_service.rank_and_reason(
            specific_need=request.specific_need,
            candidates=candidates,
        )

        # ── Step D: Map raw dicts → validated Pydantic models ─────────────
        results = [
            ChannelResponseItem(
                entity_id=item["entity_id"],
                name=item["name"],
                type=item["type"],
                rank_position=int(item["rank_position"]),
                relevance_score=float(item["relevance_score"]),
                comparative_reasoning=item["comparative_reasoning"],
            )
            for item in ranked_raw
        ]

        logger.info(
            "Returning %d ranked channel(s) for request.", len(results)
        )
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _embed_text(self, text: str) -> list[float]:
        """
        Call the OpenAI Embeddings API and return the dense vector.

        Parameters
        ----------
        text:
            The string to embed.

        Returns
        -------
        list[float]
            A vector of length `embedding_dimensions` (384 by default).

        Raises
        ------
        RuntimeError
            If the API call fails.
        """
        try:
            response = await self._openai.embeddings.create(
                model=self._settings.embedding_model,
                input=text,
                dimensions=self._settings.embedding_dimensions,
            )
            vector: list[float] = response.data[0].embedding
            logger.debug(
                "Embedding generated — model=%s, dims=%d",
                self._settings.embedding_model,
                len(vector),
            )
            return vector
        except Exception as exc:
            logger.exception("Embedding API call failed: %s", exc)
            raise RuntimeError(f"Embedding failed: {exc}") from exc
