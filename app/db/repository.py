"""
app/db/repository.py
--------------------
Data-access layer — Single Responsibility Principle (SRP).

`ChannelRepository` owns ALL interactions with the Supabase `entities`
table. No business logic lives here; it only translates Python call
arguments into Supabase RPC invocations and returns raw results.
"""

import logging
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type alias for a raw DB row returned by the RPC function
# ---------------------------------------------------------------------------
RawChannel = dict[str, Any]


class ChannelRepository:
    """
    Repository for the `entities` table in Supabase.

    Parameters
    ----------
    supabase_client:
        An initialised `supabase.Client` instance (injected via DI).
    """

    def __init__(self, supabase_client: Client) -> None:
        self._client = supabase_client

    def search_similar_channels(
        self,
        query_vector: list[float],
        district: str,
        demographic: str,
        limit: int = 10,
    ) -> list[RawChannel]:
        """
        Call the Supabase `match_entities` RPC function to retrieve
        the most semantically similar healthcare channels for a given
        district and demographic type.

        The SQL function (which must exist in the DB) performs:
          1. Cosine-similarity ordering via pgvector (`<=>` operator).
          2. Pre-filtering on `district` and `demographic_type` columns.

        Parameters
        ----------
        query_vector:
            Dense embedding of the user's `specific_need` (dim=384).
        district:
            District name to filter on (exact match, case-sensitive in SQL).
        demographic:
            "rural" or "urban" — matched against the `demographic_type` column.
        limit:
            Maximum number of candidate rows to return (default 10).

        Returns
        -------
        list[RawChannel]
            List of dicts, each containing:
            ``id``, ``name``, ``district``, ``demographic_type``,
            ``metadata``, ``similarity``.

        Raises
        ------
        RuntimeError
            If the Supabase RPC call returns an error or no data.
        """
        logger.info(
            "Searching entities — district=%s, demographic=%s, limit=%d",
            district,
            demographic,
            limit,
        )

        response = self._client.rpc(
            "match_entities",
            {
                "query_embedding": query_vector,
                "filter_district": district,
                "filter_demographic": demographic,
                "match_count": limit,
            },
        ).execute()

        if response.data is None:
            raise RuntimeError(
                f"Supabase RPC 'match_entities' returned no data. "
                f"Check that the function exists and the filters are correct. "
                f"district={district!r}, demographic={demographic!r}"
            )

        candidates: list[RawChannel] = response.data
        logger.info("Retrieved %d candidate channel(s) from DB.", len(candidates))

        if not candidates:
            raise RuntimeError(
                f"No healthcare channels found for district={district!r} "
                f"and demographic={demographic!r}. "
                "Verify that the entities table has matching rows."
            )

        return candidates
