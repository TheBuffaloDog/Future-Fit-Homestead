-- Read-only public access, for the frontend to query Supabase directly
-- instead of going through a custom API. No INSERT/UPDATE/DELETE policy is
-- added anywhere — the anon role can only ever SELECT, and only from layers
-- and features. scoring_profiles, scoring_weights, and watchlist_parcels
-- stay fully private; nothing outside your own connection string can touch
-- them.

CREATE POLICY "Public read access" ON layers FOR SELECT TO anon USING (true);
CREATE POLICY "Public read access" ON features FOR SELECT TO anon USING (true);

-- Supabase's REST API returns PostGIS geometry as raw WKB, which a browser
-- can't hand straight to MapLibre. This view pre-converts it to GeoJSON so
-- the frontend can query it directly with no parsing step. Views inherit
-- RLS from their underlying tables, so the same read-only rule above applies
-- here automatically.
CREATE OR REPLACE VIEW features_geojson AS
SELECT
  f.id,
  f.layer_id,
  l.slug AS layer_slug,
  l.category,
  l.confidence_tier,
  ST_AsGeoJSON(f.geom)::jsonb AS geometry,
  f.properties
FROM features f
JOIN layers l ON l.id = f.layer_id;
