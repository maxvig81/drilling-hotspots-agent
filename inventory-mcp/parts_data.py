"""Load and query the synthetic spare-parts inventory."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
from issues import resolve_issue, label_for  # noqa: E402

DATA_DIR = Path(os.environ.get("PARTS_DATA_DIR", HERE))


class PartsData:
    def __init__(self, path: Path):
        self.path = path
        self.records: list[dict[str, Any]] = []
        self.warehouses: list[dict[str, Any]] = []
        self.source_mtime: float | None = None
        self.load()

    def load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.records = raw.get("records", [])
        self.warehouses = raw.get("warehouses", [])
        try:
            self.source_mtime = self.path.stat().st_mtime
        except OSError:
            self.source_mtime = None

    # ------------------------------------------------------------------ #
    def query(
        self,
        category: str | None = None,
        in_stock: bool | None = None,
        search: str | None = None,
        issue_code: str | None = None,
        region: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        cat = category.strip().lower() if category else None
        q = search.strip().lower() if search else None
        rg = region.strip().lower() if region else None
        out = []
        for r in self.records:
            if cat and cat not in r["category"].lower():
                continue
            if in_stock is not None and bool(r["in_stock"]) != bool(in_stock):
                continue
            if issue_code and issue_code not in r["issue_codes"]:
                continue
            if rg and rg not in r["region"].lower() and rg not in r["country"].lower():
                continue
            if q and q not in r["name"].lower() and q not in r["part_id"].lower() \
                    and q not in r["sku"].lower():
                continue
            out.append(r)
        out.sort(key=lambda r: (not r["in_stock"], r["part_id"], r["warehouse"]))
        if limit is not None:
            out = out[:limit]
        return out

    # ------------------------------------------------------------------ #
    def summary(self, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        recs = self.records if records is None else records
        by_cat: dict[str, int] = {}
        by_wh: dict[str, int] = {}
        parts = set()
        in_stock_lines = 0
        total_qty = 0
        for r in recs:
            by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
            by_wh[r["warehouse"]] = by_wh.get(r["warehouse"], 0) + 1
            parts.add(r["part_id"])
            if r["in_stock"]:
                in_stock_lines += 1
            total_qty += int(r["quantity"])
        return {
            "stock_lines": len(recs),
            "distinct_parts": len(parts),
            "in_stock_lines": in_stock_lines,
            "out_of_stock_lines": len(recs) - in_stock_lines,
            "total_units": total_qty,
            "by_category": dict(sorted(by_cat.items())),
            "warehouses": len(by_wh),
            "source_file": self.path.name,
        }

    # ------------------------------------------------------------------ #
    def check_part(self, term: str) -> dict[str, Any]:
        """Availability for a part id or name across all warehouses."""
        recs = self.query(search=term)
        # If the term looks like a part id, prefer exact id lines.
        exact = [r for r in recs if r["part_id"].lower() == term.strip().lower()]
        recs = exact or recs
        if not recs:
            return {"term": term, "found": False,
                    "message": f"No part matches '{term}'."}
        total = sum(r["quantity"] for r in recs)
        available = [r for r in recs if r["in_stock"]]
        soonest_lead = min((r["lead_time_days"] for r in recs), default=None)
        return {
            "term": term,
            "found": True,
            "part_id": recs[0]["part_id"],
            "name": recs[0]["name"],
            "category": recs[0]["category"],
            "total_units_available": total,
            "in_stock": total > 0,
            "locations": [
                {"warehouse": r["warehouse"], "warehouse_name": r["warehouse_name"],
                 "region": r["region"], "quantity": r["quantity"],
                 "in_stock": r["in_stock"], "lead_time_days": r["lead_time_days"]}
                for r in recs
            ],
            "reorder_lead_time_days": soonest_lead if total == 0 else 0,
        }

    # ------------------------------------------------------------------ #
    def resolve_for_order(self, term: str, region: str | None = None) -> dict | None:
        """Resolve a part (by id or name) into the fields needed to raise a PO.

        Picks a supplier region: the caller's ``region`` if given, else the
        region of an out-of-stock line for that part (the one to reorder), else
        the first stock line's region.
        """
        recs = self.query(search=term)
        exact = [r for r in recs if r["part_id"].lower() == (term or "").strip().lower()]
        recs = exact or recs
        if not recs:
            return None
        chosen = None
        if region:
            rg = region.strip().lower()
            chosen = next((r for r in recs
                           if rg in r["region"].lower() or rg in r["country"].lower()), None)
        if chosen is None:
            chosen = next((r for r in recs if not r["in_stock"]), None)
        if chosen is None:
            chosen = recs[0]
        return {
            "part_id": chosen["part_id"],
            "name": chosen["name"],
            "category": chosen["category"],
            "unit": chosen["unit"],
            "unit_cost": chosen.get("unit_cost_usd", chosen.get("unit_cost", 0)),
            "lead_time_days": chosen["lead_time_days"],
            "region": region or chosen["region"],
        }

    # ------------------------------------------------------------------ #
    def parts_for_issue(self, issue_text: str, region: str | None = None) -> dict[str, Any]:
        code = resolve_issue(issue_text)
        if not code:
            return {"issue_query": issue_text, "resolved": False,
                    "message": f"Could not map '{issue_text}' to a known issue."}
        recs = self.query(issue_code=code, region=region)
        # Group by part_id, aggregating across warehouses.
        parts: dict[str, dict[str, Any]] = {}
        for r in recs:
            p = parts.setdefault(r["part_id"], {
                "part_id": r["part_id"], "name": r["name"],
                "category": r["category"], "unit": r["unit"],
                "total_units": 0, "in_stock": False, "locations": [],
                "min_lead_time_days": None,
            })
            p["total_units"] += r["quantity"]
            p["in_stock"] = p["in_stock"] or r["in_stock"]
            p["locations"].append({
                "warehouse": r["warehouse"], "region": r["region"],
                "quantity": r["quantity"], "lead_time_days": r["lead_time_days"]})
            lt = r["lead_time_days"]
            if p["min_lead_time_days"] is None or lt < p["min_lead_time_days"]:
                p["min_lead_time_days"] = lt
        part_list = sorted(parts.values(), key=lambda p: (not p["in_stock"], p["part_id"]))
        all_in_stock = bool(part_list) and all(p["in_stock"] for p in part_list)
        missing = [p["name"] for p in part_list if not p["in_stock"]]
        # Earliest we could have every part on hand (0 if all in stock).
        max_lead = max((p["min_lead_time_days"] for p in part_list if not p["in_stock"]),
                       default=0)
        return {
            "issue_query": issue_text,
            "resolved": True,
            "issue_code": code,
            "issue_label": label_for(code),
            "region": region,
            "required_parts": part_list,
            "part_count": len(part_list),
            "all_in_stock": all_in_stock,
            "missing_parts": missing,
            "parts_ready_in_days": 0 if all_in_stock else max_lead,
        }


# --------------------------------------------------------------------------- #
def _latest() -> Path:
    override = os.environ.get("PARTS_DATA_PATH")
    if override:
        p = Path(override)
        if not p.exists():
            raise FileNotFoundError(f"PARTS_DATA_PATH does not exist: {p}")
        return p
    cands = sorted(DATA_DIR.glob("parts_*.json"))
    if not cands:
        raise FileNotFoundError(
            f"No parts_*.json in {DATA_DIR}. Run generate_parts.py first.")
    return cands[-1]


_instance: PartsData | None = None


def get_data() -> PartsData:
    global _instance
    latest = _latest()
    try:
        mtime = latest.stat().st_mtime
    except OSError:
        mtime = None
    if _instance is None or _instance.path != latest or _instance.source_mtime != mtime:
        _instance = PartsData(latest)
    return _instance


if __name__ == "__main__":
    d = get_data()
    print(json.dumps(d.summary(), indent=2))
    print(json.dumps(d.parts_for_issue("annulus overpressure"), indent=2)[:800])
