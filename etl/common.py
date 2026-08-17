"""
Shared helpers for every ETL script. Extracted after the 2nd real pipeline
(FEMA NRI) made the copy-pasted pattern from fetch_county_boundaries.py
obvious — see the sanity-check note from a couple turns back about not
repeating this by hand ~65 more times.

Each pipeline script still owns its own fetch URL, column mapping, and
geometry logic (those genuinely differ per source) — this just factors out
the parts that are identical every time: caching a download, upserting the
layer catalog row, and clearing old features before a refresh.
"""
import os

import requests
from sqlalchemy import create_engine, text

from config import DATABASE_URL


def get_engine():
    return create_engine(DATABASE_URL)


def fetch_and_cache(url: str, cache_path: str, binary: bool = True):
    """Downloads url unless cache_path already exists, in which case reuses it.
    Set binary=False for CSV/text sources, True for zips/shapefiles."""
    if os.path.exists(cache_path):
        print(f"Using cached copy at {cache_path}")
        mode = "rb" if binary else "r"
        kwargs = {} if binary else {"encoding": "utf-8-sig"}
        with open(cache_path, mode, **kwargs) as f:
            return f.read()

    print(f"Downloading {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    mode = "wb" if binary else "w"
    content = resp.content if binary else resp.text
    with open(cache_path, mode) as f:
        f.write(content)
    return content


def upsert_layer(conn, *, slug, category, name, source_org, source_url,
                  confidence_tier, data_kind, vintage, unit,
                  license="Public domain", forecast_epoch=None,
                  cog_path=None, notes=None) -> int:
    """Inserts or refreshes one row in the layers catalog. Returns its id."""
    return conn.execute(
        text(
            """
            INSERT INTO layers (slug, category, name, source_org, source_url,
                                 confidence_tier, data_kind, vintage, forecast_epoch,
                                 unit, cog_path, license, notes)
            VALUES (:slug, :category, :name, :source_org, :source_url,
                    :confidence_tier, :data_kind, :vintage, :forecast_epoch,
                    :unit, :cog_path, :license, :notes)
            ON CONFLICT (slug) DO UPDATE SET last_ingested_at = now()
            RETURNING id
            """
        ),
        dict(slug=slug, category=category, name=name, source_org=source_org,
             source_url=source_url, confidence_tier=confidence_tier,
             data_kind=data_kind, vintage=vintage, forecast_epoch=forecast_epoch,
             unit=unit, cog_path=cog_path, license=license, notes=notes),
    ).scalar_one()


def clear_features(conn, layer_id: int):
    conn.execute(text("DELETE FROM features WHERE layer_id = :lid"), {"lid": layer_id})


def county_geom_by_fips(conn, fips: str):
    """Looks up a county's geometry from the boundaries layer, for pipelines
    that attach attribute data to existing county shapes rather than carrying
    their own polygons (the FEMA NRI / drought monitor pattern)."""
    return conn.execute(
        text(
            """
            SELECT geom FROM features f
            JOIN layers l ON l.id = f.layer_id
            WHERE l.slug = 'census-county-boundaries'
              AND f.properties ->> 'fips' = :fips
            """
        ),
        {"fips": fips},
    ).scalar_one_or_none()
