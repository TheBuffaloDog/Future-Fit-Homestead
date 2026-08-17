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

from sqlalchemy import text

from common import (clear_features, county_geom_by_fips, fetch_and_cache,
                     get_engine, upsert_layer)
from config import RAW_DATA_CACHE_DIR, TARGET_STATE_FIPS

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


def parse(raw_csv: str) -> list[dict]:
    """Split out on purpose: this is the part testable without a network
    call — see test_parse.py."""
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
    engine = get_engine()
    with engine.begin() as conn:
        layer_id = upsert_layer(
            conn, slug=LAYER_SLUG, category="D", name="FEMA National Risk Index (county)",
            source_org="FEMA", source_url=SOURCE_URL, confidence_tier=1,
            data_kind="observed", vintage="2025-12-01", unit="index score 0-100",
        )
        clear_features(conn, layer_id)

        matched, unmatched = 0, 0
        for rec in rows:
            geom = county_geom_by_fips(conn, rec["fips"])
            if geom is None:
                unmatched += 1
                continue
            conn.execute(
                text(
                    "INSERT INTO features (layer_id, geom, properties) "
                    "VALUES (:lid, :geom, CAST(:props AS JSONB))"
                ),
                {"lid": layer_id, "geom": geom, "props": json.dumps(rec)},
            )
            matched += 1

    print(
        f"Loaded {matched} counties into '{LAYER_SLUG}' "
        f"({unmatched} had no matching boundary — run fetch_county_boundaries.py first)"
    )


if __name__ == "__main__":
    raw = fetch_and_cache(SOURCE_URL, f"{RAW_DATA_CACHE_DIR}/nri_counties_{NRI_VERSION}.csv", binary=False)
    load(parse(raw))
