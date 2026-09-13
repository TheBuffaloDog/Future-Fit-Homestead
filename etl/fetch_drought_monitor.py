"""Fetches US Drought Monitor county stats via NDMC's real REST API
(usdmdataservices.unl.edu) — the actual data endpoint, not the download
page this pointed at before. Category B, Tier 1."""
import csv
import io
import json
from datetime import date, timedelta

from sqlalchemy import text

from common import (clear_features, county_geom_by_fips, fetch_and_cache,
                     get_engine, upsert_layer)
from config import RAW_DATA_CACHE_DIR, TARGET_STATE_ABBR

END = date.today()
START = END - timedelta(days=14)
SOURCE_URL = (
    f"https://usdmdataservices.unl.edu/api/CountyStatistics/"
    f"GetDroughtSeverityStatisticsByAreaPercent?aoi={TARGET_STATE_ABBR}"
    f"&startdate={START.month}/{START.day}/{START.year}"
    f"&enddate={END.month}/{END.day}/{END.year}&statisticsType=1"
)
LAYER_SLUG = "usdm-drought-county"

KEEP_COLUMNS = {
    "FIPS": "fips", "County": "county", "State": "state", "ValidStart": "week_of",
    "None": "pct_no_drought", "D0": "pct_abnormally_dry", "D1": "pct_moderate_drought",
    "D2": "pct_severe_drought", "D3": "pct_extreme_drought", "D4": "pct_exceptional_drought",
}


def parse(raw_csv: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(raw_csv))
    print(f"Columns returned: {reader.fieldnames}")
    latest = {}
    for row in reader:
        fips = (row.get("FIPS") or "").strip()
        if not fips:
            continue
        rec = {dest: row.get(src, "") for src, dest in KEEP_COLUMNS.items()}
        rec["fips"] = fips
        latest[fips] = rec
    return list(latest.values())


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
                text("INSERT INTO features (layer_id, geom, properties) VALUES (:lid, :geom, CAST(:props AS JSONB))"),
                {"lid": layer_id, "geom": geom, "props": json.dumps(rec)},
            )
            matched += 1
    print(f"Loaded {matched} counties ({unmatched} unmatched)")


if __name__ == "__main__":
    raw = fetch_and_cache(SOURCE_URL, f"{RAW_DATA_CACHE_DIR}/usdm_{TARGET_STATE_ABBR}_{END.isoformat()}.csv", binary=False)
    load(parse(raw))
