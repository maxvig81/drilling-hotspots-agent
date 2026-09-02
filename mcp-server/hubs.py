"""Build optional map layers (parts-stock warehouses, maintenance-crew bases).

The wells MCP server serves the map widget, so it also assembles these two
overlay layers by reading the sibling ``inventory-mcp`` and ``crew-mcp``
datasets and attaching a coordinate to each regional hub. This keeps the widget
self-contained: the layers travel inside the ``show_wells_map`` payload and need
no cross-server calls.

If a sibling dataset is missing, the corresponding layer is simply empty.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Regional supply/crew hub -> (city, lon, lat). Each basin has one hub, shared
# by its warehouse (parts) and its crew base.
REGION_HUB: dict[str, tuple[str, float, float]] = {
    "North Sea": ("Aberdeen", -2.10, 57.15),
    "Gulf of Mexico": ("Houston", -95.37, 29.76),
    "Permian Basin": ("Midland", -102.08, 31.99),
    "Ghawar / Persian Gulf": ("Dammam", 50.10, 26.43),
    "Campos Basin": ("Macaé", -41.78, -22.37),
    "Niger Delta": ("Port Harcourt", 7.01, 4.82),
    "West Siberia": ("Surgut", 73.40, 61.25),
    "Bohai Bay": ("Tianjin", 117.20, 39.13),
}
# Crew "base" is a city name; map it to coordinates.
BASE_COORDS: dict[str, tuple[float, float]] = {
    city: (lon, lat) for city, lon, lat in REGION_HUB.values()
}


def _latest(folder: str, pattern: str) -> Path | None:
    d = ROOT / folder
    if not d.exists():
        return None
    cands = sorted(d.glob(pattern))
    return cands[-1] if cands else None


def warehouse_layer() -> list[dict]:
    """Aggregate parts stock per warehouse with a map coordinate."""
    p = _latest("inventory-mcp", "parts_*.json")
    if not p:
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    agg: dict[str, dict] = {}
    for r in data.get("records", []):
        wh = agg.setdefault(r["warehouse"], {
            "code": r["warehouse"], "name": r["warehouse_name"],
            "region": r["region"], "country": r.get("country"),
            "total_units": 0, "distinct_parts": set(),
            "out_of_stock_lines": 0,
        })
        wh["total_units"] += int(r.get("quantity", 0))
        wh["distinct_parts"].add(r["part_id"])
        if not r.get("in_stock"):
            wh["out_of_stock_lines"] += 1
    out = []
    for wh in agg.values():
        coord = REGION_HUB.get(wh["region"])
        if not coord:
            continue
        _, lon, lat = coord
        out.append({
            "code": wh["code"], "name": wh["name"], "region": wh["region"],
            "lon": lon, "lat": lat,
            "total_units": wh["total_units"],
            "distinct_parts": len(wh["distinct_parts"]),
            "out_of_stock_lines": wh["out_of_stock_lines"],
        })
    out.sort(key=lambda w: w["code"])
    return out


def crew_layer() -> list[dict]:
    """Aggregate maintenance crews per base with a map coordinate."""
    c = _latest("crew-mcp", "crews_*.json")
    if not c:
        return []
    try:
        data = json.loads(c.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    today = date.today()

    def days(iso: str) -> int:
        try:
            return max(0, (date.fromisoformat(iso) - today).days)
        except (ValueError, TypeError):
            return 0

    agg: dict[str, dict] = {}
    for cr in data.get("crews", []):
        base = cr["base"]
        b = agg.setdefault(base, {
            "base": base, "country": cr.get("country"),
            "crew_count": 0, "available_now": 0,
            "earliest_in_days": None, "earliest_date": None,
            "specialties": set(),
        })
        b["crew_count"] += 1
        d = days(cr.get("next_available_date", ""))
        if d == 0:
            b["available_now"] += 1
        if b["earliest_in_days"] is None or d < b["earliest_in_days"]:
            b["earliest_in_days"] = d
            b["earliest_date"] = cr.get("next_available_date")
        b["specialties"].add(cr.get("specialty_label", cr.get("specialty")))
    out = []
    for b in agg.values():
        coord = BASE_COORDS.get(b["base"])
        if not coord:
            continue
        lon, lat = coord
        out.append({
            "base": b["base"], "country": b["country"],
            "lon": lon, "lat": lat,
            "crew_count": b["crew_count"],
            "available_now": b["available_now"],
            "earliest_in_days": b["earliest_in_days"] or 0,
            "earliest_date": b["earliest_date"],
            "specialties": sorted(s for s in b["specialties"] if s),
        })
    out.sort(key=lambda b: b["base"])
    return out


def build_layers() -> dict:
    return {"warehouses": warehouse_layer(), "crews": crew_layer()}


if __name__ == "__main__":
    print(json.dumps(build_layers(), indent=2))
