-- Migration: add geospatial columns to entities for map rendering
-- Run in Supabase SQL Editor for existing deployments.

ALTER TABLE entities
ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;

ALTER TABLE entities
ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_entities_district_geo
ON entities (district)
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
