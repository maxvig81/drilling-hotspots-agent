"""Build the bundled base-map outline for the wells map widget.

Downloads coarse (Natural Earth 110m) world land polygons and country border
lines, simplifies them, and writes two compact JSON files consumed by main.js
and inlined into widget.html at build time (so the widget needs no network):

    ../assets/basemap_outline.json  -> {"bbox": [...], "rings": [[lon,lat,...]]}
    ../assets/borders_outline.json  -> {"lines": [[lon,lat,...]]}

Run once (or whenever you want to refresh the base map):
    python build_outline.py
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"

LAND_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
            "master/geojson/ne_110m_land.geojson")
BORDERS_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
               "master/geojson/ne_110m_admin_0_boundary_lines_land.geojson")

# World view used by the widget's equirectangular projection. Antarctica is
# clipped off the bottom so the inhabited world fills the frame.
BBOX = [-180.0, -60.0, 180.0, 84.0]


def _fetch(url: str) -> dict:
    print(f"  GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "wells-outline/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _flatten_ring(ring: list, quant: int = 2) -> list[float]:
    """Flatten [[lon,lat],...] -> [lon,lat,...], rounded and de-duplicated."""
    flat: list[float] = []
    last = None
    for pt in ring:
        lon, lat = round(pt[0], quant), round(pt[1], quant)
        if (lon, lat) == last:
            continue
        flat.extend((lon, lat))
        last = (lon, lat)
    return flat


def _iter_polygons(geom: dict):
    t = geom.get("type")
    coords = geom.get("coordinates") or []
    if t == "Polygon":
        yield from coords
    elif t == "MultiPolygon":
        for poly in coords:
            yield from poly


def _iter_lines(geom: dict):
    t = geom.get("type")
    coords = geom.get("coordinates") or []
    if t == "LineString":
        yield coords
    elif t == "MultiLineString":
        yield from coords


def build() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    print("Fetching land polygons...")
    land = _fetch(LAND_URL)
    rings: list[list[float]] = []
    for feat in land.get("features", []):
        for ring in _iter_polygons(feat.get("geometry") or {}):
            flat = _flatten_ring(ring)
            if len(flat) >= 8:  # at least 4 points
                rings.append(flat)
    basemap = {"bbox": BBOX, "rings": rings}
    (ASSETS / "basemap_outline.json").write_text(
        json.dumps(basemap, separators=(",", ":")), encoding="utf-8")

    print("Fetching country borders...")
    try:
        borders_geo = _fetch(BORDERS_URL)
        lines: list[list[float]] = []
        for feat in borders_geo.get("features", []):
            for line in _iter_lines(feat.get("geometry") or {}):
                flat = _flatten_ring(line)
                if len(flat) >= 4:
                    lines.append(flat)
    except Exception as exc:  # noqa: BLE001 - borders are optional
        print(f"  (borders unavailable: {exc})")
        lines = []
    (ASSETS / "borders_outline.json").write_text(
        json.dumps({"lines": lines}, separators=(",", ":")), encoding="utf-8")

    lp = ASSETS / "basemap_outline.json"
    bp = ASSETS / "borders_outline.json"
    print(f"Wrote {lp} ({lp.stat().st_size/1024:.0f} KB, {len(rings)} rings)")
    print(f"Wrote {bp} ({bp.stat().st_size/1024:.0f} KB, {len(lines)} lines)")


if __name__ == "__main__":
    build()
