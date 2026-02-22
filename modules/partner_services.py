"""
modules/partner_services.py
---------------------------
Business logic for Service 2: Funding & Partnership Scout.

Two classes following SRP:
  - PartnerLLMReasoner  — GPT-4o layer (ranking & reasoning)
  - PartnerService      — Orchestration layer (embed → search → LLM → map)

Completely isolated from services.py (Service 1) and
outreach_services.py (Service 3).
"""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from modules.ngo_repository import NgoRepository, RawNgo
from modules.partner_schemas import (
    PartnerResponseItem,
    PartnerSearchRequest,
    PartnerSearchResponse,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Layer 1 — LLM Reasoning  (GPT-4o)
# ═══════════════════════════════════════════════════════════════════════

class PartnerLLMReasoner:
    """
    Wraps GPT-4o to evaluate NGO candidates against a project goal.

    Given up to 10 raw DB candidates, it selects the best 4 and
    returns `inferred_capability` and `alignment_reasoning` for each.
    """

    _SYSTEM_PROMPT = """\
You are a Strategic Grant & Partnership Evaluator supporting a maternal \
health AI programme in India. Your task is to analyse candidate partners \
and funders and identify the most mission-aligned entities.

RULES — read carefully:
1. Return a JSON object with a single key "results" containing an array.
2. The array MUST contain exactly the best 1–4 candidates.
3. Each object in the array MUST have these fields:
   - "ngo_id"               : string  — UUID, copy verbatim from candidates
   - "title"                : string  — name of the partner/funder
   - "city"                 : string or null — if location is "Global", return null. Otherwise, return the city.
   - "partner_type"         : string  — MUST be one of: "Global foundations", "AI for Social Good funds", "HNIs & philanthropists", "NGO", "Open grants".
   - "rank_position"        : integer — 1 (best) to 4
   - "relevance_score"      : float   — 0.0 to 1.0
   - "inferred_capability"  : string  — specific operational or funding role.
   - "alignment_reasoning"  : string  — A compelling, unique explanation of WHY this specific partner was selected over others for THIS project goal.
4. Classification Logic:
   - Classify as "NGO" only if they are clearly a local implementation body.
   - Classify as "Open grants" if they are bilateral/multilateral agencies (e.g., USAID).
   - Classify as "Global foundations" for large independent global philanthropy (e.g., Wellcome Trust).
   - Classify as "AI for Social Good funds" for corporate or tech-focused impact funds (e.g., Microsoft AI, Nvidia).
   - Classify as "HNIs & philanthropists" for family/industrial trusts (e.g., Tata, Reliance).
5. Do NOT add any fields beyond those listed above.
"""

    def __init__(self, openai_client: AsyncOpenAI, model: str = "gpt-4o") -> None:
        self._client = openai_client
        self._model = model

    def _build_candidate_block(self, candidates: list[RawNgo]) -> str:
        """
        Format raw DB rows into a numbered candidate list for the LLM prompt.

        Handles both NGO rows (title/content) and funder rows (name/description).
        """
        lines: list[str] = []
        for i, c in enumerate(candidates, start=1):
            # NGO rows use 'title'+'content'; funder rows use 'name'+'description'
            display_name = c.get('title') or c.get('name', 'Unknown')
            body_text = c.get('content') or c.get('description', 'N/A')
            city = c.get('city', 'N/A')
            lines.append(
                f"[{i}] ngo_id={c['id']}\n"
                f"    title={display_name}\n"
                f"    city={city}\n"
                f"    content={body_text}\n"
            )
        return "\n".join(lines)

    def _parse_and_validate(self, raw_json: str) -> list[dict[str, Any]]:
        """
        Parse GPT-4o JSON output and validate it contains 1–4 results
        with all required keys.

        Raises
        ------
        ValueError
            If the JSON is malformed or violates the schema rules.
        """
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

        results = parsed.get("results")
        if not isinstance(results, list):
            raise ValueError("LLM JSON missing 'results' array.")

        if not (0 < len(results) <= 4):
            raise ValueError(
                f"LLM returned {len(results)} results; expected 1–4."
            )

        required_keys = {
            "ngo_id", "title", "city", "partner_type", "rank_position",
            "relevance_score", "inferred_capability", "alignment_reasoning",
        }
        for item in results:
            missing = required_keys - item.keys()
            if missing:
                raise ValueError(f"LLM result missing keys: {missing}")

        return sorted(results, key=lambda x: x["rank_position"])

    async def rank_and_reason(
        self,
        project_goal: str,
        candidates: list[RawNgo],
    ) -> list[dict[str, Any]]:
        """
        Send candidates to GPT-4o and return the ranked, reasoned list.

        Parameters
        ----------
        project_goal:
            Plain-text description of the maternal health initiative.
        candidates:
            Raw NGO rows from the Supabase `ngos` table (up to 10).

        Returns
        -------
        list[dict]
            Validated list of 1–4 ranked candidate dicts.

        Raises
        ------
        RuntimeError
            If the OpenAI API call fails or returns unusable output.
        ValueError
            If LLM output fails validation.
        """
        candidate_block = self._build_candidate_block(candidates)
        user_message = (
            f"Project Goal: {project_goal}\n\n"
            f"NGO Candidates:\n{candidate_block}\n\n"
            "Evaluate the candidates above and return the best 1–4 as "
            "a JSON object following the system rules exactly."
        )

        logger.info(
            "Calling GPT-4o for partner ranking — %d candidates, goal=%r",
            len(candidates),
            project_goal[:80],
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=0.3,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI API call failed: {exc}") from exc

        raw_json = response.choices[0].message.content or ""
        logger.debug("GPT-4o raw output: %s", raw_json[:300])

        return self._parse_and_validate(raw_json)


# ═══════════════════════════════════════════════════════════════════════
# Layer 2 — Orchestration
# ═══════════════════════════════════════════════════════════════════════

class PartnerService:
    """
    Orchestrates the full Service 2 pipeline:
      1. Embed `project_goal` via OpenAI
      2. Retrieve candidate NGOs + Funders from Supabase
      3. Merge & deduplicate candidates
      4. Rank & reason with GPT-4o (via PartnerLLMReasoner)
      5. Map to PartnerSearchResponse
    """

    def __init__(
        self,
        ngo_repository: NgoRepository,
        llm_reasoner: PartnerLLMReasoner,
        openai_client: AsyncOpenAI,
        embedding_model: str = "text-embedding-3-small",
        embedding_dimensions: int = 1536,
        candidate_pool_size: int = 10,
    ) -> None:
        self._repo = ngo_repository
        self._llm = llm_reasoner
        self._openai = openai_client
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._pool_size = candidate_pool_size

    async def _embed_text(self, text: str) -> list[float]:
        """Generate an OpenAI embedding for the given text."""
        try:
            response = await self._openai.embeddings.create(
                model=self._embedding_model,
                input=[text.replace("\n", " ")],
                dimensions=self._embedding_dimensions,
            )
            return response.data[0].embedding
        except Exception as exc:
            raise RuntimeError(
                f"Embedding generation failed: {exc}"
            ) from exc

    def _merge_candidates(
        self,
        ngo_candidates: list[RawNgo],
        funder_candidates: list[RawNgo],
    ) -> list[RawNgo]:
        """
        Merge NGO and funder candidates, deduplicate by ID,
        and return the combined pool (up to pool_size * 2).
        """
        seen_ids: set[str] = set()
        merged: list[RawNgo] = []

        for candidate in ngo_candidates + funder_candidates:
            cid = str(candidate.get("id", ""))
            if cid not in seen_ids:
                seen_ids.add(cid)
                merged.append(candidate)

        logger.info(
            "Merged candidates — %d NGO(s) + %d funder(s) = %d unique.",
            len(ngo_candidates),
            len(funder_candidates),
            len(merged),
        )
        return merged

    async def find_top_partners(
        self, request: PartnerSearchRequest
    ) -> PartnerSearchResponse:
        """
        Full pipeline: embed → search NGOs + funders → merge → LLM rank → response.

        Parameters
        ----------
        request:
            Validated PartnerSearchRequest with target_region and project_goal.

        Returns
        -------
        PartnerSearchResponse
            Contains up to 4 ranked PartnerResponseItem objects.

        Raises
        ------
        ValueError
            If no candidates found across both tables.
        RuntimeError
            If embedding, DB search, or LLM call fails.
        """
        logger.info(
            "Service 2 pipeline — region=%r, goal=%r",
            request.target_region,
            request.project_goal[:80],
        )

        # Step 1 — Embed the project goal
        query_vector = await self._embed_text(request.project_goal)

        # Step 2 — Retrieve candidates from BOTH tables
        ngo_candidates = self._repo.match_ngos_by_region(
            query_vector=query_vector,
            region=request.target_region,
            limit=self._pool_size,
        )

        funder_candidates: list[RawNgo] = []
        try:
            funder_candidates = self._repo.match_funders_by_region(
                query_vector=query_vector,
                region=request.target_region,
                limit=self._pool_size,
            )
        except RuntimeError as exc:
            # Funders table might not exist yet — degrade gracefully
            logger.warning("Funder search failed (non-fatal): %s", exc)

        # Step 3 — Merge & deduplicate
        candidates = self._merge_candidates(ngo_candidates, funder_candidates)

        if not candidates:
            raise ValueError(
                f"No partners or funders found for region='{request.target_region}'. "
                "Please try a different city name."
            )

        logger.info(
            "Total %d candidate(s) for region=%r.",
            len(candidates),
            request.target_region,
        )

        # Step 4 — LLM ranking and reasoning
        ranked_raw = await self._llm.rank_and_reason(
            project_goal=request.project_goal,
            candidates=candidates,
        )

        # Step 5 — Map to Pydantic models
        results = [
            PartnerResponseItem(
                ngo_id=item["ngo_id"],
                title=item["title"],
                city=item.get("city"),  # Optional now
                partner_type=item["partner_type"],
                rank_position=item["rank_position"],
                relevance_score=item["relevance_score"],
                inferred_capability=item["inferred_capability"],
                alignment_reasoning=item["alignment_reasoning"],
            )
            for item in ranked_raw
        ]

        logger.info(
            "Service 2 complete — returning %d ranked partner(s).",
            len(results),
        )
        return PartnerSearchResponse(results=results)
