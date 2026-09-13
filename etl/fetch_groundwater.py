"""
Fetches USGS groundwater level data — Category B (Water Resources), Tier 2.
Pulls the most recent groundwater depth measurements from USGS's
National Water Information System (NWIS) for all US counties.

Source: USGS National Water Information System
"""
import json
import requests
from sqlalchemy import text
from common import clear_features, county_geom_by_fips, get_engine, upsert_layer

# USGS groundwater statistics by county — median depth to water table
SOURCE_URL = "https://waterservices.usgs.gov/nwis/gwlevels/?format=rdb&statCd=50000&siteType=GW&startDT=2023-01-01&endDT=2024-12-31&siteStatus=active"
LAYER_SLUG = "usgs-groundwater-levels"


def fetch() -> list[dict]:
    print(f"Downloading USGS groundwater data...")
    resp = requests.get(SOURCE_URL, timeout=120)
    resp.raise_for_status()
    lines = resp.text.splitlines()
    data_lines = [l for l in lines if not l.startswith("#") and l.strip()]
    if len(data_lines) < 3:
        print("No data returned")
        return []
    headers = data_lines[0].split("\t")
    print(f"USGS headers: {headers[:10]}")  # debug — show first 10 column names
    seen_fips = {}
    for line in data_lines[2:]:
        fields = line.split("\t")
        if len(fields) < len(headers):
            continue
        row = dict(zip(headers, fields))
        # USGS RDB uses site_no which encodes state+county differently
        # Try common field names
        county_cd = (row.get("county_cd") or row.get("county") or "").strip()
        state_cd = (row.get("state_cd") or row.get("state") or "").strip()
        fips = f"{state_cd}{county_cd}".zfill(5)
        if not fips or len(fips) != 5:
            continue
        lev_va = (row.get("lev_va") or row.get("value") or "").strip()
        if not lev_va:
            continue
        try:
            depth = float(lev_va)
        except ValueError:
            continue
        if fips not in seen_fips:
            seen_fips[fips] = []
        seen_fips[fips].append(depth)

    records = []
    for fips, depths in seen_fips.items():
        median = sorted(depths)[len(depths) // 2]
        records.append({
            "fips": fips,
            "median_depth_ft": round(median, 1),
            "measurement_count": len(depths),
        })
    print(f"Parsed {len(records)} counties with groundwater data")
    return records


def load(rows: list[dict]):
    engine = get_engine()
    with engine.begin() as conn:
        layer_id = upsert_layer(
            conn, slug=LAYER_SLUG, category="B",
            name="USGS Groundwater Levels (county median)",
            source_org="USGS National Water Information System",
            source_url=SOURCE_URL,
            confidence_tier=2, data_kind="observed",
            vintage=None,
            unit="feet below land surface (median)",
            notes="Median of active monitoring wells per county, 2023-2024",
        )
        clear_features(conn, layer_id)
        matched, unmatched = 0, 0
        for rec in rows:
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
    load(fetch())
