"""
modules/database.py
-------------------
Data-access layer for Supabase interactions.
"""

import logging
from typing import Any, Dict, List
from supabase import Client

logger = logging.getLogger(__name__)

RawChannel = dict[str, Any]

class ChannelRepository:
    """Repository for the `entities` table in Supabase."""

    def __init__(self, supabase_client: Client) -> None:
        self._client = supabase_client

    def search_by_district(
        self,
        query_vector: List[float],
        district: str,
        limit: int = 10,
    ) -> List[RawChannel]:
        """Call the `search_entities_by_district` RPC — filters by district only,
        then ranks by semantic similarity."""
        logger.info(
            "Searching HRAG entities — district=%s, limit=%d",
            district, limit,
        )

        response = self._client.rpc(
            "search_entities_by_district",
            {
                "query_embedding": query_vector,
                "filter_district": district,
                "match_count": limit,
            },
        ).execute()

        if response.data is None:
            raise RuntimeError("Supabase RPC 'search_entities_by_district' returned no data.")

        candidates: List[RawChannel] = response.data
        logger.info("Retrieved %d candidate chunk(s) from DB.", len(candidates))

        if not candidates:
            logger.warning(
                "No HRAG chunks found for district=%r.",
                district,
            )

        return candidates

    # Legacy method kept for backward compatibility
    def search_similar_channels(
        self,
        query_vector: List[float],
        district: str,
        environment: str,
        limit: int = 10,
    ) -> List[RawChannel]:
        """Call the Supabase `search_entities` RPC function (filters district + environment)."""
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

    # -------------------------------------------------------------------------
    # Service 3 — fetch a single entity by primary key
    # -------------------------------------------------------------------------
    async def get_entity_by_id(self, entity_id: str) -> Dict[str, Any]:
        """
        Fetch a single row from the `entities` table by UUID.

        Raises
        ------
        ValueError
            If no entity with the given ID exists (router maps this to HTTP 404).
        RuntimeError
            If the Supabase call itself fails (router maps this to HTTP 503).
        """
        logger.info("Fetching entity by id=%s", entity_id)
        try:
            response = (
                self._client.table("entities")
                .select("*")
                .eq("id", entity_id)
                .single()
                .execute()
            )
        except Exception as exc:
            # .single() raises PostgREST APIError when 0 rows match
            error_msg = str(exc).lower()
            if "no rows" in error_msg or "406" in error_msg or "pgrst116" in error_msg:
                raise ValueError(f"Entity with id='{entity_id}' not found.") from exc
            raise RuntimeError(f"Supabase query failed: {exc}") from exc

        if response.data is None:
            raise ValueError(f"Entity with id='{entity_id}' not found.")

        logger.info("Fetched entity: %s", response.data.get("title", entity_id))
        return response.data
