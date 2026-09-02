# mcp-server

Python MCP **app server** that serves the synthetic drilling-well data to the
declarative agent and returns the interactive map widget.

- **Transport:** streamable HTTP (stateless), so it can sit behind a dev tunnel
  and be consumed by Microsoft 365 Copilot as a `RemoteMCPServer` plugin action.
- **MCP endpoint:** `/mcp/`  ·  **Health:** `/health`  ·  browser test payload:
  `/wells?area=North%20Sea&bbox=-3.5,55.5,8,61.5`
- **Default port:** `8010` (override with the `PORT` env var). Port 8010 is used
  to avoid colliding with other local MCP servers on 8000.

## Tools

| Tool | Purpose |
|------|---------|
| `get_wells_summary` | Fleet-wide aggregate stats (by status/type/basin, production, alerts). |
| `list_wells` | Filtered list of wells with KPIs (status, type, basin, only_alerts, bbox). |
| `get_well_details` | Full detail for a single well by id (e.g. `NS-014`). |
| `show_wells_map` | **MCP Apps UI widget** — interactive map with status markers + popups. |

`show_wells_map` declares `_meta.ui.resourceUri = ui://wells/wells-map.html`.
The server serves that resource (mime `text/html;profile=mcp-app`) from
`assets/widget.html`, which is a fully self-contained page (JS + base map inlined
at build time — the Copilot sandbox blocks network access from the widget).

The map widget supports: status-coloured well markers with a **click-to-open KPI
popup** (production, wellhead pressure, water cut, depth), a toggleable status
legend, pan/zoom, and **two optional overlay layers** — 🏭 parts-stock
warehouses and 👷 maintenance-crew bases. Those two layers are aggregated by
`hubs.py` (which reads the sibling `inventory-mcp` and `crew-mcp` datasets and
attaches a coordinate to each regional hub) and travel inside the
`show_wells_map` payload, so the widget needs no cross-server calls.

## Run

```powershell
pip install -r requirements.txt
python server.py                 # or: pwsh -File run.ps1  (also hosts the tunnel)
python test_client.py            # exercise the tools over the MCP protocol
```

## Rebuild the map widget

The widget is bundled from `widget-src/` into `assets/widget.html`:

```powershell
cd widget-src
npm install
python build_outline.py          # (re)fetch + simplify the world base map -> assets/*.json
npm run build                    # bundle main.js + base map -> ../assets/widget.html
python build_preview.py          # optional: write preview.html to open in a browser
```

## Dev tunnel

The agent must reach this server over a public HTTPS URL. The `wells-mcp` tunnel
forwards to local `:8010`:

```powershell
devtunnel create wells-mcp
devtunnel port create wells-mcp -p 8010
devtunnel access create wells-mcp -p 8010 --anonymous
devtunnel host wells-mcp         # prints the public URL
```

Put `<public-host>/mcp/` into `agent/appPackage/wells-plugin.json`
(`runtimes[0].spec.url`) and add `<public-host>` to `validDomains` in
`agent/appPackage/manifest.json`.
