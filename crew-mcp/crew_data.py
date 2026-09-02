"""Load and query the synthetic maintenance-crew availability referential."""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
from issues import resolve_issue, specialty_for, label_for, SPECIALTY_LABELS  # noqa: E402

DATA_DIR = Path(os.environ.get("CREWS_DATA_DIR", HERE))


def _days_from_today(iso_date: str) -> int:
    try:
        d = date.fromisoformat(iso_date)
    except (ValueError, TypeError):
        return 0
    return max(0, (d - date.today()).days)


class CrewData:
    def __init__(self, path: Path):
        self.path = path
        self.crews: list[dict[str, Any]] = []
        self.source_mtime: float | None = None
        self.load()

    def load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        crews = raw.get("crews", [])
        # Recompute availability relative to *today* so the referential stays
        # meaningful after the generation date.
        for c in crews:
            c["available_in_days"] = _days_from_today(c.get("next_available_date", ""))
        self.crews = crews
        try:
            self.source_mtime = self.path.stat().st_mtime
        except OSError:
            self.source_mtime = None

    # ------------------------------------------------------------------ #
    def query(
        self,
        specialty: str | None = None,
        region: str | None = None,
        available_within_days: int | None = None,
        include_general: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sp = specialty.strip().upper() if specialty else None
        rg = region.strip().lower() if region else None
        out = []
        for c in self.crews:
            if sp:
                if c["specialty"] != sp and not (include_general and c["specialty"] == "GENERAL"):
                    continue
            if rg and not any(rg in r.lower() for r in c["regions_covered"]) \
                    and rg not in c["base"].lower() and rg not in c["country"].lower():
                continue
            if available_within_days is not None and c["available_in_days"] > available_within_days:
                continue
            out.append(c)
        out.sort(key=lambda c: (c["available_in_days"], c["specialty"] == "GENERAL", c["crew_id"]))
        if limit is not None:
            out = out[:limit]
        return out

    # ------------------------------------------------------------------ #
    def summary(self, crews: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        cs = self.crews if crews is None else crews
        by_spec: dict[str, int] = {}
        by_region: dict[str, int] = {}
        avail_now = 0
        for c in cs:
            by_spec[c["specialty"]] = by_spec.get(c["specialty"], 0) + 1
            for r in c["regions_covered"]:
                by_region[r] = by_region.get(r, 0) + 1
            if c["available_in_days"] == 0:
                avail_now += 1
        return {
            "total_crews": len(cs),
            "available_now": avail_now,
            "by_specialty": {k: by_spec[k] for k in sorted(by_spec)},
            "by_region_coverage": dict(sorted(by_region.items())),
            "source_file": self.path.name,
        }

    # ------------------------------------------------------------------ #
    def _slim(self, c: dict[str, Any]) -> dict[str, Any]:
        return {
            "crew_id": c["crew_id"], "name": c["name"],
            "specialty": c["specialty"], "specialty_label": c["specialty_label"],
            "base": c["base"], "regions_covered": c["regions_covered"],
            "members": c["members"], "status": c["status"],
            "next_available_date": c["next_available_date"],
            "available_in_days": c["available_in_days"],
        }

    def find_available_crew(
        self,
        issue: str | None = None,
        specialty: str | None = None,
        region: str | None = None,
        top: int = 3,
    ) -> dict[str, Any]:
        code = resolve_issue(issue) if issue else None
        sp = specialty.strip().upper() if specialty else (specialty_for(code) if code else None)

        # First try crews with the exact specialty (plus GENERAL as fallback).
        matches = self.query(specialty=sp, region=region, include_general=True) if sp \
            else self.query(region=region)

        # If nothing matches the region, relax the region constraint.
        relaxed_region = False
        if not matches and region:
            matches = self.query(specialty=sp, include_general=True) if sp else self.query()
            relaxed_region = True

        best = matches[:top]
        earliest = best[0] if best else None
        return {
            "issue_query": issue,
            "issue_code": code,
            "issue_label": label_for(code) if code else None,
            "required_specialty": sp,
            "required_specialty_label": SPECIALTY_LABELS.get(sp) if sp else None,
            "region": region,
            "region_constraint_relaxed": relaxed_region,
            "match_count": len(matches),
            "earliest_crew": self._slim(earliest) if earliest else None,
            "earliest_available_date": earliest["next_available_date"] if earliest else None,
            "earliest_in_days": earliest["available_in_days"] if earliest else None,
            "candidates": [self._slim(c) for c in best],
        }


# --------------------------------------------------------------------------- #
def _latest() -> Path:
    override = os.environ.get("CREWS_DATA_PATH")
    if override:
        p = Path(override)
        if not p.exists():
            raise FileNotFoundError(f"CREWS_DATA_PATH does not exist: {p}")
        return p
    cands = sorted(DATA_DIR.glob("crews_*.json"))
    if not cands:
        raise FileNotFoundError(
            f"No crews_*.json in {DATA_DIR}. Run generate_crews.py first.")
    return cands[-1]


_instance: CrewData | None = None


def get_data() -> CrewData:
    global _instance
    latest = _latest()
    try:
        mtime = latest.stat().st_mtime
    except OSError:
        mtime = None
    # Always reload if the day changed so availability stays fresh.
    if _instance is None or _instance.path != latest or _instance.source_mtime != mtime:
        _instance = CrewData(latest)
    return _instance


if __name__ == "__main__":
    d = get_data()
    print(json.dumps(d.summary(), indent=2))
    print(json.dumps(d.find_available_crew(issue="annulus overpressure",
                                           region="North Sea"), indent=2)[:900])
