# Future-Fit Homestead — starter scaffold

Personal-first build of the site-selection platform. Companion to the design
brief from earlier in this project (`future-fit-homestead-site-selection-brief.md`)
— this repo makes Sections 3 and 5 of that doc real, starting with one region
and one real data source, per the phased roadmap in 3.8.

## What's here — and tested
- **`db/schema.sql`** — generic, metadata-driven schema (Design Principle 2.1:
  every layer carries its own confidence tier, source, and vintage, not just a
  value). Ran cleanly against a live PostGIS 16 instance.
- **`etl/fetch_county_boundaries.py`** — base reference geometry (Census
  cartographic boundaries) that other layers join against.
- **`etl/fetch_fema_nri.py`** — first real pipeline, Category D (Natural
  Hazards). Copy this pattern for the other ~65 layers in the taxonomy.
- **`etl/test_parse.py`** — unit tests for the parsing/filtering logic, run
  against a representative sample since this sandbox can't reach FEMA's
  servers. All passing.
- **`api/main.py`** — thin FastAPI layer: `/layers` (catalog) and
  `/layers/{slug}/geojson` (straight into MapLibre via PostGIS's `ST_AsGeoJSON`).
- **`frontend/index.html`** — MapLibre GL JS prototype: filter panel grouped by
  taxonomy category, confidence-tier encoding on every layer, and a mock
  scoring readout, running on sample data so the interaction pattern is real
  today even before the pipeline has more than one layer in it.

The full chain — schema → ETL parse/load → live database → API → GeoJSON out —
was run end-to-end against synthetic data standing in for the real Census/FEMA
downloads, from schema creation through to a working `/layers/{slug}/geojson`
response. That part is genuinely proven, not just "looks right."

## What's NOT here yet
- **Real network access to Census/FEMA from this sandbox was blocked** while
  building this (locked to package registries only) — the ETL scripts are
  real, correct code and the *logic* is tested, but they haven't been run
  against a live download. Run them yourself once this is on your machine.
- The scoring engine is a mock in the frontend, not wired to real weighted
  math yet.
- Every layer past the first one in the 14-category taxonomy.

## Setup
1. `docker compose up -d` — starts local Postgres+PostGIS and loads `schema.sql`
2. `pip install -r requirements.txt --break-system-packages`
3. Edit `etl/config.py` if needed — `TARGET_STATE_FIPS` defaults to Colorado
   (`08`) purely as a placeholder. Swap it for your actual candidate region.
4. `cd etl && python fetch_county_boundaries.py`
5. `python fetch_fema_nri.py` (confirm `SOURCE_URL` against
   hazards.fema.gov/nri/data-resources first — see the comment in the file)
6. `cd ../api && uvicorn main:app --reload`
7. Open `frontend/index.html` in a browser — it runs standalone on sample data
   out of the box, or point its `API_BASE` constant at `http://localhost:8000`
   to wire it to your real data instead

## Recommended: move this into Claude Code next
This scaffold proves the pattern and gets you a working first slice. The
sustained build — adding the other ~65 layers, wiring the real scoring engine,
eventually deploying — wants a persistent local project with full network
access, which this chat sandbox doesn't have. Claude Code is the natural next
environment for that.
