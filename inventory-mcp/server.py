"""MCP server exposing the synthetic spare-parts inventory.

Transport: streamable HTTP (stateless), consumed by Microsoft 365 Copilot as a
RemoteMCPServer plugin action.

Tools
-----
* ``get_inventory_summary``   — stock overview (lines, distinct parts, categories).
* ``list_parts``              — filtered list of stock lines.
* ``check_part_availability`` — availability of a part (by id or name) across warehouses.
* ``find_parts_for_issue``    — parts required to fix a well problem + their availability.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import mcp.types as types
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from parts_data import get_data
from purchase_order import build_po, send_po
import po_history

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
from issues import ISSUE_CODES  # noqa: E402

server = Server("drilling-parts-inventory")
_ISSUE_HINT = ", ".join(f"'{c}'" for c in ISSUE_CODES)

TOOLS: list[types.Tool] = [
    types.Tool(
        name="get_inventory_summary",
        description=(
            "Get an overview of the spare-parts inventory: number of stock lines, "
            "distinct parts, how many lines are in stock vs out of stock, total "
            "units, breakdown by category, and number of warehouses."
        ),
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool(
        name="list_parts",
        description=(
            "List spare-parts stock lines, optionally filtered by category, stock "
            "status, a search term (part name or id), the failure/issue code a "
            "part addresses, or a warehouse region. Each line shows quantity, "
            "warehouse, region and reorder lead time."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string",
                             "description": "Filter by category, e.g. 'Wellhead', 'Downhole', "
                                            "'Artificial lift', 'Chemicals', 'Instrumentation'."},
                "in_stock": {"type": "boolean",
                             "description": "true = only in-stock lines, false = only out-of-stock."},
                "search": {"type": "string",
                           "description": "Match part name or id (e.g. 'packer', 'P-1005')."},
                "issue_code": {"type": "string",
                               "description": f"Filter to parts that address a failure code: {_ISSUE_HINT}."},
                "region": {"type": "string",
                           "description": "Filter by warehouse region/country, e.g. 'North Sea'."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200,
                          "description": "Max lines to return (default 25)."},
            },
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool(
        name="check_part_availability",
        description=(
            "Check the availability of a specific part by its id (e.g. 'P-1005') "
            "or name (e.g. 'annulus safety valve') across all warehouses: total "
            "units available, per-warehouse breakdown, and reorder lead time if "
            "out of stock."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "part": {"type": "string",
                         "description": "Part id or name to look up."},
            },
            "required": ["part"],
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool(
        name="find_parts_for_issue",
        description=(
            "Given a well problem described in plain language (e.g. 'annulus "
            "overpressure', 'ESP failure', 'H2S', 'surpression de l'anneau'), "
            "return the spare parts required to fix it and whether each is in "
            "stock, with a summary of whether all parts are available and, if "
            "not, in how many days they can be on hand. Optionally restrict to a "
            "warehouse region to prefer local stock."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "issue": {"type": "string",
                          "description": "The problem to fix, e.g. 'annulus overpressure'."},
                "region": {"type": "string",
                           "description": "Optional warehouse region to prefer, e.g. 'North Sea'."},
            },
            "required": ["issue"],
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool(
        name="create_purchase_order",
        description=(
            "Fill a purchase-order form (a DRAFT) to reorder a spare part, "
            "typically one that is out of stock. Provide the part (id or name) "
            "and quantity; the tool resolves the part's unit cost and supplier "
            "lead time, picks the nominated supplier for the region, and returns "
            "a fully formatted purchase order (PO number, buyer, supplier, "
            "line item, subtotal) ready for review. This does NOT send anything "
            "— present the draft to the user, then use send_purchase_order once "
            "they confirm."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "part": {"type": "string",
                         "description": "Part id or name to order, e.g. 'P-1002' or 'casing head pack-off'."},
                "quantity": {"type": "integer", "minimum": 1, "maximum": 500,
                             "description": "Quantity to order (default 1)."},
                "region": {"type": "string",
                           "description": "Region/basin whose supplier to order from, e.g. 'Gulf of Mexico'."},
                "well_id": {"type": "string",
                            "description": "Optional well reference the order relates to, e.g. 'GOM-011'."},
                "needed_by": {"type": "string",
                              "description": "Optional required delivery date (YYYY-MM-DD)."},
                "reason": {"type": "string",
                           "description": "Optional reason/justification for the order."},
                "requested_by": {"type": "string",
                                 "description": "Name of the person raising the order."},
                "requester_email": {"type": "string",
                                    "description": "Requester email (used as CC / buyer contact)."},
            },
            "required": ["part"],
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool(
        name="send_purchase_order",
        description=(
            "Send a spare-part purchase order by email to the supplier, with the "
            "requester in CC. Takes the same inputs as create_purchase_order and "
            "rebuilds the identical PO (same PO number), then sends it and records "
            "it in the purchase-order history. Only call this after the user has "
            "confirmed the draft."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "part": {"type": "string",
                         "description": "Part id or name to order."},
                "quantity": {"type": "integer", "minimum": 1, "maximum": 500,
                             "description": "Quantity to order (default 1)."},
                "region": {"type": "string",
                           "description": "Region/basin whose supplier to order from."},
                "well_id": {"type": "string",
                            "description": "Optional well reference the order relates to."},
                "needed_by": {"type": "string",
                              "description": "Optional required delivery date (YYYY-MM-DD)."},
                "reason": {"type": "string",
                           "description": "Optional reason/justification for the order."},
                "requested_by": {"type": "string",
                                 "description": "Name of the person raising the order."},
                "requester_email": {"type": "string",
                                    "description": "Requester email (used as CC / buyer contact)."},
            },
            "required": ["part"],
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=False),
    ),
    types.Tool(
        name="list_purchase_orders",
        description=(
            "Search the history of purchase orders that have been placed, to "
            "confirm whether a part was ordered or review recent orders. Filter "
            "by part (id or name), well reference, PO number, supplier, or status. "
            "Returns matching orders (PO number, part, quantity, supplier, date, "
            "well reference) newest first."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "part": {"type": "string",
                         "description": "Part id or name to look for, e.g. 'P-1002' or 'pack-off'."},
                "well_id": {"type": "string",
                            "description": "Well reference the order was raised for, e.g. 'GOM-011'."},
                "po_number": {"type": "string",
                              "description": "A specific PO number, e.g. 'PO-20260902-A2F83'."},
                "supplier": {"type": "string",
                             "description": "Supplier company name (partial match)."},
                "status": {"type": "string",
                           "description": "Filter by status (currently 'SENT')."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200,
                          "description": "Max orders to return (default 25)."},
            },
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool(
        name="get_purchase_order",
        description=(
            "Get the full detail of a single purchase order from the history by "
            "its PO number, including the formatted purchase-order document."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "po_number": {"type": "string",
                              "description": "The PO number, e.g. 'PO-20260902-A2F83'."},
            },
            "required": ["po_number"],
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    print(">>> parts list_tools", flush=True)
    return TOOLS


def _text(obj: object) -> list[types.ContentBlock]:
    return [types.TextContent(type="text", text=json.dumps(obj, indent=2, default=str))]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> tuple[list[types.ContentBlock], dict]:
    print(f">>> parts call_tool name={name} args={arguments}", flush=True)
    data = get_data()
    args = arguments or {}

    if name == "get_inventory_summary":
        s = data.summary()
        return _text(s), s

    if name == "list_parts":
        recs = data.query(
            category=args.get("category"),
            in_stock=args.get("in_stock"),
            search=args.get("search"),
            issue_code=args.get("issue_code"),
            region=args.get("region"),
            limit=args.get("limit", 25),
        )
        result = {
            "parts": [
                {"part_id": r["part_id"], "name": r["name"], "category": r["category"],
                 "quantity": r["quantity"], "in_stock": r["in_stock"],
                 "warehouse": r["warehouse_name"], "region": r["region"],
                 "lead_time_days": r["lead_time_days"],
                 "addresses": r["addresses"]}
                for r in recs
            ],
            "returned": len(recs),
            "summary": data.summary(recs),
        }
        return _text(result), result

    if name == "check_part_availability":
        r = data.check_part(args.get("part", ""))
        if r.get("found"):
            loc = ", ".join(f"{l['quantity']}×{l['warehouse']}" for l in r["locations"])
            text = (f"{r['name']} ({r['part_id']}): "
                    + (f"{r['total_units_available']} unit(s) in stock ({loc})."
                       if r["in_stock"] else
                       f"OUT OF STOCK — reorder lead time {r['reorder_lead_time_days']} days."))
        else:
            text = r.get("message", "Not found.")
        return [types.TextContent(type="text", text=text)], r

    if name == "find_parts_for_issue":
        r = data.parts_for_issue(args.get("issue", ""), region=args.get("region"))
        if not r.get("resolved"):
            return [types.TextContent(type="text", text=r.get("message", "Unknown issue."))], r
        if r["all_in_stock"]:
            text = (f"All {r['part_count']} part(s) for '{r['issue_label']}' are in "
                    f"stock: {', '.join(p['name'] for p in r['required_parts'])}.")
        else:
            text = (f"{r['part_count']} part(s) needed for '{r['issue_label']}'; "
                    f"missing: {', '.join(r['missing_parts'])} "
                    f"(available in {r['parts_ready_in_days']} days).")
        return [types.TextContent(type="text", text=text)], r

    if name in ("create_purchase_order", "send_purchase_order"):
        term = args.get("part", "")
        info = data.resolve_for_order(term, region=args.get("region"))
        if not info:
            msg = {"error": f"No part matches '{term}'."}
            return _text(msg), msg
        po = build_po(
            part_id=info["part_id"], name=info["name"], category=info["category"],
            unit=info["unit"], unit_cost=info["unit_cost"],
            lead_time_days=info["lead_time_days"], quantity=args.get("quantity", 1),
            region=info["region"], well_id=args.get("well_id"),
            needed_by=args.get("needed_by"), reason=args.get("reason"),
            requested_by=args.get("requested_by"),
            requester_email=args.get("requester_email"),
            status="DRAFT",
        )
        if name == "create_purchase_order":
            text = ("DRAFT purchase order ready — review, then confirm to send.\n\n"
                    + po["document_text"]
                    + f"\n\nWill be emailed to {po['email']['to']} "
                      f"(cc {po['email']['cc']}) on confirmation.")
            return [types.TextContent(type="text", text=text)], po
        # send_purchase_order
        result = send_po(po)
        return [types.TextContent(type="text", text=result["message"])], result

    if name == "list_purchase_orders":
        r = po_history.query(
            part=args.get("part"), well_id=args.get("well_id"),
            po_number=args.get("po_number"), supplier=args.get("supplier"),
            status=args.get("status"), limit=args.get("limit", 25),
        )
        if r["total_matches"] == 0:
            filt = args.get("part") or args.get("well_id") or args.get("po_number") or "the given filters"
            text = f"No purchase orders found for {filt}."
        else:
            lines = "; ".join(
                f"{o['po_number']}: {o['part_name']} ×{o['quantity']} "
                f"({o['supplier']}, {o['sent_at'][:10]}"
                + (f", {o['well_ref']}" if o.get('well_ref') else "") + ")"
                for o in r["orders"][:5])
            text = f"{r['total_matches']} purchase order(s) found. {lines}."
        return [types.TextContent(type="text", text=text)], r

    if name == "get_purchase_order":
        po_rec = po_history.get(args.get("po_number", ""))
        if not po_rec:
            msg = {"error": f"No purchase order found with number '{args.get('po_number')}'."}
            return _text(msg), msg
        return [types.TextContent(type="text", text=po_rec.get("document_text", ""))], po_rec

    raise ValueError(f"Unknown tool: {name}")


session_manager = StreamableHTTPSessionManager(
    app=server,
    stateless=True,
    security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


async def handle_mcp(scope, receive, send) -> None:
    await session_manager.handle_request(scope, receive, send)


async def health(_req: Request) -> JSONResponse:
    d = get_data()
    return JSONResponse({"status": "ok", "stock_lines": len(d.records),
                         "source": d.path.name})


async def index(_req: Request) -> PlainTextResponse:
    return PlainTextResponse("Drilling parts-inventory MCP server. Endpoint: /mcp  Health: /health\n")


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    get_data()
    async with session_manager.run():
        yield


app = Starlette(
    debug=False,
    lifespan=lifespan,
    routes=[
        Route("/", index),
        Route("/health", health),
        Mount("/mcp", app=handle_mcp),
    ],
)


def main() -> None:
    import asyncio
    import socket

    host = os.environ.get("HOST", "::")
    port = int(os.environ.get("PORT", "8011"))
    config = uvicorn.Config(app, log_level="info")
    srv = uvicorn.Server(config)
    if host in ("::", "dual"):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except (AttributeError, OSError):
            pass
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("::", port))
        sock.listen()
        asyncio.run(srv.serve(sockets=[sock]))
    else:
        config.host = host
        config.port = port
        asyncio.run(srv.serve())


if __name__ == "__main__":
    main()
