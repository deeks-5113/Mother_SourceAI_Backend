-- ============================================================
-- setup_funders.sql
-- Supabase schema for Service 2: Funders data
-- Run once in the Supabase SQL Editor.
-- ============================================================

-- 1. Enable pgvector (idempotent)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create funders table
CREATE TABLE IF NOT EXISTS funders (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name           TEXT NOT NULL,
  city           TEXT NOT NULL,
  state          TEXT NOT NULL,
  focus_areas    TEXT[] NOT NULL DEFAULT '{}',
  level          TEXT,
  contact_name   TEXT,
  contact_email  TEXT,
  description    TEXT NOT NULL,
  embedding      VECTOR(1536),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. HNSW index for fast cosine search
CREATE INDEX IF NOT EXISTS funders_embedding_idx
  ON funders
  USING hnsw (embedding vector_cosine_ops);

-- 4. RPC: match_funders
-- Returns city-specific funders AND all "Global" funders for any query.
DROP FUNCTION IF EXISTS match_funders(vector, text, integer);

CREATE OR REPLACE FUNCTION match_funders(
  query_embedding  VECTOR(1536),
  filter_region    TEXT,
  match_count      INT DEFAULT 10
)
RETURNS TABLE (
  id              UUID,
  name            TEXT,
  city            TEXT,
  state           TEXT,
  focus_areas     TEXT[],
  level           TEXT,
  contact_name    TEXT,
  contact_email   TEXT,
  description     TEXT,
  similarity      FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    f.id,
    f.name,
    f.city,
    f.state,
    f.focus_areas,
    f.level,
    f.contact_name,
    f.contact_email,
    f.description,
    1 - (f.embedding <=> query_embedding) AS similarity
  FROM funders f
  WHERE
    f.city ILIKE '%' || filter_region || '%'
    OR f.city ILIKE 'global'
  ORDER BY
    f.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
