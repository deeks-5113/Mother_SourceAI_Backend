# Service 3 — Smart Outreach Generator
## Complete Technical Documentation

> **Project:** MotherSource AI
> **Service:** Service 3 — Smart Outreach Generator
> **Depends on:** Service 1 (`entities` table in Supabase)
> **Status:** ✅ Running & Tested
> **Last Updated:** February 2026

---

## 1. What Is This Service?

Service 3 is a **FastAPI endpoint** that generates a personalised outreach email draft for a specific healthcare entity (hospital, clinic, NGO) stored in the `entities` table.

Given an **entity ID** (UUID), a **pilot description**, a **sender name**, and an optional **tone**, the service:

1. Fetches the full entity record from Supabase (`entities` table) by UUID
2. Passes the entity's name, district, environment type, and content to **GPT-4o**
3. GPT-4o writes a personalised email draft that directly references that entity's context
4. Returns `subject_line`, `email_body`, and `missing_variables` (anything the LLM needed but didn't have)

---

## 2. Architecture Overview

```
Client (Swagger / curl / Frontend)
        │
        ▼
  POST /api/v1/outreach/draft
        │
        ▼
   outreach_routes.py  (FastAPI Router)
        │
        ▼
   OutreachOrchestrator.generate_draft()
        │
        ├── Step 1: ChannelRepository.get_entity_by_id(entity_id)
        │       └── Supabase: entities table → single row by UUID
        │       └── Not found? → ValueError → 404
        │
        └── Step 2: OutreachDraftingService.draft_email(entity_data, request)
                └── GPT-4o (json_object mode, temp=0.4) → subject + body + missing_vars
                └── API fails? → RuntimeError → 503
        │
        ▼
   OutreachDraftResponse { subject_line, email_body, missing_variables }
```

---

## 3. File Structure (Service 3 Only)

```
Mother_SourceAI_Backend/
│
├── modules/
│   ├── outreach_schemas.py     ← NEW: Pydantic request/response models
│   ├── outreach_services.py    ← NEW: LLM layer + orchestration layer
│   ├── outreach_routes.py      ← NEW: FastAPI router for /outreach/draft
│   ├── ngo_repository.py       ← NEW: NgoRepository (for future NGO search)
│   └── database.py             ← MODIFIED: added get_entity_by_id() method
│
├── scripts/
│   └── ingest_ngos.py          ← NEW: NGO embedding + Supabase ingest pipeline
│
├── data/
│   └── ngos.json               ← NEW: 4 sample AP/Telangana NGO profiles
│
├── main.py                     ← MODIFIED: registered outreach router
│
└── test_payloads/
    ├── s3_uc1_professional_tone.json
    ├── s3_uc2_warm_tone.json
    ├── s3_uc3_unknown_entity.json
    ├── s3_uc4_missing_field.json
    └── s3_uc5_complex_pilot.json
```

**Service 1 files untouched:** `schemas.py`, `services.py`, `routes.py`

---

## 4. Module-by-Module Breakdown

### 4.1 `modules/outreach_schemas.py` — Pydantic Models

Defines the API contract: what the caller sends and what the service returns.

#### Request — `OutreachDraftRequest`

```json
{
  "entity_id": "630ff118-4dfd-41f4-990e-f6b63c11a600",
  "pilot_description": "A 3-month maternal vaccination camp in rural Warangal...",
  "sender_name": "Dr. Priya Sharma",
  "tone": "professional and collaborative"
}
```

| Field | Type | Constraints | Default |
|-------|------|-------------|---------|
| `entity_id` | str | UUID of entity | required |
| `pilot_description` | str | 10–1000 chars | required |
| `sender_name` | str | 2–100 chars | required |
| `tone` | str | 2–100 chars | `"professional and collaborative"` |

#### Response — `OutreachDraftResponse`

```json
{
  "subject_line": "Partnership Proposal: Maternal Vaccination Drive — Tirumala Multi Speciality Hospitals",
  "email_body": "Dear Team at Tirumala Multi Speciality Hospitals,\n\nWe are writing to propose...",
  "missing_variables": ["Insert Meeting Date", "Insert Contact Phone Number"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `subject_line` | str | Ready-to-use email subject |
| `email_body` | str | Full personalised email body |
| `missing_variables` | list[str] | Placeholders LLM couldn't fill from context |

---

### 4.2 `modules/database.py` — `get_entity_by_id()` (added method)

The only modification to an existing Service 1 file. One async method added to `ChannelRepository`:

```python
async def get_entity_by_id(self, entity_id: str) -> dict
```

- Calls: `self._client.table("entities").select("*").eq("id", entity_id).single().execute()`
- `.single()` tells PostgREST to expect exactly one row — raises `APIError` if 0 rows match
- The `except` block catches this and converts it to `ValueError` so the router can return 404

**PostgREST error detection:**
```python
if "no rows" in error_msg or "406" in error_msg or "pgrst116" in error_msg:
    raise ValueError(f"Entity with id='{entity_id}' not found.")
```

---

### 4.3 `modules/outreach_services.py` — Business Logic

Two classes following **Single Responsibility Principle**:

---

#### `OutreachDraftingService` — LLM Layer

Only responsibility: talk to GPT-4o and return a validated dict.

**System prompt strategy:**
- Role: "Expert healthcare partnership outreach writer"
- Must return JSON with exactly 3 keys: `subject_line`, `email_body`, `missing_variables`
- Email must reference the entity's `title`, `district`, `environment`, and `content`
- `missing_variables` must list anything needed but unavailable (dates, phone numbers, etc.)
- GPT-4o call settings:
  - `response_format={"type": "json_object"}` — no markdown bleed
  - `temperature=0.4` — slightly creative but consistent
  - `max_tokens=2048`

**User prompt fields passed to GPT-4o:**

| Field | Source |
|-------|--------|
| Entity name / title | `entity_data["title"]` |
| District | `entity_data["district"]` |
| Environment | `entity_data["environment"]` |
| Service context | `entity_data["content"][:1500]` (truncated to avoid token overflow) |
| Pilot description | `request.pilot_description` |
| Sender name | `request.sender_name` |
| Tone | `request.tone` |

**`_parse_and_validate()` method:**
- Parses JSON from GPT-4o
- Checks all 3 required keys are present
- Ensures `missing_variables` is a list (normalises it if not)

---

#### `OutreachOrchestrator` — Orchestration Layer

Only responsibility: wire `ChannelRepository` + `OutreachDraftingService`, own the flow.

Constructor injects `supabase_client` and `openai_client` (Dependency Inversion).

**`generate_draft(request)` flow:**

```
1. ChannelRepository.get_entity_by_id(entity_id)
   └── ValueError if not found → propagates → 404

2. OutreachDraftingService.draft_email(entity_data, request)
   └── RuntimeError if OpenAI fails → propagates → 503

3. Map raw dict to OutreachDraftResponse → return
```

---

### 4.4 `modules/outreach_routes.py` — FastAPI Router

Standalone router with its own `APIRouter(prefix="/outreach", tags=["Outreach"])`.  
Mounted in `main.py` at `prefix="/api/v1"` → final path: `/api/v1/outreach/draft`.

**Endpoint:** `POST /api/v1/outreach/draft`

**Error mapping:**

| Exception | HTTP Code | Cause |
|-----------|-----------|-------|
| `ValueError` | 404 | entity_id not found in DB |
| `RuntimeError` | 503 | OpenAI or Supabase API failure |
| Any other `Exception` | 500 | Unexpected internal error |
| Pydantic `ValidationError` | 422 | Invalid/incomplete request body (auto by FastAPI) |

**`main.py` change (2 lines added):**
```python
from modules.outreach_routes import router as outreach_router
application.include_router(outreach_router, prefix="/api/v1")
```

---

### 4.5 `modules/ngo_repository.py` — NGO Repository (Future Use)

Dedicated repository for the `ngos` table — entirely separate from `ChannelRepository`.

| Method | Purpose |
|--------|---------|
| `search_similar_ngos(query_vector, district, limit)` | Semantic search via Supabase `search_ngos` RPC |
| `get_ngo_by_id(ngo_id)` | Fetch single NGO by UUID |
| `upsert_ngo(record)` | Write/update an NGO row (used by ingest script) |

**Not wired into any current endpoint** — ready for a future "Search NGOs by outreach need" service.

---

### 4.6 `scripts/ingest_ngos.py` — NGO Ingestion Pipeline

Reads `data/ngos.json`, generates embeddings, upserts into Supabase `ngos` table.

**Run it:**
```bash
python scripts/ingest_ngos.py --input data/ngos.json
```

**Input JSON format** (per NGO object):

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | NGO name |
| `district` | ✅ | AP/Telangana district |
| `state` | ✅ | Andhra Pradesh / Telangana |
| `focus_areas` | ✅ | Array of topic tags |
| `description` | ✅ | Full profile text — **used to generate embedding** |
| `contact_name` | optional | Primary contact person |
| `contact_email` | optional | Contact email |
| `contact_phone` | optional | Contact phone |
| `level` | optional | district / city / block |

---

## 5. Data Flow — Step by Step

```
1. Client sends:
   POST /api/v1/outreach/draft
   {
     "entity_id": "630ff118-4dfd-41f4-990e-f6b63c11a600",
     "pilot_description": "A 3-month maternal vaccination camp in Warangal...",
     "sender_name": "Dr. Priya Sharma",
     "tone": "professional and collaborative"
   }

2. FastAPI validates body via Pydantic
   └── Missing/invalid field? → 422 immediately

3. OutreachOrchestrator.generate_draft(request)

4. ChannelRepository.get_entity_by_id("630ff118-...")
   └── Supabase: SELECT * FROM entities WHERE id = '...' LIMIT 1
   └── Returns: { id, title, district, environment, content, ... }
   └── Not found? → ValueError → 404

5. OutreachDraftingService.draft_email(entity_data, request)
   └── Builds system prompt + user message with all entity context
   └── Calls GPT-4o (json_object, temp=0.4)
   └── GPT-4o returns:
       {
         "subject_line": "Partnership Proposal: Maternal Health Drive — Tirumala Hospitals",
         "email_body": "Dear Team at Tirumala Multi Speciality Hospitals...",
         "missing_variables": ["Insert Meeting Date"]
       }
   └── Validated: all 3 keys present, missing_variables is a list

6. OutreachOrchestrator maps dict → OutreachDraftResponse

7. Router returns HTTP 200:
   {
     "subject_line": "...",
     "email_body": "...",
     "missing_variables": ["Insert Meeting Date"]
   }
```

---

## 6. API Reference

### `POST /api/v1/outreach/draft`

**Request body:**
```json
{
  "entity_id": "string (UUID)",
  "pilot_description": "string (10–1000 chars)",
  "sender_name": "string (2–100 chars)",
  "tone": "string (optional, default: 'professional and collaborative')"
}
```

**Success response (200):**
```json
{
  "subject_line": "string",
  "email_body": "string",
  "missing_variables": ["string", ...]
}
```

**Error responses:**

| Code | When |
|------|------|
| 422 | Missing/invalid field (Pydantic catches before service) |
| 404 | `entity_id` not found in Supabase `entities` table |
| 503 | OpenAI or Supabase API unreachable |
| 500 | Unexpected internal error |

---

## 7. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Separate files per service** | SRP — `outreach_*.py` files have zero coupling to Service 1 code |
| **Only `database.py` modified** | `get_entity_by_id()` is a pure additive method on an existing class — no regression risk |
| **`response_format={"type": "json_object"}`** | Forces GPT-4o to return valid JSON — eliminates markdown fences in output |
| **`temperature=0.4`** | Higher than Service 1 (0.2) — email writing benefits from slightly more creative phrasing while remaining reliable |
| **`missing_variables` field** | Surfaces LLM uncertainty explicitly — the caller knows exactly what to fill in manually before sending |
| **Content truncated to 1500 chars** | Avoids token overflow when entity content is long; preserves the most relevant leading context |
| **`ValueError` → 404, `RuntimeError` → 503** | Clean, predictable HTTP semantics — consumers can distinguish "not found" from "service down" |
| **`NgoRepository` as a separate class** | DIP — future NGO service can inject it without touching any existing code |

---

## 8. Database — NGO Table (Future)

SQL to create the `ngos` table (run in Supabase SQL Editor):

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE ngos (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  district      TEXT NOT NULL,
  state         TEXT NOT NULL DEFAULT 'Telangana',
  focus_areas   TEXT[],
  level         TEXT,
  contact_name  TEXT,
  contact_email TEXT,
  contact_phone TEXT,
  description   TEXT,
  source_id     TEXT,
  embedding     VECTOR(1536),
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON ngos USING hnsw (embedding vector_cosine_ops);
```

Then ingest sample data:
```bash
python scripts/ingest_ngos.py --input data/ngos.json
```

---

## 9. Testing

### Test Payloads (ready to paste into Swagger)

Open [http://localhost:8000/docs](http://localhost:8000/docs) → **Outreach** → `POST /api/v1/outreach/draft` → Try it out

| File | Entity | Tone | Expected |
|------|--------|------|----------|
| `s3_uc1_professional_tone.json` | Tirumala Multi Speciality Hospitals | Professional | **200** |
| `s3_uc2_warm_tone.json` | Sri Sai Super Speciality Hospital | Warm & persuasive | **200** |
| `s3_uc3_unknown_entity.json` | Non-existent UUID | — | **404** |
| `s3_uc4_missing_field.json` | Tirumala (no `pilot_description`) | — | **422** |
| `s3_uc5_complex_pilot.json` | District-wise Hospital Counts | Urgent | **200** + `missing_variables` non-empty |

### What to Verify on a 200 Response

1. `subject_line` references the entity name or district
2. `email_body` has at least 3 paragraphs; signed with `sender_name`
3. `email_body` mentions something specific from the entity's context (not generic)
4. `missing_variables` is a list (can be empty — that's fine)
5. For UC-5 (`urgent` tone): `missing_variables` should flag missing dates/contacts

---

## 10. Known Limitations & Next Steps

| Item | Status |
|------|--------|
| Service 3 reads from `entities` table — built for hospitals/clinics, not dedicated NGOs | `ngos` table + `NgoRepository` ready, needs new endpoint |
| No draft persistence — email is generated and returned but not saved | Add `outreach_drafts` table if audit trail needed post-hackathon |
| Content truncated to 1500 chars — long entity records lose tail context | Increase or implement smarter chunking selection |
| CORS fully open | Tighten to frontend origin before production |
