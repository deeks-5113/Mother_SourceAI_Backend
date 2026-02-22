"""
modules/services.py
-------------------
Business logic for healthcare channel ranking and reasoning.
"""

import json
import logging
from typing import Any, List, Dict
from openai import AsyncOpenAI
from supabase import Client

from .config import get_settings
from .database import ChannelRepository
from .schemas import ChannelResponseItem, ChannelSearchRequest

logger = logging.getLogger(__name__)

# --- LLM Reasoning Service ---

_SYSTEM_PROMPT = """\
You are a senior healthcare analyst supporting a maternal health outreach \
programme in India. Your task is to evaluate a list of candidate \
healthcare entities, select the best ones (up to 4), and rank them from \
1 (strongest match) downward.

RULES — read carefully:
1. You MUST return a JSON object with a key "results" containing an array.
2. The array MUST contain one object per candidate, UP TO a maximum of 4.
   If fewer than 4 candidates are provided, return only as many as given.
   NEVER duplicate or invent candidates.
3. Each object MUST have these fields (and only these fields):
   - "entity_id"            : string  — copy verbatim from the candidate list
   - "name"                 : string  — copy verbatim from the candidate list
   - "type"                 : string  — copy the "source_type" field verbatim
   - "rank_position"        : integer — starting from 1
   - "relevance_score"      : float   — between 0.0 and 1.0
   - "comparative_reasoning": string  — explain why this entity is relevant
                               to the outreach need. If there are multiple
                               candidates, reference adjacent ranks explicitly.
4. Order the array by rank_position ascending (rank 1 first).

DIVERSITY REQUIREMENT:
- Each candidate has a "source_type" field (hospital, phc, or medical_college).
- You MUST select exactly 2 hospitals, 1 PHC, and 1 medical college when all
  three types are available in the candidate pool.
- If a category has zero candidates, fill the gap from the most relevant
  remaining candidates of other types.
"""

_USER_PROMPT_TEMPLATE = """\
Outreach Need:
{specific_need}

Candidate Healthcare Entities (JSON):
{candidates_json}
"""

class LLMReasoningService:
    """Uses GPT-4o to rank candidate healthcare channels."""

    def __init__(self, openai_client: AsyncOpenAI, model: str = "gpt-4o") -> None:
        self._client = openai_client
        self._model = model

    async def rank_and_reason(
        self,
        specific_need: str,
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        slim_candidates = [
            {
                "entity_id": str(c.get("id", "")),
                "name": c.get("title", ""),
                "source_type": c.get("source_type", "hospital"),
                "content": c.get("content", ""),
                "semantic_summary": c.get("semantic_summary", ""),
                "district": c.get("district", ""),
                "similarity_score": round(float(c.get("similarity", 0.0)), 4),
            }
            for c in candidates
        ]

        user_message = _USER_PROMPT_TEMPLATE.format(
            specific_need=specific_need,
            candidates_json=json.dumps(slim_candidates, indent=2, ensure_ascii=False),
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
                max_tokens=2048,
            )
        except Exception as exc:
            logger.exception("OpenAI API call failed: %s", exc)
            raise RuntimeError(f"LLM call failed: {exc}") from exc

        raw_text = response.choices[0].message.content or ""
        return self._parse_and_validate(raw_text)

    @staticmethod
    def _parse_and_validate(raw_text: str) -> List[Dict[str, Any]]:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM returned non-JSON output.") from exc

        if isinstance(parsed, dict):
            array_value = next((v for v in parsed.values() if isinstance(v, list)), None)
            if array_value is None:
                raise ValueError("LLM JSON object contains no array.")
            ranked: List[Dict] = array_value
        elif isinstance(parsed, list):
            ranked = parsed
        else:
            raise ValueError("Unexpected LLM output type.")

        required_keys = {"entity_id", "name", "type", "rank_position", "relevance_score", "comparative_reasoning"}
        
        for item in ranked:
            if not required_keys.issubset(item.keys()):
                raise ValueError("LLM result item is missing keys.")

        if not (0 < len(ranked) <= 4):
            raise ValueError(f"LLM returned {len(ranked)} results; expected 1-4.")

        ranked.sort(key=lambda x: int(x["rank_position"]))
        return ranked

# --- Channel Service ---

class ChannelService:
    """Orchestrates the end-to-end flow for finding and ranking channels."""

    def __init__(self, supabase_client: Client, openai_client: AsyncOpenAI) -> None:
        _settings = get_settings()
        self._settings = _settings
        self._repository = ChannelRepository(supabase_client)
        self._llm_service = LLMReasoningService(
            openai_client=openai_client,
            model=_settings.llm_model,
        )
        self._openai = openai_client

    async def find_top_channels(self, request: ChannelSearchRequest) -> List[ChannelResponseItem]:
        query_vector = await self._embed_text(request.specific_need)

        # --- Diversified search: 3 typed queries ---
        # Fetch candidates per source type to ensure the LLM has a diverse pool
        type_quotas = {
            "hospital": 4,          # fetch more so LLM can pick best 2
            "phc": 2,
            "medical_college": 2,
        }

        all_candidates: List[Dict[str, Any]] = []
        for source_type, limit in type_quotas.items():
            try:
                typed_hits = await self._repository.search_by_district_and_type(
                    query_vector=query_vector,
                    district=request.district,
                    source_type=source_type,
                    limit=limit,
                )
                all_candidates.extend(typed_hits)
            except Exception as exc:
                logger.warning(
                    "Typed search failed for source_type=%s: %s — falling back.",
                    source_type, exc,
                )

        # Fallback: if no typed results at all, use the regular district search
        if not all_candidates:
            logger.info(
                "No typed candidates found; falling back to district-only search for district=%r.",
                request.district,
            )
            all_candidates = await self._repository.search_by_district(
                query_vector=query_vector,
                district=request.district,
                limit=self._settings.candidate_pool_size,
            )

        if not all_candidates:
            logger.info("No candidates found in DB for district=%r; skipping LLM ranking.", request.district)
            return []

        # Log the composition of the candidate pool
        type_counts = {}
        for c in all_candidates:
            st = c.get("source_type", "unknown")
            type_counts[st] = type_counts.get(st, 0) + 1
        logger.info("Candidate pool composition: %s", type_counts)

        ranked_raw = await self._llm_service.rank_and_reason(
            specific_need=request.specific_need,
            candidates=all_candidates,
        )

        results = []
        candidate_map = {str(c["id"]): c for c in all_candidates}
        
        for item in ranked_raw:
            entity_id = str(item["entity_id"])
            db_row = candidate_map.get(entity_id, {})
            
            results.append(
                ChannelResponseItem(
                    entity_id=entity_id,
                    name=item["name"],
                    type=item.get("type", db_row.get("source_type", "hospital")),
                    content=db_row.get("content"),
                    semantic_summary=db_row.get("semantic_summary"),
                    rank_position=int(item["rank_position"]),
                    relevance_score=float(item["relevance_score"]),
                    comparative_reasoning=item["comparative_reasoning"],
                )
            )

        return results

    async def _embed_text(self, text: str) -> List[float]:
        try:
            response = await self._openai.embeddings.create(
                model=self._settings.embedding_model,
                input=text,
                dimensions=self._settings.embedding_dimensions,
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.exception("Embedding API call failed: %s", exc)
            raise RuntimeError(f"Embedding failed: {exc}") from exc
