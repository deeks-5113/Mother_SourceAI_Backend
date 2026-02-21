"""
modules/outreach_services.py
-----------------------------
Business logic for Service 3: Smart Outreach Generator.

Supports multi-channel output (email, WhatsApp, phone script, LinkedIn,
concept note) with persona-driven personalization based on recipient role.

Two classes following SRP:
  - OutreachDraftingService  — GPT-4o layer (prompt construction + LLM call)
  - OutreachOrchestrator     — Orchestration layer (fetch entity → draft → return)

Isolated from services.py (Service 1) and partner_services.py (Service 2).
"""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from modules.database import ChannelRepository
from modules.outreach_schemas import OutreachDraftRequest, OutreachDraftResponse

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Layer 1 — LLM Drafting  (GPT-4o)
# ═══════════════════════════════════════════════════════════════════════

class OutreachDraftingService:
    """
    Wraps GPT-4o to generate a persona-adapted, channel-specific
    outreach draft for a given healthcare entity.

    Persona and channel instructions are resolved from internal
    dictionaries and injected dynamically into the system prompt.
    """

    # ── Persona instructions — keyed by lowercase keyword fragments ───
    # Matched against recipient_role via substring search (first match wins).
    _PERSONA_INSTRUCTIONS: dict[str, str] = {
        # Clinical / Hospital decision-makers
        "cmo":              (
            "You are addressing a Chief Medical Officer at a hospital. "
            "Focus on patient outcomes, high-risk ANC referral pathways, "
            "reduction in maternal mortality indicators, and clinical efficiency. "
            "Use clinical terminology where appropriate and cite evidence-based impact."
        ),
        "ob-gyn":           (
            "You are addressing a Head of Obstetrics & Gynaecology. "
            "Focus on antenatal care protocols, high-risk pregnancy identification, "
            "and how this pilot integrates with existing OB-GYN workflows."
        ),
        "medical college":  (
            "You are addressing a Medical College administrator. "
            "Focus on academic collaboration, research opportunities, training for "
            "residents, and the pilot's potential for peer-reviewed publication."
        ),
        "medical officer":  (
            "You are addressing a Medical Officer at a secondary-care facility. "
            "Emphasise clinical outcomes, referral pathway improvement, and reduced "
            "burden on emergency obstetric services."
        ),
        # Grassroots / PHC tier
        "primary":          (
            "You are addressing a Primary Health Centre officer. "
            "Focus on reducing the daily workload of frontline workers, strengthening "
            "community trust, and making maternal health support reach the last mile. "
            "Use simple, jargon-free language."
        ),
        "asha":             (
            "You are addressing an ASHA Coordinator or Community Health Worker lead. "
            "Focus on empowering frontline workers, reducing paperwork, improving "
            "community outreach efficiency, and building grassroots health resilience."
        ),
        "grassroots":       (
            "You are addressing a grassroots health organisation leader. "
            "Focus on community impact, local trust, and how the pilot strengthens "
            "existing community-based health delivery."
        ),
        # Corporate / CSR / Funder tier
        "csr":              (
            "You are addressing a Corporate CSR Head or sustainability officer. "
            "Focus on scalable social impact, ESG goal alignment, health equity metrics, "
            "and how this pilot generates measurable ROI on social investment. "
            "Reference SDG 3 (Good Health) and SDG 5 (Gender Equality)."
        ),
        "funder":           (
            "You are addressing a grant funder or impact investor. "
            "Focus on the funding gap, evidence-based model, scalability roadmap, "
            "and expected outcomes per rupee invested."
        ),
        "corporate":        (
            "You are addressing a corporate executive. "
            "Focus on brand positioning, employee engagement, scalable health impact, "
            "and alignment with the company's ESG commitments."
        ),
        # NGO / Partnership tier
        "ngo":              (
            "You are addressing an NGO leader or programme director. "
            "Focus on shared mission, complementary strengths, co-implementation "
            "opportunities, and how collaboration amplifies both organisations' impact."
        ),
    }

    _DEFAULT_PERSONA: str = (
        "You are addressing a Facility Administrator or senior decision-maker. "
        "Balance clinical credibility with operational practicality. "
        "Be concise, respectful, and outcome-focused."
    )

    # ── Channel instructions — keyed literally by channel value ───────
    _CHANNEL_INSTRUCTIONS: dict[str, str] = {
        "email": (
            "Write a highly personalized, professional email. "
            "Do NOT sound like a generic template — reference the entity's specific "
            "location, district, and causes. Include a clear subject line, a warm "
            "but professional opening, a value proposition paragraph, a specific ask, "
            "and a polite closing. Include the subject line in the 'subject_line' field."
        ),
        "whatsapp": (
            "Write a concise, engaging WhatsApp message. "
            "Use bullet points (•) and relevant emojis to aid readability. "
            "Keep it under 250 words. Do NOT include a formal subject line — "
            "return an empty string for 'subject_line'. "
            "End with a clear call-to-action."
        ),
        "phone_script": (
            "Write a 30-second cold-call phone script. "
            "Structure: Opening hook → Brief intro → Value proposition (one sentence) "
            "→ Specific ask → Close. Include conversational cues such as "
            "[Pause for them to respond] and [If yes, continue:] at natural breaks. "
            "Return an empty string for 'subject_line'."
        ),
        "linkedin": (
            "Write two parts in the 'message_content' field, clearly separated:\n"
            "PART 1 — LinkedIn Connection Request (under 300 characters, no subject line needed).\n"
            "PART 2 — Follow-up DM (sent after they accept; 150–200 words, "
            "personalised, references their organisation and causes). "
            "Return an empty string for 'subject_line'."
        ),
        "concept_note": (
            "Write a structured 1-page concept note using Markdown headings. "
            "Include the following sections in order:\n"
            "## Background\n"
            "## Proposed Pilot\n"
            "## Alignment with Facility\n"
            "## Expected Outcomes\n"
            "## Next Steps\n"
            "Be specific, data-informed, and persuasive. "
            "Include the concept note title as the 'subject_line'."
        ),
    }

    # ── Master system prompt template ─────────────────────────────────
    _SYSTEM_PROMPT = """\
You are an expert healthcare partnership communications specialist for \
MotherSource AI — a maternal health technology programme in India.

Your task is to draft a highly personalised outreach communication for a \
specific healthcare entity, using the persona approach and channel format \
described below.

PERSONA APPROACH:
{persona_instruction}

CHANNEL FORMAT:
{channel_instruction}

TONE: {tone}

RULES:
1. Return ONLY a valid JSON object with exactly these keys:
   - "subject_line"       : string (empty "" if not applicable for this channel)
   - "message_content"   : string (the full outreach content)
   - "missing_variables" : list of strings (info you needed but wasn't available, \
e.g. ["Contact Person's Direct Number"])
2. Do NOT include any text outside the JSON object.
3. Do NOT invent facts — only use information provided below.
4. If the recipient_name is provided, use it in the salutation.
5. Reference the entity's specific location, district, and social causes.
"""

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        model: str = "gpt-4o",
    ) -> None:
        self._client = openai_client
        self._model = model

    def _resolve_persona(self, recipient_role: str | None) -> str:
        """
        Match recipient_role against _PERSONA_INSTRUCTIONS keywords.
        Returns the first matching instruction, or the default fallback.
        """
        if not recipient_role:
            return self._DEFAULT_PERSONA
        role_lower = recipient_role.lower()
        for keyword, instruction in self._PERSONA_INSTRUCTIONS.items():
            if keyword in role_lower:
                return instruction
        return self._DEFAULT_PERSONA

    def _build_user_message(
        self,
        request: OutreachDraftRequest,
        entity: dict[str, Any],
    ) -> str:
        """
        Construct the user message block with entity metadata and request context.
        Truncates entity content to 1500 chars to stay within token budget.
        """
        recipient_line = (
            f"Recipient Name : {request.recipient_name}"
            if request.recipient_name
            else "Recipient Name : [Not provided — use a generic salutation]"
        )
        return (
            f"ENTITY DETAILS:\n"
            f"  Title (Reg No / Name) : {entity.get('title', 'N/A')}\n"
            f"  District / City       : {entity.get('district') or entity.get('city', 'N/A')}\n"
            f"  Full Details          : {str(entity.get('content', ''))[:1500]}\n\n"
            f"OUTREACH CONTEXT:\n"
            f"  Pilot Description : {request.pilot_description}\n"
            f"  Sender Name       : {request.sender_name}\n"
            f"  {recipient_line}\n"
            f"  Recipient Role    : {request.recipient_role or 'Facility Administrator'}\n"
            f"  Channel           : {request.channel}\n\n"
            "Draft the outreach now. Return valid JSON only."
        )

    async def draft(
        self,
        request: OutreachDraftRequest,
        entity: dict[str, Any],
    ) -> OutreachDraftResponse:
        """
        Generate a channel-specific, persona-adapted outreach draft.

        Parameters
        ----------
        request:
            Validated OutreachDraftRequest (includes channel, recipient_role, etc.)
        entity:
            Raw entity row from the Supabase `entities` table.

        Returns
        -------
        OutreachDraftResponse
            Contains subject_line, message_content, missing_variables.

        Raises
        ------
        RuntimeError
            If the OpenAI API call fails or returns unparseable output.
        """
        persona_instruction = self._resolve_persona(request.recipient_role)
        channel_instruction = self._CHANNEL_INSTRUCTIONS[request.channel]

        system_prompt = self._SYSTEM_PROMPT.format(
            persona_instruction=persona_instruction,
            channel_instruction=channel_instruction,
            tone=request.tone,
        )
        user_message = self._build_user_message(request, entity)

        logger.info(
            "Calling GPT-4o — channel=%s, role=%r, entity=%s",
            request.channel,
            request.recipient_role,
            entity.get("title", "unknown"),
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=0.4,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI API call failed: {exc}") from exc

        raw_json = response.choices[0].message.content or ""
        logger.debug("GPT-4o raw output: %s", raw_json[:300])

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"GPT-4o returned invalid JSON: {exc}\nRaw: {raw_json[:200]}"
            ) from exc

        try:
            return OutreachDraftResponse(
                subject_line=parsed.get("subject_line", ""),
                message_content=parsed["message_content"],
                missing_variables=parsed.get("missing_variables", []),
            )
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                f"GPT-4o response missing required fields: {exc}"
            ) from exc


# ═══════════════════════════════════════════════════════════════════════
# Layer 2 — Orchestration
# ═══════════════════════════════════════════════════════════════════════

class OutreachOrchestrator:
    """
    Orchestrates the full Service 3 pipeline:
      1. Fetch entity from Supabase `entities` table by UUID
      2. Pass to OutreachDraftingService to generate the draft
      3. Return OutreachDraftResponse

    Raises
    ------
    ValueError
        If entity_id is not found in the database (→ HTTP 404).
    RuntimeError
        If Supabase query or OpenAI API call fails (→ HTTP 503).
    """

    def __init__(
        self,
        repository: ChannelRepository,
        drafting_service: OutreachDraftingService,
    ) -> None:
        self._repository = repository
        self._drafting_service = drafting_service

    async def generate_draft(
        self,
        request: OutreachDraftRequest,
    ) -> OutreachDraftResponse:
        """
        Full pipeline: fetch entity → draft outreach → return response.

        Parameters
        ----------
        request:
            Validated OutreachDraftRequest from the API layer.

        Returns
        -------
        OutreachDraftResponse
        """
        logger.info(
            "Service 3 pipeline — entity_id=%s, channel=%s, role=%r",
            request.entity_id,
            request.channel,
            request.recipient_role,
        )

        # Step 1 — Fetch entity from Supabase
        entity = await self._repository.get_entity_by_id(request.entity_id)

        # Step 2 — Generate channel-specific, persona-adapted draft
        draft = await self._drafting_service.draft(request, entity)

        logger.info(
            "Service 3 complete — channel=%s, missing_vars=%d",
            request.channel,
            len(draft.missing_variables),
        )
        return draft
