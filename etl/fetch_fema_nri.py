"""
Fetches FEMA's National Risk Index (county level) and loads it as a Tier-1
Natural Hazards layer (Category D in the taxonomy doc): a composite risk score
plus per-hazard scores across 18 hazard types. Current release: NRI December
2025, v1.20.

Run fetch_county_boundaries.py FIRST — this script joins NRI's attribute data
onto the boundary geometry already in the database rather than carrying its
own polygons.

NOTE ON THIS SOURCE SPECIFICALLY: FEMA retired the standalone NRI web
*application*; the underlying data downloads are still published through
OpenFEMA / hazards.fema.gov/nri/data-resources. This is a live example of
exactly the "the front door moves, the data usually survives" problem the
project brief calls out re: EJScreen — confirm SOURCE_URL against that page
before running.
"""
import csv
import io
import json
import os

import requests
from sqlalchemy import create_engine, text

from config import DATABASE_URL, RAW_DATA_CACHE_DIR, TARGET_STATE_FIPS

NRI_VERSION = "v1.20"
# Verify current link at https://hazards.fema.gov/nri/data-resources before running.
SOURCE_URL = "https://hazards.fema.gov/nri/Content/StaticDocuments/DataDownload/NRI_Table_Counties/NRI_Table_Counties.csv"
LAYER_SLUG = "fema-nri-county"

# The real file has ~130 columns (composite score + score/rating/expected-annual-
# loss per hazard). This is a starting subset — confirm exact column names
# against the NRI Technical Documentation / Data Dictionary, since these are
# recalled from general familiarity with the dataset, not verified against a
# live copy of the current release.
KEEP_COLUMNS = {
    "STCOFIPS": "fips",
    "COUNTY": "county",
    "STATE": "state",
    "RISK_SCORE": "composite_risk_score",
    "RISK_RATNG": "composite_risk_rating",
    "WFIR_RISKS": "wildfire_risk_score",
    "DRGT_RISKS": "drought_risk_score",
    "RFLD_RISKS": "riverine_flood_risk_score",
    "TRND_RISKS": "tornado_risk_score",
    "HRCN_RISKS": "hurricane_risk_score",
}


def fetch_and_cache() -> str:
    cache_path = f"{RAW_DATA_CACHE_DIR}/nri_counties_{NRI_VERSION}.csv"
    if os.path.exists(cache_path):
        print(f"Using cached copy at {cache_path}")
        with open(cache_path, "r", encoding="utf-8-sig") as f:
            return f.read()

    print(f"Downloading {SOURCE_URL}")
    resp = requests.get(SOURCE_URL, timeout=60)
    resp.raise_for_status()
    os.makedirs(RAW_DATA_CACHE_DIR, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(resp.text)
    return resp.text


def parse(raw_csv: str) -> list[dict]:
    """Split out from fetch_and_cache() on purpose: this is the part testable
    without a network call — see test_parse.py."""
    reader = csv.DictReader(io.StringIO(raw_csv))
    rows = []
    for row in reader:
        fips = (row.get("STCOFIPS") or "").strip()
        if not fips:
            continue
        if TARGET_STATE_FIPS and not fips.startswith(TARGET_STATE_FIPS):
            continue
        record = {dest: row.get(src, "") for src, dest in KEEP_COLUMNS.items()}
        record["fips"] = fips
        rows.append(record)
    return rows


def load(rows: list[dict]):
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        layer_id = conn.execute(
            text(
                """
                INSERT INTO layers (slug, category, name, source_org, source_url,
                                     confidence_tier, data_kind, vintage, unit, license)
                VALUES (:slug, 'D', 'FEMA National Risk Index (county)', 'FEMA', :url,
                        1, 'observed', :vintage, 'index score 0-100', 'Public domain')
                ON CONFLICT (slug) DO UPDATE SET last_ingested_at = now()
                RETURNING id
                """
            ),
            {"slug": LAYER_SLUG, "url": SOURCE_URL, "vintage": "2025-12-01"},
        ).scalar_one()

        conn.execute(text("DELETE FROM features WHERE layer_id = :lid"), {"lid": layer_id})

        matched, unmatched = 0, 0
        for rec in rows:
            geom = conn.execute(
                text(
                    """
                    SELECT geom FROM features f
                    JOIN layers l ON l.id = f.layer_id
                    WHERE l.slug = 'census-county-boundaries'
                      AND f.properties ->> 'fips' = :fips
                    """
                ),
                {"fips": rec["fips"]},
            ).scalar_one_or_none()

            if geom is None:
                unmatched += 1
                continue

            conn.execute(
                text(
                    """
                    INSERT INTO features (layer_id, geom, properties)
                    VALUES (:lid, :geom, CAST(:props AS JSONB))
                    """
                ),
                {"lid": layer_id, "geom": geom, "props": json.dumps(rec)},
            )
            matched += 1

    print(
        f"Loaded {matched} counties into '{LAYER_SLUG}' "
        f"({unmatched} had no matching boundary — run fetch_county_boundaries.py first)"
    )


if __name__ == "__main__":
    load(parse(fetch_and_cache()))
