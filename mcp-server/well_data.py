"""Load and query the synthetic drilling-well dataset.

The generator (``data/generate_wells.py``) writes ``wells_<timestamp>.geojson``
into the repo's ``data/`` folder. This module discovers the most recent such
file (overridable with ``WELLS_DATA_PATH``) and exposes small, pure query
helpers used by the MCP tools.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DATA_DIR = Path(
    os.environ.get("WELLS_DATA_DIR", Path(__file__).resolve().parent.parent / "data")
)

STATUS_ORDER = ["producing", "shut-in", "drilling", "maintenance"]
TYPE_ORDER = ["oil", "gas", "injection", "exploration"]

# Fields copied verbatim from the GeoJSON properties onto each in-memory well.
_PROP_FIELDS = (
    "id", "name", "basin", "basin_key", "country", "region", "operator",
    "offshore", "status", "status_label", "type", "type_label",
    "production_bbl_d", "wellhead_pressure_psi", "depth_m", "water_cut_pct",
    "alerts", "alert_count", "health", "spud_date", "last_update",
)


class WellData:
    def __init__(self, path: Path):
        self.path = path
        self.wells: list[dict[str, Any]] = []
        self.loaded_at: datetime | None = None
        self.source_mtime: float | None = None
        self.load()

    # ------------------------------------------------------------------ #
    def load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        wells: list[dict[str, Any]] = []
        for f in raw.get("features", []):
            geom = f.get("geometry") or {}
            coords = geom.get("coordinates") or [None, None]
            props = f.get("properties") or {}
            lon, lat = coords[0], coords[1]
            if lon is None or lat is None:
                continue
            w: dict[str, Any] = {"lon": float(lon), "lat": float(lat)}
            for k in _PROP_FIELDS:
                w[k] = props.get(k)
            wells.append(w)
        self.wells = wells
        self.loaded_at = datetime.now(timezone.utc)
        try:
            self.source_mtime = self.path.stat().st_mtime
        except OSError:
            self.source_mtime = None

    # ------------------------------------------------------------------ #
    def query(
        self,
        status: str | None = None,
        well_type: str | None = None,
        basin: str | None = None,
        only_alerts: bool | None = None,
        bbox: Iterable[float] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        st = status.strip().lower() if status else None
        ty = well_type.strip().lower() if well_type else None
        bs = basin.strip().lower() if basin else None
        box = list(bbox) if bbox else None
        out = []
        for w in self.wells:
            if st and w["status"] != st:
                continue
            if ty and w["type"] != ty:
                continue
            if bs and bs not in (w["basin"] or "").lower() \
                    and bs not in (w["basin_key"] or "").lower() \
                    and bs not in (w["country"] or "").lower():
                continue
            if only_alerts and not w["alert_count"]:
                continue
            if box:
                minlon, minlat, maxlon, maxlat = box
                if not (minlon <= w["lon"] <= maxlon and minlat <= w["lat"] <= maxlat):
                    continue
            out.append(w)
        out.sort(key=lambda w: w["id"])
        if limit is not None:
            out = out[:limit]
        return out

    # ------------------------------------------------------------------ #
    def get(self, well_id: str) -> dict[str, Any] | None:
        wid = (well_id or "").strip().lower()
        for w in self.wells:
            if (w["id"] or "").lower() == wid:
                return w
        return None

    # ------------------------------------------------------------------ #
    def summary(self, wells: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        ws = self.wells if wells is None else wells
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_basin: dict[str, int] = {}
        by_health: dict[str, int] = {}
        total_prod = 0
        wells_with_alerts = 0
        critical = 0
        minlon = minlat = 1e9
        maxlon = maxlat = -1e9
        for w in ws:
            by_status[w["status"]] = by_status.get(w["status"], 0) + 1
            by_type[w["type"]] = by_type.get(w["type"], 0) + 1
            by_basin[w["basin"]] = by_basin.get(w["basin"], 0) + 1
            by_health[w["health"]] = by_health.get(w["health"], 0) + 1
            total_prod += int(w.get("production_bbl_d") or 0)
            if w.get("alert_count"):
                wells_with_alerts += 1
            if w.get("health") == "critical":
                critical += 1
            minlon = min(minlon, w["lon"]); maxlon = max(maxlon, w["lon"])
            minlat = min(minlat, w["lat"]); maxlat = max(maxlat, w["lat"])

        def _ordered(d: dict[str, int], order: list[str]) -> dict[str, int]:
            out = {k: d[k] for k in order if k in d}
            out.update({k: v for k, v in d.items() if k not in out})
            return out

        return {
            "total": len(ws),
            "by_status": _ordered(by_status, STATUS_ORDER),
            "by_type": _ordered(by_type, TYPE_ORDER),
            "by_basin": dict(sorted(by_basin.items())),
            "by_health": by_health,
            "total_production_bbl_d": total_prod,
            "wells_with_alerts": wells_with_alerts,
            "critical_wells": critical,
            "bbox": [round(minlon, 3), round(minlat, 3),
                     round(maxlon, 3), round(maxlat, 3)] if ws else None,
            "source_file": self.path.name,
        }

    # ------------------------------------------------------------------ #
    def map_payload(self, wells: list[dict[str, Any]]) -> dict[str, Any]:
        """Compact per-well payload for the map widget (markers + popups)."""
        pts = []
        for w in wells:
            pts.append({
                "id": w["id"],
                "name": w["name"],
                "lon": round(w["lon"], 4),
                "lat": round(w["lat"], 4),
                "status": w["status"],
                "type": w["type"],
                "type_label": w["type_label"],
                "prod": int(w.get("production_bbl_d") or 0),
                "whp": w.get("wellhead_pressure_psi"),
                "depth": w.get("depth_m"),
                "wc": w.get("water_cut_pct"),
                "health": w["health"],
                "basin": w["basin"],
                "country": w["country"],
                "operator": w["operator"],
                "offshore": bool(w.get("offshore")),
                "alerts": [a["label"] for a in (w.get("alerts") or [])],
            })
        return {
            "wells": pts,
            "count": len(pts),
            "statuses": STATUS_ORDER,
        }


# --------------------------------------------------------------------------- #
def _latest_data_file() -> Path:
    override = os.environ.get("WELLS_DATA_PATH")
    if override:
        p = Path(override)
        if not p.exists():
            raise FileNotFoundError(f"WELLS_DATA_PATH does not exist: {p}")
        return p
    candidates = sorted(DATA_DIR.glob("wells_*.geojson"))
    if not candidates:
        raise FileNotFoundError(
            f"No wells_*.geojson found in {DATA_DIR}. "
            f"Run data/generate_wells.py first."
        )
    return candidates[-1]


_instance: WellData | None = None


def get_data() -> WellData:
    """Return the loaded dataset, hot-reloading when a newer snapshot appears."""
    global _instance
    if os.environ.get("WELLS_DATA_PATH"):
        if _instance is None:
            _instance = WellData(_latest_data_file())
        return _instance
    latest = _latest_data_file()
    try:
        mtime = latest.stat().st_mtime
    except OSError:
        mtime = None
    if _instance is None or _instance.path != latest or _instance.source_mtime != mtime:
        _instance = WellData(latest)
    return _instance


if __name__ == "__main__":
    d = get_data()
    print(json.dumps(d.summary(), indent=2))
