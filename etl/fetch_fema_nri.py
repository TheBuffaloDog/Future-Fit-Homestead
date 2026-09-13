"""
Fetches FEMA National Risk Index via the official ArcGIS Feature Service.
This is the actual live data source behind the NRI web app. No key required.
Paginates through all ~3,200 US counties using ArcGIS's resultOffset parameter.
Category D (Natural Hazards), Tier 1.
"""
import json
import requests
from sqlalchemy import text
from common import clear_features, county_geom_by_fips, get_engine, upsert_layer

BASE_URL = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services"
    "/National_Risk_Index_Counties/FeatureServer/0/query"
)
LAYER_SLUG = "fema-nri-county"

FIELDS = "STCOFIPS,COUNTY,STATE,RISK_SCORE,RISK_RATNG,WFIR_RISKS,DRGT_RISKS,RFLD_RISKS,TRND_RISKS,HRCN_RISKS,ERQK_RISKS"

FIELD_MAP = {
    "STCOFIPS":  "fips",
    "COUNTY":    "county",
    "STATE":     "state",
    "RISK_SCORE": "composite_risk_score",
    "RISK_RATNG": "composite_risk_rating",
    "WFIR_RISKS": "wildfire_risk_score",
    "DRGT_RISKS": "drought_risk_score",
    "RFLD_RISKS": "riverine_flood_risk_score",
    "TRND_RISKS": "tornado_risk_score",
    "HRCN_RISKS": "hurricane_risk_score",
    "ERQK_RISKS": "earthquake_risk_score",
}


def fetch_all() -> list[dict]:
    all_records = []
    offset = 0
    page_size = 1000
    while True:
        print(f"Fetching records {offset} to {offset + page_size}...")
        resp = requests.get(BASE_URL, params={
            "where": "1=1",
            "outFields": FIELDS,
            "returnGeometry": "false",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": "json",
        }, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        if not features:
            break
        for feat in features:
            attrs = feat.get("attributes", {})
            rec = {dest: attrs.get(src, "") for src, dest in FIELD_MAP.items()}
            fips = (rec.get("fips") or "").strip()
            if fips:
                all_records.append(rec)
        print(f"  Got {len(features)}, total: {len(all_records)}")
        if len(features) < page_size:
            break
        offset += page_size
    return all_records


def load(records: list[dict]):
    engine = get_engine()
    with engine.begin() as conn:
        layer_id = upsert_layer(
            conn, slug=LAYER_SLUG, category="D",
            name="FEMA National Risk Index (county)",
            source_org="FEMA", source_url=BASE_URL,
            confidence_tier=1, data_kind="observed",
            vintage="2025-12-01", unit="index score 0-100",
        )
        clear_features(conn, layer_id)
        matched, unmatched = 0, 0
        for rec in records:
            fips = rec.get("fips", "").strip()
            geom = county_geom_by_fips(conn, fips)
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
    records = fetch_all()
    print(f"Total fetched: {len(records)}")
    load(records)
