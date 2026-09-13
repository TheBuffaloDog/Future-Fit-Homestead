"""
Fetches USDA Plant Hardiness Zone (PHZ) data — Category A (Climate & Weather),
Tier 1. The 2023 update (first since 2012) already shows real warming — about
half the US shifted warmer by a half-zone. Directly relevant to growing season
and farming viability.

Source: USDA Agricultural Research Service
Download: https://planthardiness.ars.usda.gov/downloads/
"""
import io
import json
import zipfile

import geopandas as gpd
from sqlalchemy import text

from common import clear_features, fetch_and_cache, get_engine, upsert_layer

SOURCE_URL = "SOURCE_URL = "https://prism.oregonstate.edu/phzm/data/2023/phzm_us_zones_shp_2023.zip""
LAYER_SLUG = "usda-plant-hardiness-zone"


def load_zones(raw_zip: bytes) -> gpd.GeoDataFrame:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as z:
        # Find the shapefile inside the zip
        shp_files = [f for f in z.namelist() if f.endswith(".shp")]
        print(f"Found shapefiles: {shp_files}")
        if not shp_files:
            raise ValueError("No shapefile found in zip")
        shp_name = shp_files[0]
        # Extract all related files to a temp location
        z.extractall("/tmp/phz/")
    gdf = gpd.read_file(f"/tmp/phz/{shp_name}")
    gdf = gdf.to_crs(epsg=4326)
    print(f"Loaded {len(gdf)} zone polygons, columns: {list(gdf.columns)}")
    return gdf


def load(gdf: gpd.GeoDataFrame):
    engine = get_engine()
    with engine.begin() as conn:
        layer_id = upsert_layer(
            conn, slug=LAYER_SLUG, category="A",
            name="USDA Plant Hardiness Zone (2023)",
            source_org="USDA Agricultural Research Service",
            source_url=SOURCE_URL,
            confidence_tier=1, data_kind="observed",
            vintage="2023-11-01",
            unit="zone (e.g. 6b)",
            notes="Updated Nov 2023, first update since 2012. ~half of US shifted warmer by half-zone.",
        )
        clear_features(conn, layer_id)
        loaded = 0
        for _, row in gdf.iterrows():
            props = {
                col: str(row[col])
                for col in gdf.columns
                if col != "geometry" and row[col] is not None
            }
            conn.execute(
                text(
                    "INSERT INTO features (layer_id, geom, properties) "
                    "VALUES (:lid, ST_GeomFromText(:wkt, 4326), CAST(:props AS JSONB))"
                ),
                {"lid": layer_id, "wkt": row.geometry.wkt, "props": json.dumps(props)},
            )
            loaded += 1
        print(f"Loaded {loaded} zone polygons into '{LAYER_SLUG}'")


if __name__ == "__main__":
    raw = fetch_and_cache(SOURCE_URL, "/tmp/phz_download.zip", binary=True)
    load(load_zones(raw))
