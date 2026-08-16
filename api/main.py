"""
Minimal API — just enough to prove the loop: DB -> API -> map. Two endpoints:
/layers feeds the frontend's filter panel, /layers/{slug}/geojson feeds the
map itself. The scoring engine (Design Principle 2.4) isn't wired in yet —
that's the natural next endpoint once there's more than one real layer to
weigh against each other.

Run: uvicorn main:app --reload
"""
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://homestead:localdev@localhost:5432/homestead"
)
engine = create_engine(DATABASE_URL)

app = FastAPI(title="Future-Fit Homestead API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/layers")
def list_layers():
    """The layer catalog — what the filter panel renders from."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT slug, category, name, source_org, confidence_tier, data_kind, vintage
                FROM layers ORDER BY category, name
                """
            )
        ).mappings().all()
    return [dict(r) for r in rows]


@app.get("/layers/{slug}/geojson")
def layer_geojson(slug: str):
    """One layer's features as a GeoJSON FeatureCollection, straight into MapLibre."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT ST_AsGeoJSON(f.geom) AS geom, f.properties
                FROM features f JOIN layers l ON l.id = f.layer_id
                WHERE l.slug = :slug
                """
            ),
            {"slug": slug},
        ).mappings().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No layer '{slug}' or it has no features yet")

    features = [
        {"type": "Feature", "geometry": json.loads(r["geom"]), "properties": r["properties"]}
        for r in rows
    ]
    return {"type": "FeatureCollection", "features": features}
