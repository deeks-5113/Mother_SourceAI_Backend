# HRAG Ingestion & Retrieval — Complete Technical Documentation

> **Project:** MotherSource AI
> **Covers:** How hospital/entity data is ingested into Supabase and retrieved for Service 1 & 3
> **Last Updated:** February 2026

---

## 1. What Is HRAG?

**HRAG = Hierarchical Retrieval-Augmented Generation**

The standard RAG approach splits documents into flat text chunks and retrieves them by semantic similarity. HRAG goes further — it preserves the **document hierarchy** (H1 → H2 → H3 → chunks) from the original source PDF, attaching metadata at each level.

For this project, the source is the **Directorate of Medical Education, Andhra Pradesh — Recognized Hospitals List**, a structured PDF containing:
- District-wise groupings (`H2` level)
- Individual hospital entries (`H3` level)
- Details: name, address, recognised specialties, recognition validity dates

Each hospital is stored as a **single chunk** in Supabase with:
- Its **title** (hospital name)
- Its **content** (full address + specialties + validity text)
- Its **district** and **environment** metadata
- A **vector embedding** of `title + content` for semantic search

---

## 2. System Components Overview

```
PDF Source (AP Hospital List)
        │
        ▼
  (Manual step) Convert PDF → Structured JSON
  (Output: data/sample1.json, sample2.json, sample3.json)
        │
        ▼
  scripts/ingest_hrag.py
        │
        ├── flatten_hrag_structure()   → extracts all chunks with metadata
        ├── get_embedding()            → OpenAI text-embedding-3-small (1536-dim)
        └── supabase.table("entities").insert()  → writes to Supabase
        │
        ▼
  Supabase: entities table (pgvector, HNSW index)
        │
        ▼
  Retrieval via search_entities() RPC  ← Service 1 (Channel Search)
  Retrieval via get_entity_by_id()     ← Service 3 (Outreach Generator)
```

---

## 3. The HRAG JSON Format

### 3.1 Structure

The source data follows a strict hierarchical JSON format representing the document structure:

```json
{
  "document_structure": [
    {
      "level": "H1",
      "title": "Directorate of Medical Education, A.P. - Recognized Hospitals List",
      "semantic_summary": "Official abstract and detailed list of recognized hospitals...",
      "children": [
        {
          "level": "H2",
          "title": "Vizianagaram District",
          "semantic_summary": "Detailed list of 24 recognized hospitals in Vizianagaram...",
          "children": [
            {
              "level": "H3",
              "title": "Tirumala Multi Speciality Hospitals",
              "chunks": [
                {
                  "source_id": "1 1",
                  "text": "Tirumala Multi Speciality Hospitals, Near R.T.C. Complex, Vizianagaram. Recognized for Cardiology, OBG, Nephrology... Valid from 18-04-2020 to 17-04-2023."
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

### 3.2 Hierarchy Levels

| Level | Represents | Example |
|-------|-----------|---------|
| `H1` | Entire document | "Directorate of Medical Education, A.P." |
| `H2` | District grouping | "Vizianagaram District", "Srikakulam District" |
| `H3` | Individual hospital | "Tirumala Multi Speciality Hospitals" |
| `chunk` | Text passage inside H3 | Address + specialties + validity dates |

### 3.3 Chunk Fields

| Field | Description |
|-------|-------------|
| `source_id` | Position reference (e.g., `"1 1"` = entry 1, district 1) |
| `text` | Full hospital details: name, address, recognised specialties, validity period |

### 3.4 Data Files

| File | District | Environment | Entities |
|------|----------|-------------|----------|
| `data/sample1.json` | All Districts | General | ~427 hospital chunks across multiple districts |
| `data/sample2.json` | Srikakulam | Urban | Srikakulam-specific hospitals |
| `data/sample3.json` | Krishna | Urban | Krishna district hospitals |

> **Note:** Multiple files can be ingested. The `district` and `environment` filters are set per file in `ingest_hrag.py`'s `ingestion_configs` list.

---

## 4. Ingestion Pipeline — `scripts/ingest_hrag.py`

### 4.1 Entry Point — `main()`

```python
ingestion_configs = [
    {"path": "data/sample1.json", "district": "All Districts", "environment": "General"},
    {"path": "data/sample2.json", "district": "Srikakulam",    "environment": "Urban"},
    {"path": "data/sample3.json", "district": "Krishna",       "environment": "Urban"},
]
```

For each config, it calls `ingest_file()`.

---

### 4.2 Step 1 — Flatten the Hierarchy: `flatten_hrag_structure()`

This is the core HRAG step. It **recursively traverses** the JSON tree and extracts every `chunk` it finds, attaching the metadata from its parent `H3` node.

```
H1 (document root)
└── H2 (district)
    └── H3 (hospital name + semantic_summary)
        └── chunks[] → each becomes one DB row
```

**What each extracted chunk record contains:**

```python
{
    "level": "H3",                          # from parent H3 node
    "title": "Tirumala Multi Speciality Hospitals",  # from parent H3 node
    "semantic_summary": "...",              # from parent H3 node
    "content": "Tirumala Multi Speciality... Recognized for OBG...",  # chunk.text
    "source_id": "1 1",                     # chunk.source_id
    "district": "All Districts",            # injected from ingestion config
    "environment": "General"                # injected from ingestion config
}
```

Key design decision: **the `district` and `environment` fields come from the ingestion config, not the JSON itself** — this makes it easy to re-tag data for different regions without re-parsing the source PDF.

---

### 4.3 Step 2 — Generate Embeddings: `get_embedding()`

```python
text_to_embed = f"{item['title']}: {item['content']}"
embedding = get_embedding(openai_client, text_to_embed, model, dimensions)
```

**Embedding strategy: title + content concatenation**

- `model`: `text-embedding-3-small` (set in `config.py`)
- `dimensions`: `1536` (set in `config.py`)
- Newlines stripped: `text.replace("\n", " ")` — prevents tokenisation artefacts
- Returns a `List[float]` of length 1536

**Why title + content?** The title alone ("Tirumala Multi Speciality Hospitals") has no specialty info. The content alone loses the hospital name. Combined, the embedding captures both "what entity" and "what it does" — improving retrieval for queries like "OBG hospital in Vizianagaram."

If embedding fails (OpenAI API error), the chunk is **skipped with a log error** — it's not inserted into Supabase.

---

### 4.4 Step 3 — Insert into Supabase

```python
item['embedding'] = embedding
supabase.table("entities").insert(item).execute()
```

No upsert — each run inserts fresh rows. The `id` is auto-generated as UUID by Supabase.

**Important:** If you run the script twice, rows are duplicated. For re-ingestion, manually delete existing rows or add a deduplication check on `source_id` first.

---

### 4.5 Full `ingest_hrag.py` Flow (Pseudocode)

```
for each config in ingestion_configs:
    load JSON from file
    chunks = flatten_hrag_structure(json, district, environment)
    # e.g., sample1.json → ~427 chunks
    
    for each chunk:
        text = f"{chunk.title}: {chunk.content}"
        vector = openai.embed(text)          # 1536-dim float list
        if vector is empty → skip (log error)
        
        chunk["embedding"] = vector
        supabase.insert("entities", chunk)   # 1 row per hospital per chunk
```

---

## 5. Supabase Schema — `entities` Table

Defined in `sql/setup_entities.sql`:

```sql
CREATE TABLE entities (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  level            TEXT,       -- "H3" for hospital entries
  title            TEXT,       -- hospital name
  semantic_summary TEXT,       -- parent node summary (H3 or H2 level)
  content          TEXT,       -- full hospital details text
  source_id        TEXT,       -- original PDF reference
  district         TEXT,       -- filter dimension 1 (e.g. "Srikakulam")
  environment      TEXT,       -- filter dimension 2 (e.g. "Urban", "General")
  embedding        VECTOR(1536) -- OpenAI text-embedding-3-small
);
```

### Index Strategy

```sql
CREATE INDEX ON entities USING hnsw (embedding vector_cosine_ops);
```

- **HNSW (Hierarchical Navigable Small World):** An approximate nearest-neighbour index optimised for high-dimensional vectors.
- **`vector_cosine_ops`:** Uses cosine distance (`<=>` operator) — ideal for normalised OpenAI embeddings where direction matters more than magnitude.
- **Why HNSW over IVFFlat?** HNSW is faster at query time, requires no training step, and handles insert well — better for a live demo.

---

## 6. Retrieval — `search_entities()` RPC

Defined in `sql/setup_entities.sql`, called by `ChannelRepository.search_similar_channels()`:

```sql
CREATE OR REPLACE FUNCTION search_entities(
  query_embedding   VECTOR(1536),
  filter_district   TEXT,
  filter_environment TEXT,
  match_count       INT
)
RETURNS TABLE (
  id, level, title, semantic_summary, content, source_id, district, environment,
  similarity FLOAT
)
AS $$
  SELECT ..., 1 - (e.embedding <=> query_embedding) AS similarity
  FROM entities e
  WHERE e.district = filter_district
    AND e.environment = filter_environment
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
$$;
```

### How It Works

1. **Hard filters first:** `WHERE district = ?  AND environment = ?`
   - Eliminates irrelevant districts before any vector scan
   - Reduces the candidate set dramatically — HNSW works on the filtered subset
2. **Vector ordering:** `ORDER BY e.embedding <=> query_embedding`
   - `<=>` = cosine distance (lower = more similar)
   - Orders by cosine distance ascending = most relevant first
3. **Similarity score returned:**
   - `1 - cosine_distance` = cosine similarity
   - Range: 0.0 (no match) to 1.0 (exact match)
4. **`LIMIT match_count`:** Configured via `settings.candidate_pool_size` (typically 10–20)

### Called From

```python
# modules/database.py — ChannelRepository.search_similar_channels()
response = self._client.rpc(
    "search_entities",
    {
        "query_embedding": query_vector,
        "filter_district": district,
        "filter_environment": environment,
        "match_count": limit,
    },
).execute()
```

---

## 7. Full Retrieval Flow — Service 1

```
Client Request:
  {
    "district": "Srikakulam",
    "demographic": "Urban",
    "specific_need": "I need a hospital with OBG and paediatrics for pregnant mothers"
  }

Step 1 — Embed the query:
  openai.embeddings.create(
      model="text-embedding-3-small",
      input="I need a hospital with OBG and paediatrics for pregnant mothers",
      dimensions=1536
  )
  → query_vector: [0.023, -0.112, 0.041, ...] (1536 floats)

Step 2 — Vector search in Supabase:
  search_entities(
      query_embedding = query_vector,
      filter_district = "Srikakulam",
      filter_environment = "Urban",
      match_count = 10  (candidate pool)
  )
  → Returns top-10 hospitals from Srikakulam Urban
    (e.g. KIMS Sai Seshadri, Medicover Srikakulam, Vijaya Harsha Mother & Child...)
    Each row has: id, title, content, similarity score

Step 3 — LLM ranking via GPT-4o:
  Candidates + query → GPT-4o → ranked list of 1-4 entities
  Each with: relevance_score, rank_position, comparative_reasoning

Step 4 — Return to client:
  Top-4 ranked hospitals with reasoning
```

---

## 8. Point Lookup — Service 3

For outreach email drafting, Service 3 fetches a **single entity by UUID** directly:

```python
# modules/database.py — ChannelRepository.get_entity_by_id()
response = (
    self._client.table("entities")
    .select("*")
    .eq("id", entity_id)
    .single()
    .execute()
)
```

- `.single()` tells PostgREST to expect exactly one row — raises `APIError` (HTTP 406, code `PGRST116`) if none found
- The entity's `title`, `district`, `environment`, `content` are passed directly to GPT-4o to personalise the email

---

## 9. Embedding Model Settings (from `config.py`)

| Setting | Value | Purpose |
|---------|-------|---------|
| `embedding_model` | `text-embedding-3-small` | OpenAI model used for both ingestion & retrieval |
| `embedding_dimensions` | `1536` | Output vector size |
| `candidate_pool_size` | configurable | How many candidates `search_entities` returns |

**Critical consistency rule:** The same model + dimensions must be used at **ingestion time** and **query time**. Using `text-embedding-3-small` at ingestion and `text-embedding-3-large` at query would make cosine distances meaningless.

---

## 10. Data Quality Observations

From `sample1.json`:

| Property | Notes |
|----------|-------|
| ~427 total hospital records | Across all AP districts |
| Each hospital = one chunk | 1:1 mapping of hospital to DB row |
| Content = full details | Name, address, specialties, validity dates in one text block |
| No null handling needed | `source_id` is always present; `text` is always non-empty |
| Validity dates not parsed | Stored as raw text — not used as a filter yet |

**Potential improvement:** Parse `validity` dates into a `valid_until DATE` column to filter out expired recognitions from search results.

---

## 11. Re-Ingestion Instructions

If you add new hospital data or re-run ingestion after clearing the table:

```bash
# Step 1 — Clear existing data (run in Supabase SQL Editor)
DELETE FROM entities;

# Step 2 — Re-run ingestion
cd C:\Users\adity\Desktop\Mother_SourceAI_Backend
python scripts/ingest_hrag.py
```

To add new districts, add a new entry to `ingestion_configs` in `ingest_hrag.py`:
```python
{"path": "data/sample4.json", "district": "Guntur", "environment": "Urban"},
```

---

## 12. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **One chunk per hospital (not sub-chunked)** | Hospital records are short (1–3 sentences). Sub-chunking would lose context and produce worse embeddings. |
| **Embed title + content together** | Title alone = no specialty info. Content alone = no hospital name. Combined = best semantic representation. |
| **District + environment as hard filters** | Reduce candidates before vector scan. A maternal health query in Srikakulam should never return Hyderabad hospitals. |
| **HNSW over IVFFlat** | HNSW needs no probing tuning, works well at demo scale, and doesn't require prior clustering. |
| **Cosine similarity (`<=>`)** | OpenAI embeddings are normalised; cosine distance is the natural metric. |
| **Ingestion configs hardcoded** | For hackathon simplicity. Production should use CLI args or a YAML config. |
| **No upsert on duplicate** | Simple insert per run. Deduplication (on `source_id`) should be added before production use. |
