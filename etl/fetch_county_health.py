"""
Fetches County Health Rankings data — Category L (Health & Community), Tier 1.
Published annually by Robert Wood Johnson Foundation / Univ. of Wisconsin.
Covers health outcomes, health behaviors, clinical care, social/economic factors.

Source: countyhealthrankings.org
"""
import io
import json
import zipfile

import requests
from sqlalchemy import text

from common import clear_features, county_geom_by_fips, get_engine, upsert_layer

SOURCE_URL = "https://www.countyhealthrankings.org/sites/default/files/media/document/analytic_data2024.csv"
LAYER_SLUG = "county-health-rankings"

KEEP_COLUMNS = {
    "fipscode": "fips",
    "county": "county",
    "state": "state",
    "v001_rawvalue": "premature_death_rate",
    "v002_rawvalue": "poor_or_fair_health_pct",
    "v009_rawvalue": "adult_smoking_pct",
    "v011_rawvalue": "adult_obesity_pct",
    "v042_rawvalue": "mental_health_providers_ratio",
    "v063_rawvalue": "median_household_income",
    "v044_rawvalue": "high_school_completion_pct",
    "v060_rawvalue": "uninsured_pct",
}


def fetch() -> str:
    print(f"Downloading {SOURCE_URL}")
    resp = requests.get(SOURCE_URL, timeout=60)
    resp.raise_for_status()
    return resp.text


def parse(raw_csv: str) -> list[dict]:
    import csv
    reader = csv.DictReader(io.StringIO(raw_csv))
    rows = []
    # Skip the first row which is a description row, not data
    for i, row in enumerate(reader):
        if i == 0:
            continue
        fips = (row.get("fipscode") or "").strip().zfill(5)
        if not fips or fips == "00000":
            continue
        rec = {dest: row.get(src, "") for src, dest in KEEP_COLUMNS.items()}
        rec["fips"] = fips
        rows.append(rec)
    return rows


def load(rows: list[dict]):
    engine = get_engine()
    with engine.begin() as conn:
        layer_id = upsert_layer(
            conn, slug=LAYER_SLUG, category="L",
            name="County Health Rankings (2024)",
            source_org="Robert Wood Johnson Foundation",
            source_url=SOURCE_URL,
            confidence_tier=1, data_kind="observed",
            vintage="2024-01-01",
            unit="various (rates, percentages, ratios)",
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
    load(parse(fetch()))
