"""Generate a fictitious maintenance-crew availability referential.

Produces ``crews_<timestamp>.json`` in this folder: a list of maintenance crews,
each with a specialty, the basins/regions they cover, their crew size, current
assignment, and their next available date. Deterministic for a given --seed.

Synthetic demo data only -- not real crews or schedules.

    python generate_crews.py [--seed 11]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
from issues import SPECIALTY_LABELS  # noqa: E402

# Operating bases and the basins each can reach (first is the home basin).
BASES = [
    {"base": "Aberdeen", "country": "United Kingdom",
     "regions": ["North Sea"]},
    {"base": "Houston", "country": "United States",
     "regions": ["Gulf of Mexico", "Permian Basin"]},
    {"base": "Midland", "country": "United States",
     "regions": ["Permian Basin", "Gulf of Mexico"]},
    {"base": "Dammam", "country": "Saudi Arabia",
     "regions": ["Ghawar / Persian Gulf"]},
    {"base": "Macaé", "country": "Brazil",
     "regions": ["Campos Basin"]},
    {"base": "Port Harcourt", "country": "Nigeria",
     "regions": ["Niger Delta"]},
    {"base": "Surgut", "country": "Russia",
     "regions": ["West Siberia"]},
    {"base": "Tianjin", "country": "China",
     "regions": ["Bohai Bay"]},
]

SPECIALTIES = ["WELL_INTEGRITY", "ARTIFICIAL_LIFT", "SAND_CONTROL",
               "FLOW_ASSURANCE", "HSE_SOUR", "GENERAL"]

# How many crews to seed per base (kept small but with full specialty coverage
# spread across the fleet).
CREWS_PER_BASE = 2

FIRST_NAMES = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot",
               "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima",
               "Mike", "November", "Oscar", "Papa"]

ASSIGNMENTS = [
    "Available on standby", "Wireline job", "Workover in progress",
    "Rig-up mobilisation", "Scheduled inspection", "Turnaround support",
    "Transit / crew change",
]


def generate(seed: int) -> dict:
    rnd = random.Random(seed)
    now = datetime.now(timezone.utc)
    today = now.date()

    crews = []
    seq = 0
    name_i = 0
    # Guarantee each specialty appears at least once by cycling through them.
    spec_cycle = SPECIALTIES * 6
    ci = 0
    for base in BASES:
        for _ in range(CREWS_PER_BASE):
            seq += 1
            specialty = spec_cycle[ci]; ci += 1
            crew_id = f"CRW-{seq:02d}"
            # Coverage: home regions plus, for GENERAL crews, a chance of an extra basin.
            regions = list(base["regions"])
            members = rnd.randint(3, 7)

            # Availability: a spread of "available now" to a few weeks out.
            offset = rnd.choices(
                [0, 1, 2, 3, 5, 7, 10, 14, 21],
                weights=[10, 8, 8, 7, 6, 6, 4, 3, 2], k=1)[0]
            next_avail = today + timedelta(days=offset)
            status = "Available now" if offset == 0 else \
                (rnd.choice(ASSIGNMENTS[1:]))

            crews.append({
                "crew_id": crew_id,
                "name": f"{base['base']} {FIRST_NAMES[name_i % len(FIRST_NAMES)]} crew",
                "specialty": specialty,
                "specialty_label": SPECIALTY_LABELS[specialty],
                "base": base["base"],
                "country": base["country"],
                "regions_covered": regions,
                "members": members,
                "status": status,
                "current_assignment": "Available on standby" if offset == 0
                    else status,
                "next_available_date": next_avail.isoformat(),
                "available_in_days": offset,
                "shift": rnd.choice(["day", "day/night", "24h rotation"]),
            })
            name_i += 1

    crews.sort(key=lambda c: c["crew_id"])
    return {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "reference_date": today.isoformat(),
        "count": len(crews),
        "note": "Synthetic demo crew availability -- not real crews or schedules.",
        "specialties": {k: SPECIALTY_LABELS[k] for k in SPECIALTIES},
        "crews": crews,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()
    data = generate(args.seed)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out = HERE / f"crews_{stamp}.json"
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    by_spec: dict[str, int] = {}
    avail_now = 0
    for c in data["crews"]:
        by_spec[c["specialty"]] = by_spec.get(c["specialty"], 0) + 1
        if c["available_in_days"] == 0:
            avail_now += 1
    print(f"Wrote {out} ({data['count']} crews, {avail_now} available now)")
    print(f"  by specialty: {by_spec}")


if __name__ == "__main__":
    main()
