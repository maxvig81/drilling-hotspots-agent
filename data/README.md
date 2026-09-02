# data

Synthetic drilling-well dataset and its generator.

## Generate

```powershell
python generate_wells.py --count 60 --seed 42
```

Writes `wells_<timestamp>.geojson` — a GeoJSON `FeatureCollection` where each
feature is one well (a `Point`) with these properties:

| Property | Meaning |
|----------|---------|
| `id`, `name` | Well identifier (e.g. `NS-014`) and display name. |
| `basin`, `basin_key`, `country`, `region` | Location grouping. |
| `operator`, `offshore` | Operating company; offshore vs onshore. |
| `status` / `status_label` | `producing` · `shut-in` · `drilling` · `maintenance`. |
| `type` / `type_label` | `oil` · `gas` · `injection` · `exploration`. |
| `production_bbl_d` | Production rate, barrels/day (0 for non-producing/injection). |
| `wellhead_pressure_psi` | Wellhead pressure, psi. |
| `depth_m` | Well depth, metres. |
| `water_cut_pct` | Water cut, % (null where not applicable). |
| `alerts`, `alert_count`, `health` | Active anomalies + derived health (nominal/watch/warning/critical). |
| `spud_date`, `last_update` | Timestamps for realism. |

Wells are scattered across 8 world basins defined in `basins.py`
(North Sea, Gulf of Mexico, Permian, Ghawar/Persian Gulf, Campos, Niger Delta,
West Siberia, Bohai Bay). Generation is deterministic for a given `--seed`.

The MCP server auto-loads the most recent `wells_*.geojson` in this folder
(override with the `WELLS_DATA_PATH` environment variable).

> This is **synthetic demo data** — not real well locations or measurements.
