-- ═══════════════════════════════════════════════════════════════════════
-- Migration: Add source_type column and diversified search RPC
-- Run this in Supabase SQL Editor
-- ═══════════════════════════════════════════════════════════════════════

-- 1. Add source_type column (default 'hospital')
ALTER TABLE entities ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'hospital';

-- 2. Backfill: tag PHCs
UPDATE entities SET source_type = 'phc'
WHERE source_type IS NULL OR source_type = 'hospital'
  AND (
    title ILIKE '%PHC%'
    OR title ILIKE '%UPHC%'
    OR title ILIKE '%Primary Health Centre%'
    OR title ILIKE '%Primary Health Center%'
    OR semantic_summary ILIKE '%Primary Health Centre%'
    OR semantic_summary ILIKE '%Primary Health Center%'
  );

-- 3. Backfill: tag medical colleges
UPDATE entities SET source_type = 'medical_college'
WHERE source_type IS NULL OR source_type = 'hospital'
  AND (
    title ILIKE '%Medical College%'
    OR title ILIKE '%Institute of Medical%'
    OR title ILIKE '%AIIMS%'
    OR semantic_summary ILIKE '%medical college%'
    OR content ILIKE '%medical college%'
  );

-- 4. Remaining rows stay as 'hospital' (the default)

-- 5. New RPC: search by district + source_type
CREATE OR REPLACE FUNCTION search_entities_by_district_and_type(
  query_embedding VECTOR(1536),
  filter_district TEXT,
  filter_source_type TEXT,
  match_count INT
)
RETURNS TABLE (
  id UUID,
  level TEXT,
  title TEXT,
  semantic_summary TEXT,
  content TEXT,
  source_id TEXT,
  district TEXT,
  environment TEXT,
  source_type TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.level,
    e.title,
    e.semantic_summary,
    e.content,
    e.source_id,
    e.district,
    e.environment,
    e.source_type,
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM entities e
  WHERE
    e.district = filter_district
    AND e.source_type = filter_source_type
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 6. Update existing RPCs to return source_type column
CREATE OR REPLACE FUNCTION search_entities_by_district(
  query_embedding VECTOR(1536),
  filter_district TEXT,
  match_count INT
)
RETURNS TABLE (
  id UUID,
  level TEXT,
  title TEXT,
  semantic_summary TEXT,
  content TEXT,
  source_id TEXT,
  district TEXT,
  environment TEXT,
  source_type TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.level,
    e.title,
    e.semantic_summary,
    e.content,
    e.source_id,
    e.district,
    e.environment,
    e.source_type,
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM entities e
  WHERE
    e.district = filter_district
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

CREATE OR REPLACE FUNCTION search_entities(
  query_embedding VECTOR(1536),
  filter_district TEXT,
  filter_environment TEXT,
  match_count INT
)
RETURNS TABLE (
  id UUID,
  level TEXT,
  title TEXT,
  semantic_summary TEXT,
  content TEXT,
  source_id TEXT,
  district TEXT,
  environment TEXT,
  source_type TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.level,
    e.title,
    e.semantic_summary,
    e.content,
    e.source_id,
    e.district,
    e.environment,
    e.source_type,
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM entities e
  WHERE
    e.district = filter_district
    AND e.environment = filter_environment
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 7. Verify: check distribution
SELECT source_type, COUNT(*) FROM entities GROUP BY source_type;
