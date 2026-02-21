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
  embedding VECTOR(1536)
);

-- Index for vector search (HNSW for production quality)
CREATE INDEX ON entities USING hnsw (embedding vector_cosine_ops);

-- RPC for hybrid search
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
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM entities e
  WHERE
    e.district = filter_district
    AND e.environment = filter_environment
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
