"""
Shared config for every ETL script. Deliberately tiny — the whole point is that
picking a region is a one-line change here, not a rewrite of any pipeline.
"""
import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://homestead:localdev@localhost:5432/homestead"
)

# PLACEHOLDER — Colorado (FIPS 08), picked only as a stand-in so this scaffold
# has something concrete to run against. Swap for your real candidate region,
# or set to None to pull the whole country (much slower, much more data).
TARGET_STATE_FIPS = os.environ.get("TARGET_STATE_FIPS", "08")

RAW_DATA_CACHE_DIR = os.environ.get("RAW_DATA_CACHE_DIR", "./data/raw")
