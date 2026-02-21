# Service 1 — Mother Onboarding Finder
## Complete Technical Documentation

> **Project:** MotherSource AI  
> **Service:** Service 1 — Mother Onboarding Finder  
> **Target Region:** Andhra Pradesh & Telangana  
> **Status:** ✅ Running & Tested  
> **Last Updated:** February 2026  

---

## 1. What Is This Service?

Service 1 is a **FastAPI backend** that helps healthcare programme managers and field officers find the most relevant healthcare channels (entities) for maternal health outreach in Andhra Pradesh and Telangana.

Given a **district**, a **target demographic/environment** (Urban/Rural/General), and a **specific outreach need** (described in plain English), the service:

1. Converts the outreach need into a **semantic vector** using OpenAI embeddings
2. Queries the **Supabase `entities` table** (backed by pgvector) for the top 10 most semantically similar records in that district + environment
3. Passes those candidates to **GPT-4o** which ranks the best 1–4 and writes comparative explanations
4. Returns a **clean JSON response** with ranked results, scores, and AI-generated reasoning

---

## 2. Architecture Overview

```
Client (Swagger / curl / Frontend)
        │
        ▼
  POST /api/v1/channels/search
        │
        ▼
   routes.py  ──────────────────────────────────────────────────────────────────────
   (FastAPI Router)                                                                  │
        │                                                                            │
        ▼                                                                            │
   services.py → ChannelService.find_top_channels()                                 │
        │                                                                            │
        ├── Step 1: _embed_text(specific_need)                                       │
        │       └── OpenAI text-embedding-3-small → vector[1536]                    │
        │                                                                            │
        ├── Step 2: ChannelRepository.search_similar_channels()                     │
        │       └── Supabase RPC: search_entities(vector, district, env, 10)        │
        │               └── pgvector cosine similarity → top 10 rows                │
        │                                                                            │
        └── Step 3: LLMReasoningService.rank_and_reason()                          │
                └── GPT-4o (json_object mode, temp=0.2) → ranked[1–4] + reasoning  │
                                                                                     │
                                                                          ◄──────────
        ▼
   ChannelSearchResponse { results[], district, demographic }
```

---

## 3. Project File Structure

```
Mother_SourceAI_Backend/
│
├── main.py                    ← FastAPI app factory, CORS, /health endpoint
├── supabase_client.py         ← Standalone Supabase singleton (used by scripts)
├── requirements.txt           ← Pinned Python dependencies
├── .env                       ← API keys (gitignored)
├── .gitignore                 ← Excludes .env, __pycache__, venv
│
├── modules/                   ← Core application layer
│   ├── config.py              ← Settings (pydantic-settings), DI factories
│   ├── schemas.py             ← Pydantic request/response models
│   ├── database.py            ← ChannelRepository — Supabase data access
│   ├── routes.py              ← FastAPI router — POST /channels/search
│   └── services.py            ← ChannelService + LLMReasoningService
│
├── sql/
│   └── setup_entities.sql     ← Creates entities table + search_entities RPC
│
├── scripts/
│   └── ingest_hrag.py         ← Ingestion script: PDFs → embeddings → Supabase
│
├── data/                      ← Raw PDF files for ingestion
│
├── docs/
│   └── SERVICE_1_DOC.md       ← This file
│
└── test_payloads/             ← Ready-to-paste JSON bodies for Swagger testing
    ├── uc1_maternal_vaccination.json
    ├── uc2_antenatal_checkup.json
    ├── uc3a_short_demographic.json
    ├── uc3b_missing_field.json
    ├── uc3c_short_need.json
    ├── uc3d_nonexistent_district.json
    ├── uc3e_empty_body.json
    ├── uc4a_postnatal_care.json
    ├── uc4b_emergency_ob.json
    └── uc4c_nonexistent_mumbai.json
```

---

## 4. Module-by-Module Breakdown

### 4.1 `main.py` — App Factory

Creates and configures the FastAPI application.

**Key responsibilities:**
- Instantiates `FastAPI` with title, description, docs URLs
- Adds `CORSMiddleware` (allow all origins — tighten before production)
- Mounts the channels router at prefix `/api/v1`
- Exposes a `GET /health` liveness probe endpoint

```python
app = create_app()
# Accessible at:
# GET  /health                      → {"status": "ok"}
# GET  /docs                        → Swagger UI
# POST /api/v1/channels/search      → main endpoint
```

---

### 4.2 `modules/config.py` — Settings & Dependency Injection

Loads all environment variables and provides singleton client factories.

**Settings class** (loaded from `.env`):

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SUPABASE_URL` | str | required | Supabase project URL |
| `SUPABASE_KEY` | str | required | Supabase anon key |
| `OPENAI_API_KEY` | str | required | OpenAI API key |
| `APP_ENV` | str | `development` | Environment tag |
| `EMBEDDING_MODEL` | str | `text-embedding-3-small` | OpenAI embedding model |
| `EMBEDDING_DIMENSIONS` | int | `1536` | Vector dimensions |
| `LLM_MODEL` | str | `gpt-4o` | LLM model for ranking |
| `CANDIDATE_POOL_SIZE` | int | `10` | Rows fetched from DB before LLM re-ranks |
| `TOP_K_RESULTS` | int | `4` | Final results returned to caller |

**Singleton factories** (using `@lru_cache`):
- `get_settings()` → cached `Settings` instance
- `get_supabase_client()` → cached `supabase.Client`
- `get_openai_client()` → cached `AsyncOpenAI` client

These are injected into the route handler via FastAPI's `Depends()`.

---

### 4.3 `modules/schemas.py` — Pydantic Models

Defines the API contract: what the caller sends and what the service returns.

#### Request — `ChannelSearchRequest`

```json
{
  "district": "Hyderabad",
  "demographic": "Urban",
  "specific_need": "maternal vaccination outreach for first-time mothers"
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `district` | str | min 2, max 100 chars | AP/Telangana district name — must match `district` column in DB |
| `demographic` | str | min 2, max 100 chars | Urban / Rural / General — must match `environment` column in DB |
| `specific_need` | str | min 5, max 500 chars | Free-text description of the outreach objective |

#### Response — `ChannelSearchResponse`

```json
{
  "district": "Hyderabad",
  "demographic": "Urban",
  "results": [...]
}
```

#### Result Item — `ChannelResponseItem`

```json
{
  "entity_id": "uuid-...",
  "name": "Title of the healthcare chunk",
  "type": "Urban",
  "content": "Full text of the document chunk",
  "semantic_summary": "One-paragraph summary of the parent section",
  "rank_position": 1,
  "relevance_score": 0.92,
  "comparative_reasoning": "Ranked #1 because..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `entity_id` | str | UUID of the row in Supabase `entities` table |
| `name` | str | Title/heading of the healthcare content chunk |
| `type` | str | Urban / Rural / General |
| `content` | str (optional) | The actual text of this chunk from the source PDF |
| `semantic_summary` | str (optional) | AI-generated summary of the parent section |
| `rank_position` | int (1–10) | Rank assigned by GPT-4o |
| `relevance_score` | float (0.0–1.0) | AI-assigned match strength |
| `comparative_reasoning` | str | GPT-4o's explanation of why this rank was assigned |

---

### 4.4 `modules/database.py` — Data Access Layer

Handles all Supabase interactions. Follows the **Repository Pattern** (Single Responsibility Principle).

**`ChannelRepository`** class:

- Takes a `supabase.Client` in its constructor
- Exposes one method: `search_similar_channels(query_vector, district, environment, limit)`
- Calls the Supabase RPC function `search_entities` with the query vector and filters
- Returns a list of raw row dicts from the database

```python
# What it calls on Supabase:
self._client.rpc("search_entities", {
    "query_embedding": query_vector,   # vector[1536]
    "filter_district": district,        # e.g. "Hyderabad"
    "filter_environment": environment,  # e.g. "Urban"
    "match_count": limit,              # default 10
}).execute()
```

**Error handling:**
- If `response.data is None` → raises `RuntimeError`
- If `response.data` is empty (no matching rows) → logs a warning and returns empty list (caller handles this upstream)

---

### 4.5 `modules/services.py` — Business Logic

Contains two classes:

#### `LLMReasoningService`

Sends candidates to GPT-4o and gets back ranked results with reasoning.

**System prompt summary:**
- Role: "Senior healthcare analyst supporting maternal health outreach in India"
- Must return a JSON object with a `"results"` array
- Each item must have: `entity_id`, `name`, `type`, `rank_position`, `relevance_score`, `comparative_reasoning`
- Returns up to 4 items — never duplicates, never invents candidates

**User prompt:** Sends the `specific_need` text and a slim JSON list of candidates (entity_id, name, type, content, semantic_summary, district, similarity_score).

**OpenAI call settings:**
- `model`: gpt-4o
- `response_format`: `{"type": "json_object"}` — forces pure JSON, no markdown
- `temperature`: 0.2 — low creativity for consistent ranking
- `max_tokens`: 2048

**`_parse_and_validate()` method:**
- Parses the JSON string from GPT-4o
- Handles both `{"results": [...]}` and bare `[...]` array responses
- Validates all required keys are present
- Ensures between 1 and 4 results (not 0, not more than 4)
- Sorts by `rank_position` ascending

---

#### `ChannelService`

Orchestrates the full end-to-end flow.

**`find_top_channels(request)`** method:

```
Step 1: Embed the specific_need
        → OpenAI text-embedding-3-small → vector[1536]

Step 2: Search Supabase
        → ChannelRepository.search_similar_channels()
        → Returns up to 10 candidate rows

Step 3: (If 0 candidates) → raises RuntimeError → 503 upstream

Step 4: LLM ranking
        → LLMReasoningService.rank_and_reason()
        → Returns 1–4 ranked dicts from GPT-4o

Step 5: Map results
        → Merge GPT-4o output with full DB row data (content, semantic_summary)
        → Build ChannelResponseItem objects

Step 6: Return list[ChannelResponseItem]
```

---

### 4.6 `modules/routes.py` — FastAPI Router

Thin HTTP layer that wires dependencies to the service.

**Endpoint:** `POST /api/v1/channels/search`

**Error mapping:**

| Exception type | HTTP code | Meaning |
|----------------|-----------|---------|
| `RuntimeError` | 503 | No data found in DB, or external API (Supabase/OpenAI) failed |
| Any other `Exception` | 500 | Unexpected internal error |
| Pydantic `ValidationError` | 422 | Invalid request body (auto-handled by FastAPI) |

---

### 4.7 `sql/setup_entities.sql` — Database Schema

Defines the Supabase table and search function.

**`entities` table:**

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated row ID |
| `level` | TEXT | Hierarchy level of the chunk (section/subsection) |
| `title` | TEXT | Heading / title of this chunk |
| `semantic_summary` | TEXT | AI-generated summary of parent section |
| `content` | TEXT | Full text content of this chunk |
| `source_id` | TEXT | Identifier for the source PDF |
| `district` | TEXT | AP/Telangana district name |
| `environment` | TEXT | Urban / Rural / General |
| `embedding` | VECTOR(1536) | OpenAI embedding of the chunk content |

**Index:** HNSW index on `embedding` column for fast cosine similarity search.

**`search_entities` RPC function:**
- Filters by `district` and `environment` exactly
- Orders results by cosine distance (`<=>`) to the query vector
- Returns similarity score as `1 - cosine_distance`
- Limits to `match_count` rows (default 10)

---

### 4.8 `scripts/ingest_hrag.py` — PDF Ingestion Script

Processes source PDFs and loads embeddings into Supabase.

**What it does:**
1. Reads PDF files from the `data/` directory
2. Chunks the content hierarchically (by section/subsection)
3. Generates embeddings for each chunk using `text-embedding-3-small`
4. Writes rows to the Supabase `entities` table with all metadata

**Run it:**
```bash
python scripts/ingest_hrag.py
```

> ⚠️ This must be run **before the API can return results** — without ingested data, every search returns 503.

---

## 5. Data Flow — Step by Step

```
1. Client sends:
   POST /api/v1/channels/search
   {
     "district": "Hyderabad",
     "demographic": "Urban",
     "specific_need": "maternal vaccination outreach for first-time mothers"
   }

2. FastAPI validates the request body via Pydantic
   └── Invalid? → 422 immediately

3. ChannelService._embed_text("maternal vaccination outreach for first-time mothers")
   └── OpenAI API call → returns float[1536]

4. ChannelRepository.search_similar_channels(vector, "Hyderabad", "Urban", 10)
   └── Supabase RPC search_entities → returns up to 10 most similar rows
   └── 0 rows? → RuntimeError → 503

5. LLMReasoningService.rank_and_reason(specific_need, candidates)
   └── Sends system prompt + slim candidate list to GPT-4o
   └── GPT-4o returns JSON with ranked results + comparative reasoning
   └── Validated: must have 1–4 items, all required keys

6. ChannelService maps LLM output + DB row data into ChannelResponseItem objects

7. Router returns:
   {
     "district": "Hyderabad",
     "demographic": "Urban",
     "results": [
       {
         "entity_id": "abc-123",
         "name": "Chapter 3: District Immunisation Programme",
         "type": "Urban",
         "content": "The district immunisation programme covers...",
         "semantic_summary": "Overview of vaccination schedules in urban Hyderabad",
         "rank_position": 1,
         "relevance_score": 0.93,
         "comparative_reasoning": "Ranked #1 because this chunk directly addresses vaccination outreach..."
       },
       ...
     ]
   }
```

---

## 6. API Reference

### `POST /api/v1/channels/search`

**Request body:**
```json
{
  "district": "string (2–100 chars)",
  "demographic": "string (2–100 chars, e.g. Urban/Rural/General)",
  "specific_need": "string (5–500 chars)"
}
```

**Success response (200):**
```json
{
  "district": "string",
  "demographic": "string",
  "results": [
    {
      "entity_id": "uuid",
      "name": "string",
      "type": "string",
      "content": "string | null",
      "semantic_summary": "string | null",
      "rank_position": 1,
      "relevance_score": 0.93,
      "comparative_reasoning": "string"
    }
  ]
}
```

**Error responses:**

| Code | When |
|------|------|
| 422 | Invalid request body (missing field, too short, wrong type) |
| 503 | No matching data in DB, or Supabase/OpenAI API unavailable |
| 500 | Unexpected internal server error |

### `GET /health`

```json
{"status": "ok", "service": "mother-onboarding-finder"}
```

---

## 7. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Fetch 10 from DB, LLM picks up to 4** | Gives GPT-4o a meaningful candidate pool; avoids asking LLM to rank a single item against nothing |
| **`response_format={"type": "json_object"}`** | Forces GPT-4o to return valid JSON — eliminates markdown bleed (```json fences, etc.) |
| **`temperature=0.2`** | Low randomness produces stable, consistent ranking decisions run-over-run |
| **`@lru_cache` on client factories** | Creates one Supabase + one OpenAI connection per process lifetime — avoids connection overhead on every request |
| **`RuntimeError` → HTTP 503** | Clearly separates expected external failures (no data, API down) from unexpected bugs (500) |
| **`demographic` as free-text `str`** | Was originally `Literal["urban", "rural"]` but real DB data uses "Urban", "Rural", "General", "Women" — made flexible to match whatever `environment` values are in the DB |
| **HNSW index** | Production-grade approximate nearest-neighbour search — faster than IVFFlat for low query latency |
| **Async all the way** | `AsyncOpenAI` + `async def` route handlers allow concurrent request handling under load |

---

## 8. Setup & Running

### Prerequisites
- Python 3.10+
- Supabase project with `entities` table (run `sql/setup_entities.sql`)
- OpenAI API key

### Environment Variables (`.env`)
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
OPENAI_API_KEY=sk-...
```

### Install & Run
```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python -m uvicorn main:app --reload --port 8000 --host 0.0.0.0
```

### Ingest Data (required before API works)
```bash
python scripts/ingest_hrag.py
```

### API Explorer
Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser.

---

## 9. Testing

### Test Payloads

All test payloads are in `test_payloads/` as individual JSON files.  
**How to use in Swagger:** Open a file → Ctrl+A → Ctrl+C → paste into body → Execute.

| File | Expected Response | Tests |
|------|------------------|-------|
| `uc1_maternal_vaccination.json` | 200 ✅ | Happy path — maternal vaccination |
| `uc2_antenatal_checkup.json` | 200 ✅ | Same district, different need (reasoning should differ) |
| `uc3a_short_demographic.json` | 422 | Validation: demographic too short |
| `uc3b_missing_field.json` | 422 | Validation: missing `specific_need` |
| `uc3c_short_need.json` | 422 | Validation: `specific_need` too short |
| `uc3d_nonexistent_district.json` | 503 | No DB data for "Atlantis" |
| `uc3e_empty_body.json` | 422 | Empty body |
| `uc4a_postnatal_care.json` | 200 ✅ | Postnatal reasoning |
| `uc4b_emergency_ob.json` | 200 ✅ | Emergency OB reasoning (compare with UC4A) |
| `uc4c_nonexistent_mumbai.json` | 503 | District filtering — Mumbai not in AP/Telangana |

### What to Check for UC-1 & UC-2

1. `results` is a non-empty array (1–4 items)
2. Each item has all 7 fields populated
3. `rank_position` starts at 1 and is ascending
4. `relevance_score` is between 0.0 and 1.0
5. `comparative_reasoning` references the specific outreach need
6. **For UC-2 vs UC-1:** The same entity should appear but with different `comparative_reasoning` (antenatal vs vaccination language)

---

## 10. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.128.0 | Web framework |
| `uvicorn[standard]` | 0.24.0 | ASGI server |
| `supabase` | 2.28.0 | Supabase Python client |
| `openai` | 2.13.0 | OpenAI API client (async) |
| `pydantic` | 2.12.5 | Data validation |
| `pydantic-settings` | 2.12.0 | `.env` file settings management |
| `python-dotenv` | 1.0.0 | `.env` loading |
| `httpx` | 0.28.1 | HTTP client (required by supabase) |

---

## 11. Known Limitations & Next Steps

| Item | Status |
|------|--------|
| DB needs real AP/Telangana data from ingestion script | ⏳ Pending — run `ingest_hrag.py` with actual PDFs |
| `district` filtering is exact-match (case-sensitive) | May need `ILIKE` or normalization if user input varies |
| CORS is fully open (`allow_origins=["*"]`) | Tighten to specific frontend domains before production |
| No authentication on the endpoint | Add API key / JWT auth before exposing publicly |
| No rate limiting | Add per-client rate limits to control OpenAI spend |
| LLM reasoning quality depends on chunk quality | Better PDF chunking → better reasoning |
