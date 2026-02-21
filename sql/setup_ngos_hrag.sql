-- ============================================================
-- setup_ngos_hrag.sql
-- NGO HRAG table — mirrors the `entities` table design.
-- Run once in the Supabase SQL Editor.
-- ============================================================

-- Enable pgvector (safe to re-run if already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop and recreate (clean slate)
DROP TABLE IF EXISTS ngos;

CREATE TABLE ngos (
  id               UUID    PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Hierarchy metadata (from the HRAG JSON)
  level            TEXT,           -- always "H3" for individual NGO entries
  title            TEXT,           -- H3 title  → NGO registration number / name
                                   --   e.g. "Reg No: 1454 Of 1994"
  semantic_summary TEXT,           -- H2 summary → city / region context blurb

  -- Chunk payload
  content          TEXT,           -- chunk.text  → address + social causes text
  source_id        TEXT,           -- chunk.source_id → original PDF position ref

  -- Filter dimensions (injected by ingestion script)
  city             TEXT,           -- H2 title   → city / region name
                                   --   e.g. "Kakinada", "Tirupati Region"

  -- Vector embedding (OpenAI text-embedding-3-small, 1536-dim)
  embedding        VECTOR(1536),

  -- Audit
  created_at       TIMESTAMPTZ DEFAULT now()
);

-- ── HNSW index for fast cosine-similarity search ─────────────────────
-- Uses cosine distance (<=>); matches the OpenAI embedding space.
CREATE INDEX ON ngos USING hnsw (embedding vector_cosine_ops);

-- ── RPC: search_ngos ────────────────────────────────────────────────
-- Drop first to allow changing the return-type signature safely.
DROP FUNCTION IF EXISTS search_ngos(vector, text, integer);

-- Semantically searches NGOs filtered by city, ordered by cosine similarity.
-- Called from NgoRepository.search_similar_ngos().
CREATE OR REPLACE FUNCTION search_ngos(
  query_embedding   VECTOR(1536),
  filter_city       TEXT,
  match_count       INT DEFAULT 10
)
RETURNS TABLE (
  id               UUID,
  level            TEXT,
  title            TEXT,
  semantic_summary TEXT,
  content          TEXT,
  source_id        TEXT,
  city             TEXT,
  similarity       FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    n.id,
    n.level,
    n.title,
    n.semantic_summary,
    n.content,
    n.source_id,
    n.city,
    -- Convert cosine DISTANCE to cosine SIMILARITY (1 = identical)
    1 - (n.embedding <=> query_embedding) AS similarity
  FROM ngos n
  WHERE n.city = filter_city
  ORDER BY n.embedding <=> query_embedding   -- ascending distance = descending similarity
  LIMIT match_count;
END;
$$;
