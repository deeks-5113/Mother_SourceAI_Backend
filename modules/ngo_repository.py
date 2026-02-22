"""
modules/ngo_repository.py
-------------------------
Data-access layer for the `ngos` table in Supabase.
Kept separate from database.py (ChannelRepository) to maintain SRP.
"""

import logging
from typing import Any, Dict, List

from supabase import Client

logger = logging.getLogger(__name__)

RawNgo = Dict[str, Any]


class NgoRepository:
    """Repository for the `ngos` table in Supabase."""

    def __init__(self, supabase_client: Client) -> None:
        self._client = supabase_client

    # ------------------------------------------------------------------
    # Semantic search — used by outreach / matching services
    # ------------------------------------------------------------------

    def search_similar_ngos(
        self,
        query_vector: List[float],
        city: str,
        limit: int = 10,
    ) -> List[RawNgo]:
        """
        Call the Supabase `search_ngos` RPC function.
        Returns up to `limit` NGOs ranked by cosine similarity.

        Raises
        ------
        RuntimeError
            If the Supabase RPC call fails or returns no data object.
        """
        logger.info(
            "Searching NGOs — city=%s, limit=%d", city, limit
        )

        response = self._client.rpc(
            "search_ngos",
            {
                "query_embedding": query_vector,
                "filter_city": city,
                "match_count": limit,
            },
        ).execute()

        if response.data is None:
            raise RuntimeError("Supabase RPC 'search_ngos' returned no data.")

        results: List[RawNgo] = response.data
        logger.info("Retrieved %d NGO(s) from DB.", len(results))

        if not results:
            logger.warning("No NGOs found for city=%r.", city)

        return results

    def match_ngos_by_region(
        self,
        query_vector: List[float],
        region: str,
        limit: int = 10,
    ) -> List[RawNgo]:
        """
        Call the Supabase `match_ngos` RPC function (Service 2).

        Uses ILIKE matching on the `city` column so partial names work:
        e.g. "Tirupati" matches rows with city="Tirupati Region".

        Parameters
        ----------
        query_vector:
            1536-dim embedding of the project goal.
        region:
            Target region string — matched via ILIKE on `city`.
        limit:
            Maximum number of candidates to return (default 10).

        Returns
        -------
        List[RawNgo]
            Up to `limit` NGO rows ordered by cosine similarity.

        Raises
        ------
        RuntimeError
            If the Supabase RPC call fails.
        """
        logger.info(
            "Matching NGOs by region — region=%r, limit=%d", region, limit
        )

        response = self._client.rpc(
            "match_ngos",
            {
                "query_embedding": query_vector,
                "filter_region": region,
                "match_count": limit,
            },
        ).execute()

        if response.data is None:
            raise RuntimeError("Supabase RPC 'match_ngos' returned no data.")

        results: List[RawNgo] = response.data
        logger.info(
            "match_ngos_by_region — retrieved %d NGO(s) for region=%r.",
            len(results),
            region,
        )
        return results

    def match_funders_by_region(
        self,
        query_vector: List[float],
        region: str,
        limit: int = 10,
    ) -> List[RawNgo]:
        """
        Call the Supabase `match_funders` RPC function (Service 2).

        Returns both city-matched funders AND global funders
        (city='Global') for any region query.

        Parameters
        ----------
        query_vector:
            1536-dim embedding of the project goal.
        region:
            Target region string — matched via ILIKE on `city`,
            plus all Global funders automatically included.
        limit:
            Maximum number of candidates to return (default 10).

        Returns
        -------
        List[RawNgo]
            Up to `limit` funder rows ordered by cosine similarity.

        Raises
        ------
        RuntimeError
            If the Supabase RPC call fails.
        """
        logger.info(
            "Matching funders by region — region=%r, limit=%d", region, limit
        )

        response = self._client.rpc(
            "match_funders",
            {
                "query_embedding": query_vector,
                "filter_region": region,
                "match_count": limit,
            },
        ).execute()

        if response.data is None:
            raise RuntimeError("Supabase RPC 'match_funders' returned no data.")

        results: List[RawNgo] = response.data
        logger.info(
            "match_funders_by_region — retrieved %d funder(s) for region=%r.",
            len(results),
            region,
        )
        return results


    # ------------------------------------------------------------------
    # Point lookup — used by Service 3 outreach drafting
    # ------------------------------------------------------------------

    async def get_ngo_by_id(self, ngo_id: str) -> RawNgo:
        """
        Fetch a single NGO row by UUID.

        Raises
        ------
        ValueError
            If no NGO with the given ID exists (router maps to HTTP 404).
        RuntimeError
            If the Supabase query itself fails (router maps to HTTP 503).
        """
        logger.info("Fetching NGO by id=%s", ngo_id)
        try:
            response = (
                self._client.table("ngos")
                .select("*")
                .eq("id", ngo_id)
                .single()
                .execute()
            )
        except Exception as exc:
            error_msg = str(exc).lower()
            if "no rows" in error_msg or "406" in error_msg or "pgrst116" in error_msg:
                raise ValueError(f"NGO with id='{ngo_id}' not found.") from exc
            raise RuntimeError(f"Supabase query failed: {exc}") from exc

        if response.data is None:
            raise ValueError(f"NGO with id='{ngo_id}' not found.")

        logger.info("Fetched NGO: %s", response.data.get("title", ngo_id))
        return response.data

    # ------------------------------------------------------------------
    # Write — used by ingest_ngos.py
    # ------------------------------------------------------------------

    def upsert_ngo(self, record: RawNgo) -> None:
        """
        Insert or update an NGO record (upsert on `id`).
        Expects the record to include the `embedding` field.

        Raises
        ------
        RuntimeError
            If the upsert fails.
        """
        try:
            self._client.table("ngos").upsert(record, on_conflict="id").execute()
            logger.info("Upserted NGO: %s", record.get("name", record.get("id")))
        except Exception as exc:
            logger.exception("Failed to upsert NGO: %s", exc)
            raise RuntimeError(f"NGO upsert failed: {exc}") from exc
