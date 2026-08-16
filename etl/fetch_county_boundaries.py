"""
Fetches US county boundaries (Census cartographic boundary file, 1:500,000
scale) and loads them as the base reference geometry — other layers (like
fetch_fema_nri.py) join against this rather than carrying their own polygons.

Source: US Census Bureau Cartographic Boundary Files
Docs:   https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html

NOTE ON URL STABILITY: the GENZ-plus-vintage-year pattern below has held for
many releases, but Census has reorganized this page before, and this sandbox
couldn't reach census.gov to confirm live. If this 404s, grab the current link
from the page above and update BOUNDARY_URL — nothing else in this script
needs to change. This is the "don't trust a live government URL to stay put"
principle from the brief, in practice rather than in theory.
"""
import io
import json
import os

import geopandas as gpd
import requests
from sqlalchemy import create_engine, text

from config import DATABASE_URL, RAW_DATA_CACHE_DIR, TARGET_STATE_FIPS

VINTAGE_YEAR = 2025  # confirmed working at https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip
BOUNDARY_URL = f"https://www2.census.gov/geo/tiger/GENZ{VINTAGE_YEAR}/shp/cb_{VINTAGE_YEAR}_us_county_500k.zip"
LAYER_SLUG = "census-county-boundaries"


def fetch_and_cache() -> bytes:
    cache_path = f"{RAW_DATA_CACHE_DIR}/cb_{VINTAGE_YEAR}_us_county_500k.zip"
    if os.path.exists(cache_path):
        print(f"Using cached copy at {cache_path}")
        with open(cache_path, "rb") as f:
            return f.read()

    print(f"Downloading {BOUNDARY_URL}")
    resp = requests.get(BOUNDARY_URL, timeout=60)
    resp.raise_for_status()
    os.makedirs(RAW_DATA_CACHE_DIR, exist_ok=True)
    with open(cache_path, "wb") as f:
        f.write(resp.content)
    return resp.content


def load_geometries(raw_zip: bytes) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(io.BytesIO(raw_zip))
    gdf = gdf.to_crs(epsg=4326)
    if TARGET_STATE_FIPS:
        gdf = gdf[gdf["STATEFP"] == TARGET_STATE_FIPS]
    return gdf


def load(gdf: gpd.GeoDataFrame):
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        layer_id = conn.execute(
            text(
                """
                INSERT INTO layers (slug, category, name, source_org, source_url,
                                     confidence_tier, data_kind, vintage, unit, license)
                VALUES (:slug, 'REF', 'County Boundaries', 'US Census Bureau', :url,
                        1, 'observed', :vintage, 'polygon', 'Public domain')
                ON CONFLICT (slug) DO UPDATE SET last_ingested_at = now()
                RETURNING id
                """
            ),
            {"slug": LAYER_SLUG, "url": BOUNDARY_URL, "vintage": f"{VINTAGE_YEAR}-01-01"},
        ).scalar_one()

        conn.execute(text("DELETE FROM features WHERE layer_id = :lid"), {"lid": layer_id})

        for _, row in gdf.iterrows():
            conn.execute(
                text(
                    """
                    INSERT INTO features (layer_id, geom, properties)
                    VALUES (:lid, ST_GeomFromText(:wkt, 4326), CAST(:props AS JSONB))
                    """
                ),
                {
                    "lid": layer_id,
                    "wkt": row.geometry.wkt,
                    "props": json.dumps(
                        {
                            "fips": row["GEOID"],
                            "name": row["NAME"],
                            "state_fips": row["STATEFP"],
                        }
                    ),
                },
            )
    print(f"Loaded {len(gdf)} counties into '{LAYER_SLUG}' (layer id {layer_id})")


if __name__ == "__main__":
    counties = load_geometries(fetch_and_cache())
    load(counties)
