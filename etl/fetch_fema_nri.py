"""
Fetches FEMA National Risk Index via the OpenFEMA API — the programmatic
access endpoint that replaced the direct CSV download. Paginates through
all ~3,200 US counties automatically.
Category D (Natural Hazards), Tier 1.
"""
import json
import requests
from sqlalchemy import text
from common import (clear_features, county_geom_by_fips, fetch_and_cache,
                     get_engine, upsert_layer)

SOURCE_URL = "https://www.fema.gov/api/open/v2/NriCounty"
LAYER_SLUG = "fema-nri-county"

KEEP_FIELDS = {
    "stcofips": "fips",
    "county": "county",
    "statefips": "state_fips",
    "riskScore": "composite_risk_score",
    "riskRatng": "composite_risk_rating",
    "wfirRisks": "wildfire_risk_score",
    "drgtRisks": "drought_risk_score",
    "rfldRisks": "riverine_flood_risk_score",
    "trndRisks": "tornado_risk_score",
    "hrcnRisks": "hurricane_risk_score",
    "erqkRisks": "earthquake_risk_score",
}


def fetch_all() -> list[dict]:
    all_records = []
    top = 1000
    skip = 0
    while True:
        url = f"{SOURCE_URL}?$top={top}&$skip={skip}&$format=json&$select={','.join(KEEP_FIELDS.keys())}"
        print(f"Fetching records {skip} to {skip + top}...")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        records = data.get("NriCounty", [])
        if not records:
            break
        all_records.extend(records)
        print(f"  Got {len(records)} records, total so far: {len(all_records)}")
        if len(records) < top:
            break
        skip += top
    return all_records


def load(records: list[dict]):
    engine = get_engine()
    with engine.begin() as conn:
        layer_id = upsert_layer(
            conn, slug=LAYER_SLUG, category="D",
            name="FEMA National Risk Index (county)",
            source_org="FEMA", source_url=SOURCE_URL,
            confidence_tier=1, data_kind="observed",
            vintage="2025-12-01", unit="index score 0-100",
        )
        clear_features(conn, layer_id)
        matched, unmatched = 0, 0
        for rec in records:
            fips = (rec.get("stcofips") or "").strip()
            if not fips:
                continue
            props = {dest: rec.get(src, "") for src, dest in KEEP_FIELDS.items()}
            props["fips"] = fips
            geom = county_geom_by_fips(conn, fips)
            if geom is None:
                unmatched += 1
                continue
            conn.execute(
                text("INSERT INTO features (layer_id, geom, properties) "
                     "VALUES (:lid, :geom, CAST(:props AS JSONB))"),
                {"lid": layer_id, "geom": geom, "props": json.dumps(props)},
            )
            matched += 1
    print(f"Loaded {matched} counties ({unmatched} unmatched)")


if __name__ == "__main__":
    records = fetch_all()
    print(f"Total fetched: {len(records)}")
    load(records)
