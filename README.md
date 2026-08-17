# Future-Fit Homestead — starter scaffold

Personal-first build of the site-selection platform. Companion to the design
brief from earlier in this project — this repo makes Sections 3 and 5 of that
doc real, one real data source at a time.

**Current direction:** build, host, and test for personal use first; think
about a public release later, once there's real data coverage worth showing
anyone. No commercialization plans — this may end up fully open source.
Deploying a custom API (Render) is deliberately deferred — Supabase's own
read API is enough for now, and standing up more infrastructure before it's
actually needed would be solving a problem we don't have yet.

## What's here — and tested
- **`db/schema.sql`** — generic, metadata-driven schema (every layer carries
  its own confidence tier, source, and vintage). Runs cleanly against a live
  PostGIS 16 instance.
- **`db/policies.sql`** — read-only public access for `layers`/`features` via
  Supabase's built-in REST API, plus a `features_geojson` view that
  pre-converts PostGIS geometry to real GeoJSON (confirmed correct output)
  so the frontend needs zero parsing logic.
- **`etl/common.py`** — the shared pattern (caching, layer-catalog upsert,
  clearing old features) extracted after the 2nd pipeline made the
  copy-pasting obvious. Every pipeline since is noticeably shorter.
- **`etl/fetch_county_boundaries.py`**, **`fetch_fema_nri.py`**,
  **`fetch_drought_monitor.py`** — three real pipelines (Category REF, D, B)
  built on that shared template. First two are proven live on real data;
  the third's parsing logic is tested against a representative sample —
  see the note in that file about confirming its exact source URL.
- **`etl/test_parse.py`** — unit tests for the FEMA parsing/filtering logic.
- **`frontend/index.html`** — MapLibre prototype that now queries Supabase's
  REST API directly for real layers, and only falls back to sample data if
  `SUPABASE_URL`/`SUPABASE_ANON_KEY` at the top of the script aren't filled
  in yet.
- **`.github/workflows/update-data.yml`** — runs all three pipelines on a
  schedule. Confirmed working end to end against the live database.

The full chain — schema → ETL → live database → real map — has been proven
piece by piece, either against a live local PostGIS instance in this sandbox
or against your actual live Supabase project.

## What's NOT here yet
- `fetch_drought_monitor.py` hasn't run against the real live source yet —
  confirm its URL first, same as any new pipeline.
- The scoring engine is still a rough client-side approximation in the
  frontend, not real weighted math against your actual scoring_weights table.
- Everything past these 3 layers in the 14-category taxonomy (~65 to go).
- Any public hosting beyond Supabase's own API — deliberately deferred.

## Setup
1. `docker compose up -d` — starts local Postgres+PostGIS and loads `schema.sql`
   (note: `policies.sql` needs real Supabase specifically — its RLS policies
   reference the `anon` role, which only exists on Supabase, not plain Postgres)
2. `pip install -r requirements.txt --break-system-packages`
3. Edit `etl/config.py` if needed — `TARGET_STATE_FIPS` defaults to Colorado (`08`)
4. Run the pipelines in order: `fetch_county_boundaries.py` →
   `fetch_fema_nri.py` → `fetch_drought_monitor.py`
5. In Supabase's SQL Editor, run `db/policies.sql` once
6. In `frontend/index.html`, fill in `SUPABASE_URL` and `SUPABASE_ANON_KEY`
   (Supabase dashboard → Connect button → Framework tab shows both)
7. Open `frontend/index.html` in a browser — it should show real data,
   confirmed by the top bar switching from "PROTOTYPE — SAMPLE DATA" to
   "LIVE DATA"

## Recommended: move the next ~65 layers into Claude Code
This sandbox has no real network access — every pipeline here was written
against documented source formats, not tested live, and gets its actual
proof from GitHub Actions running it for real. Claude Code, with real
internet access, can write and verify each new pipeline against its live
source directly, which is a meaningfully faster loop for the volume of
sources still ahead.
