"""
Fetches CDC Social Vulnerability Index via CDC's own ArcGIS FeatureServer.
Category L (Health & Community), Tier 2.
"""
import json
import requests
from sqlalchemy import text
from common import clear_features, county_geom_by_fips, get_engine, upsert_layer

BASE_URL = (
    "https://onemap.cdc.gov/onemapservices/rest/services/SVI/"
    "CDC_ATSDR_Social_Vulnerability_Index_2022_USA/FeatureServer/1/query"
)
LAYER_SLUG = "cdc-social-vulnerability-index"

FIELDS = "FIPS,COUNTY,STATE,RPL_THEMES,RPL_THEME1,RPL_THEME2,RPL_THEME3,RPL_THEME4,E_TOTPOP"

FIELD_MAP = {
    "FIPS": "fips",
    "COUNTY": "county",
    "STATE": "state",
    "RPL_THEMES": "overall_svi",
    "RPL_THEME1": "socioeconomic_svi",
    "RPL_THEME2": "household_disability_svi",
    "RPL_THEME3": "minority_language_svi",
    "RPL_THEME4": "housing_transport_svi",
    "E_TOTPOP": "population",
}


def fetch_all() -> list[dict]:
    all_records = []
    offset = 0
    page_size = 2000
    while True:
        print(f"Fetching
