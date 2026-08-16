-- Future-Fit Homestead — core schema
-- Implements Design Principles 2.1 (tier by forecastability) and 2.3 (confidence
-- & recency badges) from the project brief: every layer carries its own metadata,
-- not just a value, so the frontend can render tier honestly instead of showing
-- a 2050 projection with the same visual confidence as a live sensor feed.

CREATE EXTENSION IF NOT EXISTS postgis;

-- ── Layer catalog ────────────────────────────────────────────────────────────
-- One row per data source (~70+ once the full taxonomy is built out). This is
-- the thing the filter panel in the frontend actually renders from.
CREATE TABLE layers (
    id                SERIAL PRIMARY KEY,
    slug              TEXT UNIQUE NOT NULL,        -- 'fema-nri-county'
    category          TEXT NOT NULL,               -- 'A'..'N' per the taxonomy doc, or 'REF' for base reference geometry
    name              TEXT NOT NULL,
    source_org        TEXT NOT NULL,                -- 'FEMA', 'USDA NRCS', ...
    source_url        TEXT,
    confidence_tier   SMALLINT NOT NULL CHECK (confidence_tier IN (1, 2, 3)),
    data_kind         TEXT NOT NULL CHECK (data_kind IN ('observed', 'projected', 'live_feed')),
    vintage           DATE,                         -- when the underlying data was published
    forecast_epoch    TEXT,                         -- null for observed; 'near_term'|'mid_century'|'late_century' for projected
    unit              TEXT,
    cog_path          TEXT,                         -- populated for raster layers (climate/soil/elevation); points at a Cloud-Optimized GeoTIFF, NOT stored in this table
    license            TEXT,
    last_ingested_at  TIMESTAMPTZ,
    notes             TEXT
);

-- ── Generic vector feature store ────────────────────────────────────────────
-- Points/lines/polygons for every vector layer land here, keyed to the catalog
-- above. Deliberately generic (properties as JSONB) rather than one table per
-- data source — the taxonomy already has 14 categories and keeps growing
-- (Category E got added mid-conversation), and a per-source table means a
-- migration every time. This trades some query ergonomics for not needing a
-- schema change every time a new layer gets added.
CREATE TABLE features (
    id          BIGSERIAL PRIMARY KEY,
    layer_id    INTEGER NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
    geom        GEOMETRY(Geometry, 4326) NOT NULL,
    properties  JSONB NOT NULL DEFAULT '{}',
    valid_from  DATE,             -- for time-slider support (3.6 in the brief)
    valid_to    DATE
);
CREATE INDEX features_geom_idx ON features USING GIST (geom);
CREATE INDEX features_layer_idx ON features (layer_id);
CREATE INDEX features_properties_idx ON features USING GIN (properties);

-- ── Personal scoring engine ─────────────────────────────────────────────────
-- Design Principle 2.4: transparent, user-adjustable weights, never a black-box
-- score. Multiple named profiles so "off-grid homestead" and "family relocation
-- with kids in school" can coexist.
CREATE TABLE scoring_profiles (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scoring_weights (
    profile_id  INTEGER NOT NULL REFERENCES scoring_profiles(id) ON DELETE CASCADE,
    layer_id    INTEGER NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
    weight      NUMERIC NOT NULL DEFAULT 1.0,
    PRIMARY KEY (profile_id, layer_id)
);

-- ── Watchlist ────────────────────────────────────────────────────────────────
-- Micro-mode (Design Principle 2.5): specific parcels you're actually evaluating.
CREATE TABLE watchlist_parcels (
    id          SERIAL PRIMARY KEY,
    label       TEXT,
    geom        GEOMETRY(Point, 4326) NOT NULL,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
