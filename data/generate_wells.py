"""Generate a synthetic drilling-well dataset for the Drilling Hotspots Agent.

The output is a GeoJSON FeatureCollection written to
``wells_<timestamp>.geojson`` in this ``data/`` folder. Each feature is one
well with operational KPIs used by the MCP server and the map widget.

This data is entirely synthetic (deterministic with a fixed seed) and only
meant to power a realistic-looking demo -- it does NOT represent real wells.

Usage:
    python generate_wells.py [--count 60] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from basins import BASINS

HERE = Path(__file__).resolve().parent

# Operational domains ------------------------------------------------------- #
STATUSES = ["producing", "shut-in", "drilling", "maintenance"]
STATUS_WEIGHTS = [0.60, 0.15, 0.12, 0.13]
STATUS_LABEL = {
    "producing": "Producing",
    "shut-in": "Shut-in",
    "drilling": "Drilling",
    "maintenance": "Maintenance",
}

TYPES = ["oil", "gas", "injection", "exploration"]
TYPE_WEIGHTS = [0.55, 0.22, 0.15, 0.08]
TYPE_LABEL = {
    "oil": "Oil producer",
    "gas": "Gas producer",
    "injection": "Water/gas injector",
    "exploration": "Exploration",
}

OPERATORS = [
    "NordPetro AS", "GulfStar Energy", "Permian Resources Co.",
    "Arabian Upstream", "Atlântico E&P", "Delta Oil Nigeria",
    "Sibir Neft", "BoHai Offshore Ltd.",
]

# Alert catalogue: (code, human label, severity) --------------------------- #
ALERT_CATALOG = [
    ("HIGH_WATER_CUT", "High water cut", "warning"),
    ("PRESSURE_DECLINE", "Wellhead pressure decline", "warning"),
    ("ESP_FAILURE_RISK", "ESP failure risk", "critical"),
    ("H2S_DETECTED", "H2S detected", "critical"),
    ("SAND_PRODUCTION", "Sand production", "warning"),
    ("GAS_LOCK", "Gas lock / low intake", "warning"),
    ("CORROSION", "Corrosion inhibitor low", "info"),
    ("SCALE_BUILDUP", "Scale build-up", "warning"),
    ("OVERPRESSURE", "Annulus overpressure", "critical"),
]


def _pick(rnd: random.Random, choices, weights):
    return rnd.choices(choices, weights=weights, k=1)[0]


def _round(x: float, n: int = 3) -> float:
    return round(x, n)


def generate(count: int, seed: int) -> dict:
    rnd = random.Random(seed)
    now = datetime.now(timezone.utc)

    # Spread the requested count across basins proportionally.
    n_basins = len(BASINS)
    base = count // n_basins
    remainder = count - base * n_basins
    per_basin = [base + (1 if i < remainder else 0) for i in range(n_basins)]
    rnd.shuffle(per_basin)

    features = []
    well_seq = 0
    for basin, n in zip(BASINS, per_basin):
        clon, clat = basin["center"]
        slon, slat = basin["spread"]
        for _ in range(n):
            well_seq += 1
            # Gaussian scatter, clamped to the basin's rough box.
            lon = clon + rnd.gauss(0, slon / 2.2)
            lat = clat + rnd.gauss(0, slat / 2.2)
            lon = max(clon - slon, min(clon + slon, lon))
            lat = max(clat - slat, min(clat + slat, lat))

            status = _pick(rnd, STATUSES, STATUS_WEIGHTS)
            # Bias well type toward the basin's dominant hydrocarbon.
            if rnd.random() < 0.55:
                wtype = basin["dominant"]
            else:
                wtype = _pick(rnd, TYPES, TYPE_WEIGHTS)

            depth_m = int(rnd.uniform(1800, 5200) + (900 if basin["offshore"] else 0))

            # Production rate (bbl/day of oil equivalent). Non-producing wells
            # or injectors report 0 production.
            if status == "producing" and wtype in ("oil", "gas"):
                if wtype == "gas":
                    prod = int(rnd.uniform(900, 6500))
                else:
                    prod = int(rnd.uniform(300, 4200))
            else:
                prod = 0

            # Wellhead pressure (psi): higher for gas & deeper wells.
            base_p = 1500 + depth_m * rnd.uniform(0.15, 0.45)
            if wtype == "gas":
                base_p *= 1.35
            if status in ("shut-in", "drilling"):
                base_p *= rnd.uniform(0.4, 0.7)
            whp = int(base_p)

            # Water cut (% water in produced fluid). Injectors/exploration n/a.
            if wtype in ("oil", "gas") and status in ("producing", "shut-in"):
                water_cut = round(min(96.0, max(0.0, rnd.gauss(38, 22))), 1)
            else:
                water_cut = None

            # Alerts: correlate with poor KPIs so "hotspots" make sense.
            alerts = []
            catalog = list(ALERT_CATALOG)
            rnd.shuffle(catalog)
            if water_cut is not None and water_cut >= 70:
                alerts.append({"code": "HIGH_WATER_CUT",
                               "label": "High water cut", "severity": "warning"})
            if status == "maintenance" and rnd.random() < 0.75:
                code, label, sev = rnd.choice(
                    [c for c in ALERT_CATALOG if c[0] != "HIGH_WATER_CUT"])
                alerts.append({"code": code, "label": label, "severity": sev})
            # Random extra anomalies for a minority of wells.
            if rnd.random() < 0.30:
                code, label, sev = catalog[0]
                if code not in {a["code"] for a in alerts}:
                    alerts.append({"code": code, "label": label, "severity": sev})

            severity_rank = {"critical": 3, "warning": 2, "info": 1}
            worst = max((severity_rank[a["severity"]] for a in alerts), default=0)
            health = {3: "critical", 2: "warning", 1: "watch", 0: "nominal"}[worst]

            spud = now - timedelta(days=rnd.randint(30, 4200))
            last_update = now - timedelta(minutes=rnd.randint(5, 1440))

            well_id = f"{basin['prefix']}-{well_seq:03d}"
            props = {
                "id": well_id,
                "name": f"{basin['name'].split(' /')[0]} {well_id}",
                "basin": basin["name"],
                "basin_key": basin["key"],
                "country": basin["country"],
                "region": basin["region"],
                "operator": rnd.choice(OPERATORS),
                "offshore": basin["offshore"],
                "status": status,
                "status_label": STATUS_LABEL[status],
                "type": wtype,
                "type_label": TYPE_LABEL[wtype],
                "production_bbl_d": prod,
                "wellhead_pressure_psi": whp,
                "depth_m": depth_m,
                "water_cut_pct": water_cut,
                "alerts": alerts,
                "alert_count": len(alerts),
                "health": health,
                "spud_date": spud.date().isoformat(),
                "last_update": last_update.replace(microsecond=0).isoformat(),
            }
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [_round(lon), _round(lat)]},
                "properties": props,
            })

    features.sort(key=lambda f: f["properties"]["id"])
    return {
        "type": "FeatureCollection",
        "generated_at": now.replace(microsecond=0).isoformat(),
        "count": len(features),
        "note": "Synthetic demo data -- not real well locations or measurements.",
        "features": features,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic drilling-well data.")
    ap.add_argument("--count", type=int, default=60, help="Number of wells (default 60).")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed (default 42).")
    args = ap.parse_args()

    fc = generate(args.count, args.seed)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out = HERE / f"wells_{stamp}.geojson"
    out.write_text(json.dumps(fc, indent=2), encoding="utf-8")

    # Quick console summary.
    by_status: dict[str, int] = {}
    by_basin: dict[str, int] = {}
    alerts = 0
    for f in fc["features"]:
        p = f["properties"]
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1
        by_basin[p["basin"]] = by_basin.get(p["basin"], 0) + 1
        alerts += p["alert_count"]
    print(f"Wrote {out} ({fc['count']} wells)")
    print(f"  by status: {by_status}")
    print(f"  by basin : {by_basin}")
    print(f"  wells with alerts: "
          f"{sum(1 for f in fc['features'] if f['properties']['alert_count'])}, "
          f"total alerts: {alerts}")


if __name__ == "__main__":
    main()
