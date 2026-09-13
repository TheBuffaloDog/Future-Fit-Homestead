"""
Fetches CDC Social Vulnerability Index — Category L (Health & Community), Tier 2.
Measures community capacity to withstand and recover from disasters.
Directly relevant: a low-SVI county has less community resilience buffer
if conditions deteriorate over the next 20-30 years.

Source: CDC/ATSDR Social Vulnerability Index
"""
import csv
import io
import json
import requests
from sqlalchemy import text
from common import clear_features, county_geom_by_fips, get_engine, upsert_layer

SOURCE_URL = "https://www.atsdr.cdc.gov/placeandhealth/svi/data_documentation_download.html"
DATA_URL = "https://svi.cdc.gov/Documents/Data/2022_SVI_Data/CSV/SVI2022_US_county.csv"
LAYER_SLUG = "cdc-social-vulnerability-index"

KEEP_COLUMNS = {
    "FIPS": "fips",
    "COUNTY": "county",
    "STATE": "state",
    "RPL_THEMES": "overall_svi",          # 0-1, higher = more vulnerable
    "RPL_THEME1": "socioeconomic_svi",
    "RPL_THEME2": "household_disability_svi",
    "RPL_THEME3": "minority_language_svi",
    "RPL_THEME4": "housing_transport_svi",
    "E_TOTPOP": "population",
}


def fetch() -> str:
    print(f"Downloading CDC SVI...")
    resp = requests.get(DATA_URL, timeout=60)
    resp.raise_for_status()
    return resp.text


def parse(raw_csv: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(raw_csv))
    rows = []
    for row in reader:
        fips = (row.get("FIPS") or "").strip().zfill(5)
        if not fips or fips == "00000":
            continue
        rec = {dest: row.get(src, "") for src, dest in KEEP_COLUMNS.items()}
        rec["fips"] = fips
        # -999 means no data in SVI — convert to empty string
        for k, v in rec.items():
            if v == "-999" or v == "-999.0":
                rec[k] = ""
        rows.append(rec)
    return rows


def load(rows: list[dict]):
    engine = get_engine()
    with engine.begin() as conn:
        layer_id = upsert_layer(
            conn, slug=LAYER_SLUG, category="L",
            name="CDC Social Vulnerability Index (2022)",
            source_org="CDC/ATSDR",
            source_url=DATA_URL,
            confidence_tier=2, data_kind="observed",
            vintage="2022-01-01",
            unit="percentile rank 0-1 (higher = more vulnerable)",
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
