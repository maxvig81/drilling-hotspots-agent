# Drilling Hotspots Agent

A Microsoft 365 Copilot **declarative agent** for **operational piloting of an
oil & gas drilling-well fleet**. It shows the wells on an interactive world map,
reports their operational KPIs, and surfaces *operational hotspots* — wells with
active alerts that need attention. Well data is entirely **synthetic** (generated
for a realistic demo) and served to Copilot through an **MCP (Model Context
Protocol) app server** that also returns an interactive **MCP Apps map widget**.

The agent is backed by **three MCP servers** so it can go beyond visualization
and actually help **organize a maintenance**: for a technical problem on a well
(e.g. an annulus overpressure) it can check whether the **spare parts** are in
stock and find **from when a maintenance crew** can intervene — then propose the
earliest feasible start date.

Ask the agent things like:

- *"Show me the map of all our drilling wells worldwide"*
- *"Which wells currently have active alerts and need attention?"*
- *"Show the drilling wells in the North Sea on the map"*
- *"Give me a fleet summary: producing vs shut-in vs drilling vs maintenance"*
- *"Give me the full operational details for well NS-014"*
- *"Well GOM-011 has an annulus overpressure — organize a maintenance: which parts do we have and when can a crew intervene?"*

The map has status-coloured markers (producing / shut-in / drilling /
maintenance), red rings around critical wells, a click-to-open KPI popup per
well, a status legend you can toggle, and pan/zoom.

## Repository layout

```
.
├── data/           # Synthetic well-data generator + the generated dataset
│   ├── basins.py            #   the 8 world basins wells are scattered across
│   ├── generate_wells.py    #   deterministic generator -> wells_<timestamp>.geojson
│   └── wells_*.geojson      #   the generated dataset the server serves
├── shared/         # Shared failure/issue taxonomy used by all three servers
│   └── issues.py            #   failure codes -> label, crew specialty, EN/FR synonyms
├── mcp-server/     # Wells MCP app server (Python): tools + interactive map widget
│   ├── server.py            #   MCP server (streamable HTTP, :8010): 4 tools + UI resource
│   ├── well_data.py, geo.py
│   ├── assets/, widget-src/ #   built widget.html + widget SOURCE
│   └── run.ps1, test_client.py, requirements.txt
├── inventory-mcp/  # Parts-inventory MCP server (:8011) + its data + generator
│   ├── generate_parts.py    #   fictitious spare-parts stock -> parts_<ts>.json
│   ├── parts_data.py, server.py
│   └── run.ps1, requirements.txt
├── crew-mcp/       # Maintenance-crew MCP server (:8012) + its data + generator
│   ├── generate_crews.py    #   fictitious crews + availability -> crews_<ts>.json
│   ├── crew_data.py, server.py
│   └── run.ps1, requirements.txt
└── agent/          # The M365 declarative agent (Agents Toolkit / wiqd project)
    ├── appPackage/          #   manifest.json, declarativeAgent.json, instruction.txt,
    │                        #   wells-plugin.json, parts-plugin.json, crews-plugin.json, icons
    ├── env/                 #   environment files
    ├── evals/               #   evaluation prompts
    └── m365agents.yml       #   provisioning lifecycle
```

## The three MCP servers

| Server | Folder | Port | Tunnel | Tools |
|--------|--------|------|--------|-------|
| Wells | `mcp-server/` | 8010 | `wells-mcp` | get_wells_summary, list_wells, get_well_details, **show_wells_map** (map widget) |
| Parts inventory | `inventory-mcp/` | 8011 | `parts-mcp` | get_inventory_summary, list_parts, check_part_availability, find_parts_for_issue, **create_purchase_order**, **send_purchase_order**, **list_purchase_orders**, **get_purchase_order** |
| Maintenance crews | `crew-mcp/` | 8012 | `crews-mcp` | get_crews_summary, list_crews, find_available_crew |

Each is registered as a separate action in `agent/appPackage/declarativeAgent.json`
(`wells-plugin.json`, `parts-plugin.json`, `crews-plugin.json`) and its tunnel
host is whitelisted in `manifest.json` (`validDomains`).

## How it fits together

```
data / inventory-mcp / crew-mcp generators ──► *.geojson / *.json datasets
                                   │
                                   ▼
   three MCP servers (streamable HTTP)  ──► wells / parts / crews tools
                                   │   (show_wells_map returns an MCP Apps UI widget)
                                   ▼
        three dev tunnels (public HTTPS)  ──► referenced by the three *-plugin.json
                                   │
                                   ▼
   Microsoft 365 Copilot renders the agent, the map, and orchestrates maintenance
```

**Maintenance orchestration.** For a well problem, the agent chains the servers:
`get_well_details` (basin + alert) → `find_parts_for_issue` (parts in stock?) →
`find_available_crew` (earliest crew for that region) → proposes the earliest
feasible start date (the later of parts-ready and crew-available), flagging the
limiting factor. A shared taxonomy (`shared/issues.py`) maps a plain-language
problem — English or French, e.g. *"surpression de l'anneau"* — to the same
failure code across wells, parts and crews.

**Ordering out-of-stock parts & order history.** When a part is out of stock,
the agent can raise a purchase order: `create_purchase_order` fills an English
PO template (deterministic PO number, nominated regional supplier, line item,
subtotal) for review; after the user confirms, `send_purchase_order` emails it
to the supplier (cc the requester) and records it in the **order history**
(`inventory-mcp/po_history.json`, with a document copy in
`inventory-mcp/outbox/`). `list_purchase_orders` and `get_purchase_order` let
the agent confirm whether a specific part was ordered and retrieve past POs.
(In this environment, sent POs are written to the local history/outbox rather
than dispatched through a real mail server; supplier addresses use the reserved
`.example` TLD.)

## Quick start

### 1. Generate the data (once)

```powershell
cd data;          python generate_wells.py --count 60 --seed 42
cd ..\inventory-mcp; python generate_parts.py --seed 7
cd ..\crew-mcp;      python generate_crews.py --seed 11
```

### 2. Run the three MCP servers + public tunnels

Each server folder has a `run.ps1` that starts the server and hosts its dev
tunnel. Run each in its own terminal (install deps once with
`pip install -r requirements.txt`):

```powershell
cd mcp-server;    pwsh -File run.ps1     # wells   :8010  (tunnel wells-mcp)
cd inventory-mcp; pwsh -File run.ps1     # parts   :8011  (tunnel parts-mcp)
cd crew-mcp;      pwsh -File run.ps1     # crews   :8012  (tunnel crews-mcp)
```

Leave those windows open while using the agent. Sanity-check locally:

```powershell
Start-Process "http://localhost:8010/health"   # {"status":"ok","wells":60,...}
Start-Process "http://localhost:8011/health"   # {"status":"ok","stock_lines":57,...}
Start-Process "http://localhost:8012/health"   # {"status":"ok","crews":16,...}
```

To rebuild the map widget after changing `mcp-server/widget-src/`:

```powershell
cd mcp-server\widget-src
npm install
npm run build            # writes ../assets/widget.html
```

### 3. Provision the agent into Microsoft 365 Copilot

```powershell
cd ..\..\agent
wiqd agent validate
wiqd agent provision      # uploads the app and extends it to M365 Copilot
```

Then open Microsoft 365 Copilot, pick **Drilling Hotspots Agent**, and try one
of the conversation starters above.

> **Note on the dev tunnel URLs.** Each `*-plugin.json` (`runtimes[0].spec.url`)
> and `manifest.json` (`validDomains`) point at a specific dev-tunnel host:
> wells `1wsvgmch-8010`, parts `0g5b8whl-8011`, crews `m11q5trv-8012`
> (`*.uks1.devtunnels.ms`). If you recreate a tunnel and its host changes, update
> the URL in the matching plugin + `manifest.json` and re-provision.

## Disclaimer

All identifiers, coordinates, production figures, pressures, alerts, stock
levels and crew schedules are **synthetic demo data** produced by the generators
in `data/`, `inventory-mcp/` and `crew-mcp/`. They do not represent real wells,
inventory or crews. The base map is © Natural Earth.
