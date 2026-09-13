"""Fetches US Drought Monitor county stats for all 50 states via NDMC REST API.
Loops state by state since the API doesn't support a national county pull."""
import csv
import io
import json
from datetime import date, timedelta

from sqlalchemy import text

from common import (clear_features, county_geom_by_fips, fetch_and_cache,
                     get_engine, upsert_layer)
from config import RAW_DATA_CACHE_DIR

END = date.today()
START = END - timedelta(days=14)
LAYER_SLUG = "usdm-drought-county"

ALL_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA",
    "HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
    "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
    "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
]


def fetch_state(abbr: str) -> list[dict]:
    url = (
        f"https://usdmdataservices.unl.edu/api/CountyStatistics/"
        f"GetDroughtSeverityStatisticsByAreaPercent?aoi={abbr}"
        f"&startdate={START.month}/{START.day}/{START.year}"
        f"&enddate={END.month}/{END.day}/{END.year}&statisticsType=1"
    )
    import requests
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    latest = {}
    for row in reader:
        fips = (row.get("FIPS") or "").strip()
        if not fips:
            continue
        latest[fips] = {
            "fips": fips,
            "county": row.get("County", ""),
            "state": row.get("State", ""),
            "week_of": row.get("ValidStart", ""),
            "pct_no_drought": row.get("None", ""),
            "pct_abnormally_dry": row.get("D0", ""),
            "pct_moderate_drought": row.get("D1", ""),
            "pct_severe_drought": row.get("D2", ""),
            "pct_extreme_drought": row.get("D3", ""),
            "pct_exceptional_drought": row.get("D4", ""),
        }
    return list(latest.values())


def load(all_rows: list[dict]):
    engine = get_engine()
    with engine.begin() as conn:
        layer_id = upsert_layer(
            conn, slug=LAYER_SLUG, category="B",
            name="US Drought Monitor (county)",
            source_org="National Drought Mitigation Center",
            source_url="https://usdmdataservices.unl.edu/api/CountyStatistics/",
            confidence_tier=1, data_kind="observed", vintage=None,
            unit="percent of county area", notes="Updated weekly, Thursdays",
        )
        clear_features(conn, layer_id)
        matched, unmatched = 0, 0
        for rec in all_rows:
            geom = county_geom_by_fips(conn, rec["fips"])
            if geom is None:
                unmatched += 1
                continue
            conn.execute(
                text("INSERT INTO features (layer_id, geom, properties) "
                     "VALUES (:lid, :geom, CAST(:props AS JSONB))"),
                {"lid": layer_id, "geom": geom, "props": json.dumps(rec)},
            )
            matched += 1
    print(f"Loaded {matched} counties ({unmatched} unmatched)")


if __name__ == "__main__":
    all_rows = []
    for abbr in ALL_STATES:
        print(f"Fetching {abbr}...")
        try:
            rows = fetch_state(abbr)
            all_rows.extend(rows)
            print(f"  {len(rows)} counties")
        except Exception as e:
            print(f"  ERROR: {e}")
    print(f"Total: {len(all_rows)} counties across all states")
    load(all_rows)
