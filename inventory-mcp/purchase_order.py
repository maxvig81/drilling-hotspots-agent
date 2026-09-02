"""Build and (simulated) send spare-part purchase orders.

``build_po`` fills an English purchase-order template from resolved part +
supplier + requester details and returns a structured PO plus a formatted text
document, an HTML body, and a ``mailto:`` link. ``send_po`` performs a
*simulated* send: it writes the PO to the ``outbox/`` folder and returns a
confirmation (no real email is sent -- addresses use the reserved .example TLD).
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

from suppliers import supplier_for_region
import po_history

HERE = Path(__file__).resolve().parent
OUTBOX = HERE / "outbox"

BUYER_COMPANY = "Contoso Petroleum Operations"
DEFAULT_REQUESTER = "Operations"
DEFAULT_REQUESTER_EMAIL = "maxime.vignal@contosocpm.onmicrosoft.com"


def _po_number(part_id: str, qty: int, requested_by: str, order_date: date) -> str:
    seed = f"{part_id}|{qty}|{requested_by}|{order_date.isoformat()}"
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()[:5].upper()
    return f"PO-{order_date.strftime('%Y%m%d')}-{h}"


def build_po(
    *,
    part_id: str,
    name: str,
    category: str,
    unit: str,
    unit_cost: float,
    lead_time_days: int,
    quantity: int,
    region: str | None,
    ship_to: str | None = None,
    well_id: str | None = None,
    needed_by: str | None = None,
    reason: str | None = None,
    requested_by: str | None = None,
    requester_email: str | None = None,
    status: str = "DRAFT",
) -> dict:
    order_date = date.today()
    requested_by = requested_by or DEFAULT_REQUESTER
    requester_email = requester_email or DEFAULT_REQUESTER_EMAIL
    sup = supplier_for_region(region)
    ship_to = ship_to or sup.get("warehouse")
    region = sup.get("region", region)
    if not needed_by:
        needed_by = (order_date + timedelta(days=lead_time_days or 7)).isoformat()
    if not reason:
        reason = "Replenishment of out-of-stock part"

    qty = int(quantity)
    line_total = round(float(unit_cost) * qty, 2)
    po_number = _po_number(part_id, qty, requested_by, order_date)
    subject = f"Purchase Order {po_number} - {name} x{qty}"

    text = _render_text(
        po_number=po_number, order_date=order_date.isoformat(), status=status,
        requested_by=requested_by, requester_email=requester_email,
        supplier=sup, ship_to=ship_to, region=region,
        part_id=part_id, name=name, unit=unit, qty=qty,
        unit_cost=unit_cost, line_total=line_total,
        reason=reason, well_id=well_id or "-",
        lead_time=lead_time_days, needed_by=needed_by)
    html = _render_html(
        po_number=po_number, order_date=order_date.isoformat(),
        requested_by=requested_by, requester_email=requester_email,
        supplier=sup, ship_to=ship_to, region=region,
        part_id=part_id, name=name, unit=unit, qty=qty,
        unit_cost=unit_cost, line_total=line_total,
        reason=reason, well_id=well_id or "-",
        lead_time=lead_time_days, needed_by=needed_by)

    to = sup["email"]
    cc = requester_email
    mailto = ("mailto:" + urllib.parse.quote(to)
              + "?cc=" + urllib.parse.quote(cc)
              + "&subject=" + urllib.parse.quote(subject)
              + "&body=" + urllib.parse.quote(text))

    return {
        "po_number": po_number,
        "status": status,
        "order_date": order_date.isoformat(),
        "buyer": {"company": BUYER_COMPANY, "requested_by": requested_by,
                  "email": requester_email},
        "supplier": {"company": sup["company"], "email": sup["email"],
                     "region": region},
        "ship_to": ship_to,
        "line_items": [{
            "line": 1, "part_id": part_id, "description": name,
            "quantity": qty, "unit": unit, "unit_cost_usd": round(float(unit_cost), 2),
            "line_total_usd": line_total,
        }],
        "subtotal_usd": line_total,
        "currency": "USD",
        "reason": reason,
        "well_ref": well_id or None,
        "lead_time_days": lead_time_days,
        "needed_by": needed_by,
        "email": {"to": to, "cc": cc, "subject": subject},
        "mailto": mailto,
        "document_text": text,
        "document_html": html,
    }


def _render_text(**k) -> str:
    return f"""\
================= PURCHASE ORDER =================
PO Number   : {k['po_number']}
Order Date  : {k['order_date']}
Status      : {k['status']}

BUYER
  Company      : {BUYER_COMPANY}
  Requested by : {k['requested_by']}
  Contact      : {k['requester_email']}

SUPPLIER
  Company      : {k['supplier']['company']}
  Email        : {k['supplier']['email']}
  Region       : {k['region']}

SHIP TO
  Warehouse    : {k['ship_to']}

LINE ITEMS
  #  Part ID    Description                                Qty  Unit    Unit Cost      Line Total
  1  {k['part_id']:<9}  {k['name']:<40}  {k['qty']:>3}  {k['unit']:<6}  ${k['unit_cost']:>10,.2f}  ${k['line_total']:>12,.2f}

  Subtotal (USD): ${k['line_total']:,.2f}

DETAILS
  Reason        : {k['reason']}
  Well ref      : {k['well_id']}
  Supplier lead : {k['lead_time']} days
  Needed by     : {k['needed_by']}

Notes: Generated by the Drilling Hotspots Agent procurement assistant.
=================================================="""


def _render_html(**k) -> str:
    return f"""\
<div style="font-family:Segoe UI,Arial,sans-serif;color:#222;max-width:640px">
  <h2 style="margin:0 0 4px">Purchase Order {k['po_number']}</h2>
  <div style="color:#666;font-size:13px">Order date: {k['order_date']}</div>
  <table style="width:100%;margin-top:12px;font-size:13px;border-collapse:collapse">
    <tr><td style="vertical-align:top;width:50%">
      <b>Buyer</b><br>{BUYER_COMPANY}<br>Requested by: {k['requested_by']}<br>{k['requester_email']}
    </td><td style="vertical-align:top">
      <b>Supplier</b><br>{k['supplier']['company']}<br>{k['supplier']['email']}<br>Region: {k['region']}
    </td></tr>
  </table>
  <div style="margin-top:8px;font-size:13px"><b>Ship to:</b> {k['ship_to']}</div>
  <table style="width:100%;margin-top:12px;font-size:13px;border-collapse:collapse">
    <tr style="background:#f2f4f7"><th style="text-align:left;padding:6px">Part ID</th>
      <th style="text-align:left;padding:6px">Description</th>
      <th style="text-align:right;padding:6px">Qty</th>
      <th style="text-align:right;padding:6px">Unit cost</th>
      <th style="text-align:right;padding:6px">Line total</th></tr>
    <tr><td style="padding:6px">{k['part_id']}</td><td style="padding:6px">{k['name']}</td>
      <td style="text-align:right;padding:6px">{k['qty']} {k['unit']}</td>
      <td style="text-align:right;padding:6px">${k['unit_cost']:,.2f}</td>
      <td style="text-align:right;padding:6px">${k['line_total']:,.2f}</td></tr>
    <tr><td colspan="4" style="text-align:right;padding:6px"><b>Subtotal (USD)</b></td>
      <td style="text-align:right;padding:6px"><b>${k['line_total']:,.2f}</b></td></tr>
  </table>
  <div style="margin-top:10px;font-size:13px">
    <b>Reason:</b> {k['reason']}<br>
    <b>Well ref:</b> {k['well_id']} &nbsp; <b>Supplier lead:</b> {k['lead_time']} days &nbsp;
    <b>Needed by:</b> {k['needed_by']}
  </div>
  <div style="margin-top:12px;color:#888;font-size:12px">Generated by the Drilling Hotspots Agent procurement assistant.</div>
</div>"""


def send_po(po: dict) -> dict:
    """Send the purchase order to the supplier and record it in the history."""
    OUTBOX.mkdir(parents=True, exist_ok=True)
    po = {**po, "status": "SENT"}
    po["document_text"] = po["document_text"].replace(
        "Status      : DRAFT", "Status      : SENT")
    stem = OUTBOX / po["po_number"]
    stem.with_suffix(".txt").write_text(po["document_text"], encoding="utf-8")
    stem.with_suffix(".json").write_text(json.dumps(po, indent=2), encoding="utf-8")
    entry = po_history.record(po)
    return {
        "sent": True,
        "po_number": po["po_number"],
        "status": "SENT",
        "sent_at": entry["sent_at"],
        "to": po["email"]["to"],
        "cc": po["email"]["cc"],
        "subject": po["email"]["subject"],
        "supplier": po["supplier"]["company"],
        "mailto": po["mailto"],
        "message": (f"Purchase order {po['po_number']} sent to "
                    f"{po['supplier']['company']} <{po['email']['to']}>, "
                    f"cc {po['email']['cc']}. Recorded in the purchase-order history."),
        "document_text": po["document_text"],
    }
