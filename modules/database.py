"""
modules/database.py
-------------------
Data-access layer for Supabase interactions.
"""

import logging
from typing import Any, List
from supabase import Client

logger = logging.getLogger(__name__)

RawChannel = dict[str, Any]

class ChannelRepository:
    """Repository for the `entities` table in Supabase."""

    def __init__(self, supabase_client: Client) -> None:
        self._client = supabase_client

    def search_similar_channels(
        self,
        query_vector: List[float],
        district: str,
        environment: str,
        limit: int = 10,
    ) -> List[RawChannel]:
        """Call the Supabase `search_entities` RPC function."""
        logger.info(
            "Searching HRAG entities — district=%s, environment=%s, limit=%d",
            district, environment, limit,
        )

        response = self._client.rpc(
            "search_entities",
            {
                "query_embedding": query_vector,
                "filter_district": district,
                "filter_environment": environment,
                "match_count": limit,
            },
        ).execute()

        if response.data is None:
            raise RuntimeError("Supabase RPC 'search_entities' returned no data.")

        candidates: List[RawChannel] = response.data
        logger.info("Retrieved %d candidate chunk(s) from DB.", len(candidates))

        if not candidates:
            logger.warning(
                "No HRAG chunks found for district=%r and environment=%r.",
                district, environment
            )

        return candidates
