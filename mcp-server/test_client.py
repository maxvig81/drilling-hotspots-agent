"""Tiny MCP client that exercises the server's tools over streamable HTTP.

Run the server first (``python server.py``), then in another shell:
    python test_client.py
"""
from __future__ import annotations

import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.environ.get("MCP_URL", "http://localhost:8000/mcp/")


async def main() -> None:
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            res = await session.call_tool("get_wells_summary", {})
            print("\nget_wells_summary:")
            print(res.content[0].text[:800])

            res = await session.call_tool(
                "list_wells", {"only_alerts": True, "limit": 3})
            print("\nlist_wells(only_alerts, limit=3):")
            data = json.loads(res.content[0].text)
            print("  returned:", data["returned"])
            for w in data["wells"]:
                print(f"   {w['id']:8} {w['status']:11} {w['type']:18} "
                      f"alerts={w['alerts']}")

            res = await session.call_tool("show_wells_map", {"area": "North Sea"})
            print("\nshow_wells_map(area='North Sea'):")
            print(" ", res.content[0].text[:300])

            resources = await session.list_resources()
            print("\nRESOURCES:", [r.uri for r in resources.resources])


if __name__ == "__main__":
    asyncio.run(main())
