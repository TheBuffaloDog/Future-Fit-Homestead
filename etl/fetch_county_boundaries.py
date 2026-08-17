"""
Fetches US county boundaries (Census cartographic boundary file, 1:500,000
scale) and loads them as the base reference geometry — other layers (like
fetch_fema_nri.py) join against this rather than carrying their own polygons.

Source: US Census Bureau Cartographic Boundary Files
Docs:   https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html
Verified working as of this build: cb_2025_us_county_500k.zip
"""
import io
import json

import geopandas as gpd
from sqlalchemy import text

from common import clear_features, fetch_and_cache, get_engine, upsert_layer
from config import RAW_DATA_CACHE_DIR, TARGET_STATE_FIPS

VINTAGE_YEAR = 2025  # confirmed working at https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip
BOUNDARY_URL = f"https://www2.census.gov/geo/tiger/GENZ{VINTAGE_YEAR}/shp/cb_{VINTAGE_YEAR}_us_county_500k.zip"
LAYER_SLUG = "census-county-boundaries"


def load_geometries(raw_zip: bytes) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(io.BytesIO(raw_zip))
    gdf = gdf.to_crs(epsg=4326)
    if TARGET_STATE_FIPS:
        gdf = gdf[gdf["STATEFP"] == TARGET_STATE_FIPS]
    return gdf


def load(gdf: gpd.GeoDataFrame):
    engine = get_engine()
    with engine.begin() as conn:
        layer_id = upsert_layer(
            conn, slug=LAYER_SLUG, category="REF", name="County Boundaries",
            source_org="US Census Bureau", source_url=BOUNDARY_URL, confidence_tier=1,
            data_kind="observed", vintage=f"{VINTAGE_YEAR}-01-01", unit="polygon",
        )
        clear_features(conn, layer_id)

        for _, row in gdf.iterrows():
            conn.execute(
                text(
                    "INSERT INTO features (layer_id, geom, properties) "
                    "VALUES (:lid, ST_GeomFromText(:wkt, 4326), CAST(:props AS JSONB))"
                ),
                {
                    "lid": layer_id,
                    "wkt": row.geometry.wkt,
                    "props": json.dumps({
                        "fips": row["GEOID"], "name": row["NAME"], "state_fips": row["STATEFP"],
                    }),
                },
            )
    print(f"Loaded {len(gdf)} counties into '{LAYER_SLUG}' (layer id {layer_id})")


if __name__ == "__main__":
    raw = fetch_and_cache(BOUNDARY_URL, f"{RAW_DATA_CACHE_DIR}/cb_{VINTAGE_YEAR}_us_county_500k.zip", binary=True)
    load(load_geometries(raw))
