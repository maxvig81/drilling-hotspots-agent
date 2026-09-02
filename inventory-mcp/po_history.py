"""Persistent purchase-order history (ledger).

Every purchase order that is sent is recorded here so the agent can later
confirm whether a specific part was ordered, look up a PO by number, or review
recent orders. Backed by a single JSON file; records are upserted by PO number
(re-sending an identical order updates the existing entry rather than
duplicating it).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
HISTORY_PATH = Path(__import__("os").environ.get("PO_HISTORY_PATH", HERE / "po_history.json"))


def _load() -> list[dict[str, Any]]:
    if HISTORY_PATH.exists():
        try:
            data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("orders", [])
        except (OSError, ValueError):
            return []
    return []


def _save(items: list[dict[str, Any]]) -> None:
    HISTORY_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


def record(po: dict[str, Any]) -> dict[str, Any]:
    """Upsert a sent PO into the history and return the stored entry."""
    li = (po.get("line_items") or [{}])[0]
    entry = {
        "po_number": po["po_number"],
        "status": "SENT",
        "order_date": po.get("order_date"),
        "sent_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "part_id": li.get("part_id"),
        "part_name": li.get("description"),
        "quantity": li.get("quantity"),
        "unit": li.get("unit"),
        "unit_cost_usd": li.get("unit_cost_usd"),
        "subtotal_usd": po.get("subtotal_usd"),
        "supplier": po.get("supplier", {}).get("company"),
        "supplier_email": po.get("supplier", {}).get("email"),
        "region": po.get("supplier", {}).get("region"),
        "ship_to": po.get("ship_to"),
        "well_ref": po.get("well_ref"),
        "needed_by": po.get("needed_by"),
        "requested_by": po.get("buyer", {}).get("requested_by"),
        "requester_email": po.get("buyer", {}).get("email"),
        "document_text": po.get("document_text"),
    }
    items = [i for i in _load() if i.get("po_number") != entry["po_number"]]
    items.append(entry)
    items.sort(key=lambda i: i.get("sent_at", ""), reverse=True)
    _save(items)
    return entry


def _summary(i: dict[str, Any]) -> dict[str, Any]:
    return {k: i.get(k) for k in (
        "po_number", "status", "sent_at", "part_id", "part_name", "quantity",
        "unit", "subtotal_usd", "supplier", "region", "well_ref", "needed_by",
        "requested_by")}


def query(
    part: str | None = None,
    well_id: str | None = None,
    po_number: str | None = None,
    supplier: str | None = None,
    status: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    p = part.strip().lower() if part else None
    wid = well_id.strip().lower() if well_id else None
    pn = po_number.strip().lower() if po_number else None
    sup = supplier.strip().lower() if supplier else None
    st = status.strip().upper() if status else None
    out = []
    for i in _load():
        if p and p not in (i.get("part_id") or "").lower() \
                and p not in (i.get("part_name") or "").lower():
            continue
        if wid and wid not in (i.get("well_ref") or "").lower():
            continue
        if pn and pn not in (i.get("po_number") or "").lower():
            continue
        if sup and sup not in (i.get("supplier") or "").lower():
            continue
        if st and (i.get("status") or "").upper() != st:
            continue
        out.append(i)
    total = len(out)
    if limit is not None:
        out = out[:limit]
    return {
        "orders": [_summary(i) for i in out],
        "returned": len(out),
        "total_matches": total,
        "filters": {"part": part, "well_id": well_id, "po_number": po_number,
                    "supplier": supplier, "status": status},
    }


def get(po_number: str) -> dict[str, Any] | None:
    pn = (po_number or "").strip().lower()
    for i in _load():
        if (i.get("po_number") or "").lower() == pn:
            return i
    return None


if __name__ == "__main__":
    print(json.dumps(query(), indent=2))
