"""MCP server exposing the synthetic maintenance-crew availability referential.

Transport: streamable HTTP (stateless), consumed by Microsoft 365 Copilot as a
RemoteMCPServer plugin action.

Tools
-----
* ``get_crews_summary``    — crew overview (totals, by specialty, available now).
* ``list_crews``           — filtered list of crews.
* ``find_available_crew``  — earliest crew that can intervene for a given problem
                             / specialty and region (the maintenance scheduler).
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

from crew_data import get_data

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
from issues import SPECIALTY_LABELS  # noqa: E402

server = Server("drilling-maintenance-crews")
_SPEC_ENUM = list(SPECIALTY_LABELS)

TOOLS: list[types.Tool] = [
    types.Tool(
        name="get_crews_summary",
        description=(
            "Get an overview of the maintenance crews: total crews, how many are "
            "available now, breakdown by specialty (well integrity, artificial "
            "lift, sand control, flow assurance, HSE/sour, general) and by region "
            "coverage."
        ),
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool(
        name="list_crews",
        description=(
            "List maintenance crews, optionally filtered by specialty, the region "
            "or basin they cover, or those available within a number of days. Each "
            "crew shows its specialty, base, regions covered, size, current status "
            "and next available date."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "specialty": {"type": "string", "enum": _SPEC_ENUM,
                              "description": "Filter to a crew specialty."},
                "region": {"type": "string",
                           "description": "Filter to crews covering a basin/region, e.g. 'North Sea'."},
                "available_within_days": {"type": "integer", "minimum": 0, "maximum": 60,
                                          "description": "Only crews available within N days."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100,
                          "description": "Max crews to return (default 25)."},
            },
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
    types.Tool(
        name="find_available_crew",
        description=(
            "Find the maintenance crew that can intervene at the earliest for a "
            "given well problem and location. Provide the problem in plain "
            "language via `issue` (e.g. 'annulus overpressure', 'ESP failure', "
            "'surpression de l'anneau') — the right specialty is inferred — and/or "
            "a `specialty` directly, plus the `region`/basin of the well. Returns "
            "the earliest-available crew, its next available date, and up to a few "
            "alternative candidates, sorted by earliest availability."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "issue": {"type": "string",
                          "description": "The well problem to fix, e.g. 'annulus overpressure'."},
                "specialty": {"type": "string", "enum": _SPEC_ENUM,
                              "description": "Required specialty (if known instead of an issue)."},
                "region": {"type": "string",
                           "description": "Basin/region of the well, e.g. 'North Sea'."},
                "top": {"type": "integer", "minimum": 1, "maximum": 10,
                        "description": "How many candidate crews to return (default 3)."},
            },
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(readOnlyHint=True),
    ),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    print(">>> crews list_tools", flush=True)
    return TOOLS


def _text(obj: object) -> list[types.ContentBlock]:
    return [types.TextContent(type="text", text=json.dumps(obj, indent=2, default=str))]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> tuple[list[types.ContentBlock], dict]:
    print(f">>> crews call_tool name={name} args={arguments}", flush=True)
    data = get_data()
    args = arguments or {}

    if name == "get_crews_summary":
        s = data.summary()
        return _text(s), s

    if name == "list_crews":
        crews = data.query(
            specialty=args.get("specialty"),
            region=args.get("region"),
            available_within_days=args.get("available_within_days"),
            include_general=True,
            limit=args.get("limit", 25),
        )
        result = {
            "crews": [data._slim(c) for c in crews],
            "returned": len(crews),
            "summary": data.summary(crews),
        }
        return _text(result), result

    if name == "find_available_crew":
        r = data.find_available_crew(
            issue=args.get("issue"),
            specialty=args.get("specialty"),
            region=args.get("region"),
            top=args.get("top", 3),
        )
        c = r.get("earliest_crew")
        if c:
            when = "available now" if c["available_in_days"] == 0 \
                else f"available in {c['available_in_days']} day(s) ({c['next_available_date']})"
            job = r.get("issue_label") or r.get("required_specialty_label") or "the job"
            where = f" in {r['region']}" if r.get("region") else ""
            text = (f"Earliest crew for {job}{where}: {c['name']} "
                    f"({c['specialty_label']}, {c['members']} members, base {c['base']}) — {when}.")
            if r.get("region_constraint_relaxed"):
                text += " (No crew covers that exact region; showing nearest available.)"
        else:
            text = "No matching crew found."
        return [types.TextContent(type="text", text=text)], r

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
    return JSONResponse({"status": "ok", "crews": len(d.crews), "source": d.path.name})


async def index(_req: Request) -> PlainTextResponse:
    return PlainTextResponse("Drilling maintenance-crews MCP server. Endpoint: /mcp  Health: /health\n")


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
    port = int(os.environ.get("PORT", "8012"))
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
