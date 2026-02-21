-- ============================================================
-- setup_match_ngos.sql
-- Supabase RPC for Service 2: Funding & Partnership Scout
-- Run once in the Supabase SQL Editor.
-- ============================================================

-- Drop first to allow changing the return-type signature safely.
DROP FUNCTION IF EXISTS match_ngos(vector, text, integer);

-- ── RPC: match_ngos ─────────────────────────────────────────
-- Semantically searches NGOs by region (ILIKE on city column)
-- ordered by cosine similarity to query_embedding.
--
-- Uses ILIKE '%region%' so "Tirupati" matches "Tirupati Region".
-- Called from NgoRepository.match_ngos_by_region().
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION match_ngos(
  query_embedding  VECTOR(1536),
  filter_region    TEXT,
  match_count      INT DEFAULT 10
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
    -- Cosine similarity: 1.0 = identical, 0.0 = orthogonal
    1 - (n.embedding <=> query_embedding) AS similarity
  FROM ngos n
  WHERE
    -- Partial, case-insensitive city match
    n.city ILIKE '%' || filter_region || '%'
  ORDER BY
    n.embedding <=> query_embedding   -- ascending distance = descending similarity
  LIMIT match_count;
END;
$$;
