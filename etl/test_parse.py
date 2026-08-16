"""
Validates parse() against a small hand-built sample shaped like a real NRI
export, since this sandbox can't reach hazards.fema.gov to test against the
live file. Run this after any change to KEEP_COLUMNS or the filter logic,
and again for real once you've got an actual downloaded copy of the CSV.
"""
import fetch_fema_nri as nri

SAMPLE_CSV = """STCOFIPS,COUNTY,STATE,RISK_SCORE,RISK_RATNG,WFIR_RISKS,DRGT_RISKS,RFLD_RISKS,TRND_RISKS,HRCN_RISKS
08069,Larimer,Colorado,42.1,Relatively Moderate,61.3,55.0,20.1,18.4,0.0
08013,Boulder,Colorado,38.7,Relatively Moderate,58.9,52.1,25.6,17.9,0.0
48201,Harris,Texas,71.4,Relatively High,10.2,44.0,68.9,30.1,55.2
"""


def test_parse_filters_to_target_state():
    nri.TARGET_STATE_FIPS = "08"  # Colorado, matches config.py's placeholder
    rows = nri.parse(SAMPLE_CSV)
    assert len(rows) == 2, f"expected 2 Colorado counties, got {len(rows)}"
    assert {r["county"] for r in rows} == {"Larimer", "Boulder"}
    print("PASS: filters to target state")


def test_parse_maps_columns_correctly():
    nri.TARGET_STATE_FIPS = None  # no filter, check all 3 rows parse
    rows = nri.parse(SAMPLE_CSV)
    assert len(rows) == 3
    harris = next(r for r in rows if r["county"] == "Harris")
    assert harris["wildfire_risk_score"] == "10.2"
    assert harris["composite_risk_rating"] == "Relatively High"
    print("PASS: column mapping correct")


def test_parse_skips_blank_fips():
    dirty = SAMPLE_CSV + ",,,,,,,,,\n"
    nri.TARGET_STATE_FIPS = None
    rows = nri.parse(dirty)
    assert len(rows) == 3, "blank FIPS row should be dropped, not inserted as junk"
    print("PASS: blank rows dropped")


if __name__ == "__main__":
    test_parse_filters_to_target_state()
    test_parse_maps_columns_correctly()
    test_parse_skips_blank_fips()
    print("\nAll parse() tests passed against sample data.")
