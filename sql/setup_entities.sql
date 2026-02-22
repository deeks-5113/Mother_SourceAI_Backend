-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Update entities table structure
DROP TABLE IF EXISTS entities;
CREATE TABLE entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  level TEXT,
  title TEXT,
  semantic_summary TEXT,
  content TEXT,
  source_id TEXT,
  district TEXT,
  environment TEXT,
  source_type TEXT DEFAULT 'hospital',
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  embedding VECTOR(1536)
);

-- Index for vector search (HNSW for production quality)
CREATE INDEX ON entities USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_entities_district_geo
ON entities (district)
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- RPC for hybrid search (legacy — filters by district AND environment)
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

-- RPC for district-first search (filters only by district, semantic ranking)
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

-- RPC for diversified search (filters by district AND source_type)
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

-- ═══════════════════════════════════════════════════════════════════════
-- Service 4: Dispatch Brainstorm Sessions
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS dispatch_sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    pilot_description TEXT NOT NULL,
    channel TEXT NOT NULL,
    outreach_draft JSONB NOT NULL,
    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
