"""
Fetches US Drought Monitor county-level statistics — a Tier 1-2 water/climate
layer, Category B. Weekly data, five drought categories (D0 abnormally dry
through D4 exceptional drought) as percent of county area.

Source: National Drought Mitigation Center (droughtmonitor.unl.edu), a joint
NDMC/USDA/NOAA product. Verify the exact county-statistics endpoint at
droughtmonitor.unl.edu/DmData/DataDownload/ComprehensiveStatistics.aspx before
running — there's a documented "USDM REST services" option per NDMC, but this
sandbox couldn't reach the site to confirm the exact request format, same
caveat as every other source built in this sandbox rather than in an
environment with real network access.

This is the second pipeline built directly on common.py (after the FEMA NRI
refactor) — notice how much shorter it is than the original FEMA script,
which is the whole point of extracting that template.
"""
import csv
import io
import json

from sqlalchemy import text

from common import (clear_features, county_geom_by_fips, fetch_and_cache,
                     get_engine, upsert_layer)
from config import RAW_DATA_CACHE_DIR, TARGET_STATE_FIPS

# Verify against droughtmonitor.unl.edu/DmData/DataDownload/ComprehensiveStatistics.aspx
SOURCE_URL = "https://droughtmonitor.unl.edu/DmData/DataDownload/ComprehensiveStatistics.aspx"
LAYER_SLUG = "usdm-drought-county"

# Expected shape based on NDMC's documented county statistics format — confirm
# exact column names against a real downloaded file before relying on this.
KEEP_COLUMNS = {
    "FIPS": "fips",
    "County": "county",
    "State": "state",
    "ValidStart": "week_of",
    "None": "pct_no_drought",
    "D0": "pct_abnormally_dry",
    "D1": "pct_moderate_drought",
    "D2": "pct_severe_drought",
    "D3": "pct_extreme_drought",
    "D4": "pct_exceptional_drought",
}


def parse(raw_csv: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(raw_csv))
    rows = []
    for row in reader:
        fips = (row.get("FIPS") or "").strip()
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
            conn, slug=LAYER_SLUG, category="B", name="US Drought Monitor (county)",
            source_org="National Drought Mitigation Center", source_url=SOURCE_URL,
            confidence_tier=1, data_kind="observed", vintage=None,
            unit="percent of county area", notes="Updated weekly, Thursdays",
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
    raw = fetch_and_cache(SOURCE_URL, f"{RAW_DATA_CACHE_DIR}/usdm_counties.csv", binary=False)
    load(parse(raw))
