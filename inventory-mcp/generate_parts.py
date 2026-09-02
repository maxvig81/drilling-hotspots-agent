"""Generate a fictitious spare-parts inventory for the Drilling Hotspots Agent.

Produces ``parts_<timestamp>.json`` in this folder: a list of stock records,
each a part held at a regional warehouse, linked to the failure/issue codes it
addresses (see ../shared/issues.py). Deterministic for a given --seed.

This data is entirely synthetic and only powers a demo -- it does not represent
real inventory.

    python generate_parts.py [--seed 7]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
from issues import label_for  # noqa: E402

# Regional warehouses, each near one or more basins.
WAREHOUSES = [
    {"code": "WH-ABZ", "name": "Aberdeen Supply Base", "region": "North Sea",
     "country": "United Kingdom"},
    {"code": "WH-HOU", "name": "Houston Distribution Center", "region": "Gulf of Mexico",
     "country": "United States"},
    {"code": "WH-MID", "name": "Midland Yard", "region": "Permian Basin",
     "country": "United States"},
    {"code": "WH-DMM", "name": "Dammam Central Store", "region": "Ghawar / Persian Gulf",
     "country": "Saudi Arabia"},
    {"code": "WH-MCE", "name": "Macaé Logistics Hub", "region": "Campos Basin",
     "country": "Brazil"},
    {"code": "WH-PHC", "name": "Port Harcourt Warehouse", "region": "Niger Delta",
     "country": "Nigeria"},
    {"code": "WH-SGT", "name": "Surgut Depot", "region": "West Siberia",
     "country": "Russia"},
    {"code": "WH-TSN", "name": "Tianjin Marine Base", "region": "Bohai Bay",
     "country": "China"},
]

# Parts catalogue: (name, category, unit, [issue_codes]).
CATALOG = [
    ("Annulus safety valve", "Wellhead & X-tree", "unit", ["OVERPRESSURE"]),
    ("Wellhead seal assembly kit", "Wellhead & X-tree", "kit", ["OVERPRESSURE", "CORROSION"]),
    ("Casing head pack-off", "Wellhead & X-tree", "unit", ["OVERPRESSURE"]),
    ("Christmas tree gate valve", "Wellhead & X-tree", "unit", ["OVERPRESSURE", "PRESSURE_DECLINE"]),
    ("Tubing hanger seal", "Wellhead & X-tree", "unit", ["OVERPRESSURE"]),
    ("Production packer", "Downhole", "unit", ["OVERPRESSURE", "HIGH_WATER_CUT"]),
    ("Water shut-off packer", "Downhole", "unit", ["HIGH_WATER_CUT"]),
    ("Sand screen (premium)", "Downhole", "joint", ["SAND_PRODUCTION"]),
    ("Gravel pack assembly", "Downhole", "assembly", ["SAND_PRODUCTION"]),
    ("Corrosion-resistant tubing joint (13Cr)", "Downhole", "joint", ["CORROSION", "H2S_DETECTED"]),
    ("Surface-controlled subsurface safety valve", "Downhole", "unit", ["OVERPRESSURE", "PRESSURE_DECLINE"]),
    ("ESP pump stage cartridge", "Artificial lift", "unit", ["ESP_FAILURE_RISK"]),
    ("ESP motor", "Artificial lift", "unit", ["ESP_FAILURE_RISK"]),
    ("ESP power cable (spooled)", "Artificial lift", "reel", ["ESP_FAILURE_RISK"]),
    ("Downhole gas separator", "Artificial lift", "unit", ["ESP_FAILURE_RISK", "GAS_LOCK"]),
    ("Gas-lock breaker valve", "Artificial lift", "unit", ["GAS_LOCK"]),
    ("H2S scavenger", "Chemicals", "drum", ["H2S_DETECTED"]),
    ("Corrosion inhibitor", "Chemicals", "drum", ["CORROSION"]),
    ("Scale inhibitor", "Chemicals", "drum", ["SCALE_BUILDUP"]),
    ("Scale dissolver batch", "Chemicals", "batch", ["SCALE_BUILDUP"]),
    ("Wellhead pressure transmitter", "Instrumentation", "unit", ["PRESSURE_DECLINE", "OVERPRESSURE"]),
    ("Downhole pressure/temperature gauge", "Instrumentation", "unit", ["PRESSURE_DECLINE"]),
    ("Fixed H2S gas detector", "Instrumentation", "unit", ["H2S_DETECTED"]),
]


def generate(seed: int) -> dict:
    rnd = random.Random(seed)
    now = datetime.now(timezone.utc)
    records = []
    seq = 0
    for idx, (name, category, unit, codes) in enumerate(CATALOG):
        part_id = f"P-{1000 + idx:04d}"
        # Each part is stocked in 2-3 warehouses.
        whs = rnd.sample(WAREHOUSES, k=rnd.randint(2, 3))
        for wh in whs:
            seq += 1
            # ~22% of stock lines are out of stock (qty 0).
            if rnd.random() < 0.22:
                qty = 0
                lead = rnd.choice([7, 10, 14, 21, 30, 45])
            else:
                qty = rnd.randint(1, 14)
                lead = rnd.choice([3, 5, 7, 10])  # replenishment lead if it runs out
            records.append({
                "sku": f"{part_id}-{wh['code']}",
                "part_id": part_id,
                "name": name,
                "category": category,
                "unit": unit,
                "issue_codes": codes,
                "addresses": [label_for(c) for c in codes],
                "warehouse": wh["code"],
                "warehouse_name": wh["name"],
                "region": wh["region"],
                "country": wh["country"],
                "quantity": qty,
                "in_stock": qty > 0,
                "lead_time_days": lead,
                "unit_cost_usd": rnd.choice([420, 850, 1200, 2600, 5400, 9800, 15400]),
            })
    records.sort(key=lambda r: (r["part_id"], r["warehouse"]))
    return {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "count": len(records),
        "distinct_parts": len(CATALOG),
        "note": "Synthetic demo inventory -- not real stock data.",
        "warehouses": WAREHOUSES,
        "records": records,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    data = generate(args.seed)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out = HERE / f"parts_{stamp}.json"
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    oos = sum(1 for r in data["records"] if not r["in_stock"])
    print(f"Wrote {out} ({data['count']} stock lines, "
          f"{data['distinct_parts']} distinct parts, {oos} out-of-stock lines)")


if __name__ == "__main__":
    main()
