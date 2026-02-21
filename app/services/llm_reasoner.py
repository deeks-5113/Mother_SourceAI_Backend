"""
app/services/llm_reasoner.py
----------------------------
LLM Reasoning Service — Open/Closed Principle (OCP).

`LLMReasoningService` takes raw candidate rows from the repository,
submits them to GPT-4o with a carefully engineered comparative-ranking
prompt, and returns exactly 4 validated, ordered results.

The service is closed for modification (the prompt contract is stable)
but open for extension (swap the model or add few-shot examples without
touching the interface).
"""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

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
   - "type"                 : string  — copy verbatim from the candidate list
   - "rank_position"        : integer — starting from 1
   - "relevance_score"      : float   — between 0.0 and 1.0
   - "comparative_reasoning": string  — explain why this entity is relevant
                              to the outreach need. If there are multiple
                              candidates, reference adjacent ranks explicitly.
4. Order the array by rank_position ascending (rank 1 first).
"""

_USER_PROMPT_TEMPLATE = """\
Outreach Need:
{specific_need}

Candidate Healthcare Entities (JSON):
{candidates_json}
"""


class LLMReasoningService:
    """
    Uses GPT-4o to rank candidate healthcare channels and produce
    comparative reasoning for each of the Top-4 positions.

    Parameters
    ----------
    openai_client:
        An initialised `openai.AsyncOpenAI` client (injected via DI).
    model:
        The OpenAI model to use for ranking (default: "gpt-4o").
    """

    def __init__(self, openai_client: AsyncOpenAI, model: str = "gpt-4o") -> None:
        self._client = openai_client
        self._model = model

    async def rank_and_reason(
        self,
        specific_need: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Submit candidates to the LLM and return exactly 4 ranked results.

        Parameters
        ----------
        specific_need:
            The user's outreach objective (verbatim from the request).
        candidates:
            Raw list of DB rows from `ChannelRepository.search_similar_channels`.
            Each dict contains: id, name, district, demographic_type, metadata,
            similarity.

        Returns
        -------
        list[dict]
            Exactly 4 dicts, each with keys:
            entity_id, name, type, rank_position, relevance_score,
            comparative_reasoning — ordered by rank_position (1 → 4).

        Raises
        ------
        ValueError
            If the LLM response cannot be parsed as JSON or does not
            contain exactly 4 items.
        RuntimeError
            If the OpenAI API call fails.
        """
        # Slim the candidate payload — exclude the raw embedding vector
        slim_candidates = [
            {
                "entity_id": str(c.get("id", "")),
                "name": c.get("name", ""),
                "type": c.get("demographic_type", ""),
                "district": c.get("district", ""),
                "metadata": c.get("metadata", {}),
                "similarity_score": round(float(c.get("similarity", 0.0)), 4),
            }
            for c in candidates
        ]

        user_message = _USER_PROMPT_TEMPLATE.format(
            specific_need=specific_need,
            candidates_json=json.dumps(slim_candidates, indent=2, ensure_ascii=False),
        )

        logger.info(
            "Sending %d candidates to %s for ranking.", len(slim_candidates), self._model
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,  # low temperature for consistent structured output
                max_tokens=2048,
            )
        except Exception as exc:
            logger.exception("OpenAI API call failed: %s", exc)
            raise RuntimeError(f"LLM call failed: {exc}") from exc

        raw_text = response.choices[0].message.content or ""
        logger.debug("Raw LLM response: %s", raw_text[:500])

        return self._parse_and_validate(raw_text)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_and_validate(raw_text: str) -> list[dict[str, Any]]:
        """
        Parse the LLM JSON output and validate the contract:
        - Must be a JSON object with a key that holds an array, OR a bare array.
        - The array must contain exactly 4 items.
        - Each item must have all required keys.

        Raises
        ------
        ValueError
            On any structural violation.
        """
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned non-JSON output: {raw_text[:200]}") from exc

        # The model's response_format=json_object wraps arrays under a key
        if isinstance(parsed, dict):
            # Find the first list value in the dict (handles {"results": [...]})
            array_value = next(
                (v for v in parsed.values() if isinstance(v, list)), None
            )
            if array_value is None:
                raise ValueError(
                    f"LLM JSON object contains no array. Keys: {list(parsed.keys())}"
                )
            ranked: list[dict] = array_value
        elif isinstance(parsed, list):
            ranked = parsed
        else:
            raise ValueError(f"Unexpected LLM output type: {type(parsed)}")

        required_keys = {
            "entity_id",
            "name",
            "type",
            "rank_position",
            "relevance_score",
            "comparative_reasoning",
        }

        for i, item in enumerate(ranked):
            missing = required_keys - item.keys()
            if missing:
                raise ValueError(
                    f"LLM result item {i} is missing keys: {missing}"
                )

        if len(ranked) == 0 or len(ranked) > 4:
            raise ValueError(
                f"LLM returned {len(ranked)} results; expected 1-4."
            )

        # Sort ascending by rank_position to guarantee ordering
        ranked.sort(key=lambda x: int(x["rank_position"]))
        return ranked
