"""MCP server exposing synthetic drilling-well data with an interactive map.

Transport: streamable HTTP (stateless) so it can sit behind a dev tunnel and be
consumed by Microsoft 365 Copilot as a RemoteMCPServer plugin action.

Tools
-----
* ``get_wells_summary`` — aggregate operational stats (counts by status / type /
                          basin, total production, alert counts, bbox).
* ``list_wells``        — filtered list of individual wells with their KPIs.
* ``get_well_details``  — full operational detail for a single well by id.
* ``show_wells_map``    — MCP Apps UI widget: an inline map of the wells, with
                          status-coloured markers and click-to-open popups
                          (declares ``_meta.ui.resourceUri`` -> ui://wells/...).

The widget HTML resource (``ui://wells/wells-map.html``) is served with the MCP
Apps mime type; the base map outline is bundled into it at build time.
"""
from __future__ import annotations

import contextlib
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import mcp.types as types
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from well_data import get_data
from geo import resolve_area, AREAS
import hubs

HERE = Path(__file__).resolve().parent
WIDGET_URI = "ui://wells/wells-map.html"
WIDGET_MIME = "text/html;profile=mcp-app"

server = Server("drilling-hotspots")

_STATUS_ENUM = ["producing", "shut-in", "drilling", "maintenance"]
_TYPE_ENUM = ["oil", "gas", "injection", "exploration"]
_AREA_HINT = ", ".join(f"'{k}'" for k in AREAS)


# --------------------------------------------------------------------------- #
# Widget HTML (built by widget-src/build-widget.mjs, cached in memory)
# --------------------------------------------------------------------------- #
_WIDGET_HTML: str | None = None


def widget_html() -> str:
    global _WIDGET_HTML
    if _WIDGET_HTML is None:
        _WIDGET_HTML = (HERE / "assets" / "widget.html").read_text(encoding="utf-8")
    return _WIDGET_HTML


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
TOOLS: list[types.Tool] = [
    types.Tool(
        name="get_wells_summary",
        description=(
            "Get aggregate operational statistics for the drilling-well fleet: "
            "total wells, breakdown by status (producing/shut-in/drilling/"
            "maintenance), by well type (oil/gas/injection/exploration) and by "
            "basin, total production (bbl/day), number of wells with active "
            "alerts, and the number of critical wells."
        ),
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool(
        name="list_wells",
        description=(
            "List individual drilling wells with their operational KPIs "
            "(status, type, production bbl/day, wellhead pressure, depth, water "
            "cut, alerts), optionally filtered by status, well type, basin or "
            "country, whether they currently have alerts, or a geographic "
            "bounding box. Use `only_alerts=true` to surface operational "
            "hotspots (wells needing attention)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": _STATUS_ENUM,
                           "description": "Filter to a single well status."},
                "type": {"type": "string", "enum": _TYPE_ENUM,
                         "description": "Filter to a single well type."},
                "basin": {"type": "string",
                          "description": f"Filter to a basin or country, e.g. {_AREA_HINT}."},
                "only_alerts": {"type": "boolean",
                                "description": "Keep only wells with active alerts."},
                "bbox": {"type": "array", "items": {"type": "number"},
                         "minItems": 4, "maxItems": 4,
                         "description": "Bounding box [minLon, minLat, maxLon, maxLat]."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200,
                          "description": "Max wells to return (default 25)."},
            },
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool(
        name="get_well_details",
        description=(
            "Get the full operational detail for a single well by its id (e.g. "
            "'NS-014', 'GOM-021'): status, type, production, wellhead pressure, "
            "depth, water cut, operator, basin, spud date, last update, and the "
            "list of active alerts with their severity."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "well_id": {"type": "string",
                            "description": "Well identifier, e.g. 'NS-014'."},
            },
            "required": ["well_id"],
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool.model_validate({
        "name": "show_wells_map",
        "description": (
            "Display an interactive map of the drilling wells with markers "
            "coloured by status and click-to-open popups showing each well's "
            "KPIs. The default view shows all wells worldwide; zoom to a basin "
            f"or country via `area` (e.g. {_AREA_HINT}) or an explicit `bbox`, "
            "and filter by status, well type, or `only_alerts` to focus on "
            "operational hotspots. Renders an inline, pan/zoomable map widget."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "area": {"type": "string",
                         "description": f"Basin or country to zoom to, e.g. {_AREA_HINT}."},
                "status": {"type": "string", "enum": _STATUS_ENUM,
                           "description": "Filter to a single well status."},
                "type": {"type": "string", "enum": _TYPE_ENUM,
                         "description": "Filter to a single well type."},
                "only_alerts": {"type": "boolean",
                                "description": "Show only wells with active alerts."},
                "bbox": {"type": "array", "items": {"type": "number"},
                         "minItems": 4, "maxItems": 4,
                         "description": "Explicit zoom/filter box [minLon, minLat, "
                                        "maxLon, maxLat]."},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
        "_meta": {"ui": {"resourceUri": WIDGET_URI, "visibility": ["model", "app"]}},
    }),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    print(">>> MCP list_tools", flush=True)
    return TOOLS


def _text(obj: object) -> list[types.ContentBlock]:
    return [types.TextContent(type="text", text=json.dumps(obj, indent=2, default=str))]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> tuple[list[types.ContentBlock], dict]:
    print(f">>> MCP call_tool name={name} args={arguments}", flush=True)
    data = get_data()
    args = arguments or {}

    if name == "get_wells_summary":
        summary = data.summary()
        return _text(summary), summary

    if name == "list_wells":
        wells = data.query(
            status=args.get("status"),
            well_type=args.get("type"),
            basin=args.get("basin"),
            only_alerts=args.get("only_alerts"),
            bbox=args.get("bbox"),
            limit=args.get("limit", 25),
        )
        summary = data.summary(wells)
        result = {
            "wells": [
                {"id": w["id"], "name": w["name"], "basin": w["basin"],
                 "country": w["country"], "lat": round(w["lat"], 4),
                 "lon": round(w["lon"], 4), "status": w["status_label"],
                 "type": w["type_label"],
                 "production_bbl_d": w["production_bbl_d"],
                 "wellhead_pressure_psi": w["wellhead_pressure_psi"],
                 "depth_m": w["depth_m"], "water_cut_pct": w["water_cut_pct"],
                 "alerts": [a["label"] for a in (w["alerts"] or [])],
                 "health": w["health"]}
                for w in wells
            ],
            "returned": len(wells),
            "summary": summary,
        }
        return _text(result), result

    if name == "get_well_details":
        w = data.get(args.get("well_id", ""))
        if not w:
            msg = {"error": f"No well found with id '{args.get('well_id')}'."}
            return _text(msg), msg
        detail = {k: v for k, v in w.items()}
        text = (
            f"{w['name']} ({w['id']}) — {w['status_label']} {w['type_label']} in "
            f"{w['basin']}, {w['country']}. Production {w['production_bbl_d']} bbl/d, "
            f"wellhead {w['wellhead_pressure_psi']} psi, depth {w['depth_m']} m, "
            f"water cut {w['water_cut_pct']}%. Alerts: "
            + (", ".join(a["label"] for a in (w["alerts"] or [])) or "none") + "."
        )
        return [types.TextContent(type="text", text=text)], detail

    if name == "show_wells_map":
        view = None
        region_label = None
        if args.get("bbox"):
            view = list(args["bbox"])
            region_label = args.get("area")
        elif args.get("area"):
            resolved = resolve_area(args["area"])
            if resolved:
                view, region_label = resolved

        wells = data.query(
            status=args.get("status"),
            well_type=args.get("type"),
            only_alerts=args.get("only_alerts"),
            bbox=view,
        )
        summary = data.summary(wells)
        payload = data.map_payload(wells)
        payload["view"] = view
        payload["region_label"] = region_label
        payload["by_status"] = summary["by_status"]
        payload["by_health"] = summary["by_health"]
        payload["total_production_bbl_d"] = summary["total_production_bbl_d"]
        payload["wells_with_alerts"] = summary["wells_with_alerts"]
        payload["bbox"] = summary["bbox"]
        payload["total"] = summary["total"]
        payload["layers"] = hubs.build_layers()

        where = f" in {region_label}" if region_label else " worldwide"
        filt = []
        if args.get("status"):
            filt.append(args["status"])
        if args.get("type"):
            filt.append(args["type"])
        if args.get("only_alerts"):
            filt.append("with alerts")
        fstr = f" ({', '.join(filt)})" if filt else ""
        text = (
            f"Showing {summary['total']} wells{where}{fstr}. "
            f"By status: {summary['by_status']}. "
            f"{summary['wells_with_alerts']} well(s) with active alerts, "
            f"{summary['critical_wells']} critical. "
            f"Total production {summary['total_production_bbl_d']:,} bbl/day."
        )
        return [types.TextContent(type="text", text=text)], payload

    raise ValueError(f"Unknown tool: {name}")


# --------------------------------------------------------------------------- #
# Resources (the UI widget)
# --------------------------------------------------------------------------- #
@server.list_resources()
async def list_resources() -> list[types.Resource]:
    print(">>> MCP list_resources", flush=True)
    return [
        types.Resource(
            uri=WIDGET_URI,
            name="Drilling wells map",
            description="Interactive map widget for show_wells_map.",
            mimeType=WIDGET_MIME,
        )
    ]


@server.read_resource()
async def read_resource(uri) -> list[ReadResourceContents]:
    print(f">>> MCP read_resource uri={uri}", flush=True)
    if str(uri).rstrip("/") == WIDGET_URI:
        return [ReadResourceContents(content=widget_html(), mime_type=WIDGET_MIME)]
    raise ValueError(f"Unknown resource: {uri}")


# --------------------------------------------------------------------------- #
# ASGI app (stateless streamable HTTP)
# --------------------------------------------------------------------------- #
session_manager = StreamableHTTPSessionManager(
    app=server,
    stateless=True,
    security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


async def handle_mcp(scope, receive, send) -> None:
    await session_manager.handle_request(scope, receive, send)


async def health(_req: Request) -> JSONResponse:
    d = get_data()
    return JSONResponse({"status": "ok", "wells": len(d.wells),
                         "source": d.path.name})


async def wells_route(req: Request) -> JSONResponse:
    """Standalone/browser test endpoint mirroring show_wells_map's payload."""
    d = get_data()
    bbox = None
    raw = req.query_params.get("bbox")
    if raw:
        try:
            parts = [float(v) for v in raw.split(",")]
            if len(parts) == 4:
                bbox = parts
        except ValueError:
            bbox = None
    wells = d.query(
        status=req.query_params.get("status"),
        well_type=req.query_params.get("type"),
        only_alerts=req.query_params.get("only_alerts") in ("1", "true", "yes"),
        bbox=bbox,
    )
    summary = d.summary(wells)
    payload = d.map_payload(wells)
    payload["view"] = bbox
    payload["region_label"] = req.query_params.get("area")
    payload["by_status"] = summary["by_status"]
    payload["by_health"] = summary["by_health"]
    payload["total_production_bbl_d"] = summary["total_production_bbl_d"]
    payload["wells_with_alerts"] = summary["wells_with_alerts"]
    payload["total"] = summary["total"]
    payload["bbox"] = summary["bbox"]
    payload["layers"] = hubs.build_layers()
    return JSONResponse(payload)


async def index(_req: Request) -> PlainTextResponse:
    return PlainTextResponse(
        "Drilling Hotspots Agent MCP server. MCP endpoint: /mcp  Health: /health\n"
    )


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    get_data()  # warm the cache / fail fast if data is missing
    widget_html()
    async with session_manager.run():
        yield


app = Starlette(
    debug=False,
    lifespan=lifespan,
    routes=[
        Route("/", index),
        Route("/health", health),
        Route("/wells", wells_route),
        Mount("/mcp", app=handle_mcp),
    ],
)


def main() -> None:
    import asyncio
    import socket

    host = os.environ.get("HOST", "::")
    port = int(os.environ.get("PORT", "8000"))
    config = uvicorn.Config(app, log_level="info")
    srv = uvicorn.Server(config)

    # Dual-stack socket: accept both IPv4 (127.0.0.1) and IPv6 (::1) loopback so
    # `devtunnel host` reaches the server regardless of how it resolves
    # "localhost".
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
