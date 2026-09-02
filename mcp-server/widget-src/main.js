// Drilling Hotspots Agent — MCP Apps View (@modelcontextprotocol/ext-apps client).
//
// Renders an inline, pan/zoomable SVG world map of drilling wells: each well is a
// marker coloured by operational status, with a click-to-open popup of its KPIs.
// The base-map outline is bundled at build time; well data arrives from the host
// via the MCP Apps `ui/notifications/tool-result` handshake (App.ontoolresult).
// When the tool supplies a `view` bbox (a basin/country zoom), the map zooms to it.
import { App } from "@modelcontextprotocol/ext-apps";
import OUTLINE from "../assets/basemap_outline.json";
import BORDERS from "../assets/borders_outline.json";

const STATUS_COLORS = {
  producing: "#35c46b",
  "shut-in": "#93a6b8",
  drilling: "#3fa9ff",
  maintenance: "#ffb020",
};
const STATUS_LABELS = {
  producing: "Producing",
  "shut-in": "Shut-in",
  drilling: "Drilling",
  maintenance: "Maintenance",
};
const STATUS_ORDER = ["producing", "shut-in", "drilling", "maintenance"];

const svg = document.getElementById("map");
const subtitle = document.getElementById("subtitle");
const legendEl = document.getElementById("legend");
const emptyEl = document.getElementById("empty");
const popupEl = document.getElementById("popup");

let proj = null; // projection (from OUTLINE.bbox)
let full = null; // full viewBox {x,y,w,h}
let vb = null; // current viewBox {x,y,w,h}
let serverView = null; // last view bbox provided by the tool (for reset)
let wells = []; // last rendered wells
let hidden = new Set(); // statuses toggled off in the legend
let selectedId = null;
let app = null; // MCP Apps client (null in standalone test mode)
let layers = { warehouses: [], crews: [] }; // optional overlay data
let layerOn = { warehouses: false, crews: false }; // toggle state

// ---- Projection (equirectangular with latitude aspect correction) --------
function buildProjection(bbox) {
  const [minlon, minlat, maxlon, maxlat] = bbox;
  const midlat = (minlat + maxlat) / 2;
  const kx = Math.cos((midlat * Math.PI) / 180);
  return {
    W: (maxlon - minlon) * kx,
    H: maxlat - minlat,
    x: (lon) => (lon - minlon) * kx,
    y: (lat) => maxlat - lat,
  };
}

function clampView(v) {
  const w = Math.min(v.w, full.w);
  const h = Math.min(v.h, full.h);
  const x = Math.max(0, Math.min(v.x, full.w - w));
  const y = Math.max(0, Math.min(v.y, full.h - h));
  return { x, y, w, h };
}

function applyViewBox() {
  svg.setAttribute(
    "viewBox",
    `${vb.x.toFixed(3)} ${vb.y.toFixed(3)} ${vb.w.toFixed(3)} ${vb.h.toFixed(3)}`,
  );
  rescaleRadii();
}

function setView(v) {
  vb = clampView(v);
  applyViewBox();
}

function viewBoxFromLonLat(bbox, padFrac) {
  const [minlon, minlat, maxlon, maxlat] = bbox;
  const x0 = proj.x(minlon), x1 = proj.x(maxlon);
  const y0 = proj.y(maxlat), y1 = proj.y(minlat); // y flips
  let x = Math.min(x0, x1), y = Math.min(y0, y1);
  let w = Math.abs(x1 - x0), h = Math.abs(y1 - y0);
  const pad = padFrac == null ? 0.14 : padFrac;
  x -= w * pad; y -= h * pad; w *= 1 + 2 * pad; h *= 1 + 2 * pad;
  const minW = full.w * 0.01, minH = full.h * 0.01;
  if (w < minW) { x -= (minW - w) / 2; w = minW; }
  if (h < minH) { y -= (minH - h) / 2; h = minH; }
  return { x, y, w, h };
}

// Marker radius in current viewBox units so dots keep a stable on-screen size.
function currentRadius() {
  return Math.max(0.05, vb.w * 0.007);
}

function rescaleRadii() {
  const r = currentRadius();
  for (const c of svg.querySelectorAll("circle.well")) c.setAttribute("r", r.toFixed(3));
  for (const c of svg.querySelectorAll("circle.alertring"))
    c.setAttribute("r", (r * 1.9).toFixed(3));
  drawLayers();
}

// ---- Optional overlay layers (warehouses, crew bases) --------------------
function drawLayers() {
  if (!proj) return;
  const s = Math.max(0.08, currentRadius() * 1.7);
  const wg = svg.querySelector("#warehouses");
  if (wg) {
    wg.innerHTML = layerOn.warehouses
      ? layers.warehouses.map((w) => {
          const x = (proj.x(w.lon) - s / 2).toFixed(3);
          const y = (proj.y(w.lat) - s / 2).toFixed(3);
          return `<rect class="warehouse" data-code="${w.code}" x="${x}" y="${y}" `
            + `width="${s.toFixed(3)}" height="${s.toFixed(3)}" rx="${(s * 0.18).toFixed(3)}"/>`;
        }).join("")
      : "";
  }
  const cg = svg.querySelector("#crews");
  if (cg) {
    cg.innerHTML = layerOn.crews
      ? layers.crews.map((c) => {
          const cx = proj.x(c.lon), cy = proj.y(c.lat);
          const pts = `${cx.toFixed(3)},${(cy - s).toFixed(3)} `
            + `${(cx + s).toFixed(3)},${cy.toFixed(3)} `
            + `${cx.toFixed(3)},${(cy + s).toFixed(3)} `
            + `${(cx - s).toFixed(3)},${cy.toFixed(3)}`;
          return `<polygon class="crew" data-base="${c.base}" points="${pts}"/>`;
        }).join("")
      : "";
  }
}

// ---- Base map ------------------------------------------------------------
function drawBaseMap() {
  proj = buildProjection(OUTLINE.bbox);
  full = { x: 0, y: 0, w: proj.W, h: proj.H };
  vb = { ...full };
  applyViewBox();
  let paths = "";
  for (const flat of OUTLINE.rings) {
    let d = "";
    for (let i = 0; i < flat.length; i += 2) {
      d += (i === 0 ? "M" : "L") + proj.x(flat[i]).toFixed(3) + " " + proj.y(flat[i + 1]).toFixed(3);
    }
    paths += `<path class="land" d="${d}Z"/>`;
  }
  if (BORDERS && BORDERS.lines) {
    for (const flat of BORDERS.lines) {
      let d = "";
      for (let i = 0; i < flat.length; i += 2) {
        d += (i === 0 ? "M" : "L") + proj.x(flat[i]).toFixed(3) + " " + proj.y(flat[i + 1]).toFixed(3);
      }
      paths += `<path class="border" d="${d}"/>`;
    }
  }
  paths += `<g id="wells"></g><g id="warehouses"></g><g id="crews"></g>`;
  svg.insertAdjacentHTML("beforeend", paths);
}

// ---- Wells ---------------------------------------------------------------
function visibleWells() {
  return wells.filter((w) => !hidden.has(w.status));
}

function drawWells() {
  const g = svg.querySelector("#wells");
  if (!g) return;
  const r = currentRadius();
  let html = "";
  for (const w of visibleWells()) {
    const cx = proj.x(w.lon).toFixed(3);
    const cy = proj.y(w.lat).toFixed(3);
    const color = STATUS_COLORS[w.status] || "#cccccc";
    if (w.health === "critical") {
      html += `<circle class="alertring" cx="${cx}" cy="${cy}" r="${(r * 1.9).toFixed(3)}"/>`;
    }
    const sel = w.id === selectedId ? " sel" : "";
    html += `<circle class="well${sel}" data-id="${w.id}" cx="${cx}" cy="${cy}" `
      + `r="${r.toFixed(3)}" fill="${color}"/>`;
  }
  g.innerHTML = html;
  emptyEl.style.display = visibleWells().length ? "none" : "flex";
}

function fmt(n) {
  return n == null ? "—" : Number(n).toLocaleString("en-US");
}

function showPopup(w) {
  selectedId = w.id;
  const color = STATUS_COLORS[w.status] || "#ccc";
  const alerts = (w.alerts || []).map((a) => `<span class="chip">${a}</span>`).join("");
  const wc = w.wc == null ? "—" : `${w.wc} <small>%</small>`;
  popupEl.innerHTML = `
    <div class="phead">
      <span class="pdot" style="background:${color};color:${color}"></span>
      <span class="ptitle">${w.name} <span class="pid">· ${w.id}</span></span>
      <button class="pclose" aria-label="Close">×</button>
    </div>
    <div class="psub">${STATUS_LABELS[w.status] || w.status} · ${w.type_label || w.type}
      · ${w.offshore ? "offshore" : "onshore"}</div>
    <div class="kpis">
      <div class="kpi"><div class="val">${fmt(w.prod)} <small>bbl/d</small></div><div class="lbl">Production</div></div>
      <div class="kpi"><div class="val">${fmt(w.whp)} <small>psi</small></div><div class="lbl">Wellhead pressure</div></div>
      <div class="kpi"><div class="val">${wc}</div><div class="lbl">Water cut</div></div>
      <div class="kpi"><div class="val">${fmt(w.depth)} <small>m</small></div><div class="lbl">Depth</div></div>
    </div>
    <div class="kv">
      <span class="k">Basin</span><span class="v">${w.basin}</span>
      <span class="k">Country</span><span class="v">${w.country}</span>
      <span class="k">Operator</span><span class="v">${w.operator || "—"}</span>
    </div>
    ${alerts ? `<div class="alerts">${alerts}</div>` : ""}`;
  popupEl.classList.add("on");
  popupEl.querySelector(".pclose").addEventListener("click", closePopup);
  drawWells();
}

function showWarehousePopup(w) {
  selectedId = null;
  drawWells();
  popupEl.innerHTML = `
    <div class="phead">
      <span class="pdot" style="background:var(--maintenance);color:var(--maintenance)"></span>
      <span class="ptitle">${w.name} <span class="pid">· ${w.code}</span></span>
      <button class="pclose" aria-label="Close">×</button>
    </div>
    <div class="psub">Parts warehouse · ${w.region}</div>
    <div class="kpis">
      <div class="kpi"><div class="val">${fmt(w.total_units)}</div><div class="lbl">Units in stock</div></div>
      <div class="kpi"><div class="val">${fmt(w.distinct_parts)}</div><div class="lbl">Distinct parts</div></div>
      <div class="kpi"><div class="val">${fmt(w.out_of_stock_lines)}</div><div class="lbl">Out-of-stock lines</div></div>
    </div>`;
  popupEl.classList.add("on");
  popupEl.querySelector(".pclose").addEventListener("click", closePopup);
}

function showCrewPopup(c) {
  selectedId = null;
  drawWells();
  const now = c.earliest_in_days === 0;
  popupEl.innerHTML = `
    <div class="phead">
      <span class="pdot" style="background:#33c9c9;color:#33c9c9"></span>
      <span class="ptitle">${c.base} maintenance base</span>
      <button class="pclose" aria-label="Close">×</button>
    </div>
    <div class="psub">${c.country || ""}</div>
    <div class="kpis">
      <div class="kpi"><div class="val">${fmt(c.crew_count)}</div><div class="lbl">Crews</div></div>
      <div class="kpi"><div class="val">${fmt(c.available_now)}</div><div class="lbl">Available now</div></div>
    </div>
    <div class="kv">
      <span class="k">Earliest</span><span class="v ${now ? "ok" : ""}">${now ? "now" : c.earliest_date}</span>
      <span class="k">Specialties</span><span class="v">${(c.specialties || []).join(", ") || "—"}</span>
    </div>`;
  popupEl.classList.add("on");
  popupEl.querySelector(".pclose").addEventListener("click", closePopup);
}

function closePopup() {
  selectedId = null;
  popupEl.classList.remove("on");
  drawWells();
}

// ---- Legend (client-side status filter) ----------------------------------
function drawLegend(counts) {
  let html = "";
  for (const s of STATUS_ORDER) {
    const n = counts[s] || 0;
    const off = hidden.has(s) ? " off" : "";
    html += `<span class="item${off}" data-status="${s}">
      <span class="dot" style="background:${STATUS_COLORS[s]};color:${STATUS_COLORS[s]}"></span>
      ${STATUS_LABELS[s]} <span class="count">${n}</span></span>`;
  }
  legendEl.innerHTML = html;
  for (const el of legendEl.querySelectorAll(".item")) {
    el.addEventListener("click", () => {
      const s = el.getAttribute("data-status");
      if (hidden.has(s)) hidden.delete(s); else hidden.add(s);
      el.classList.toggle("off");
      if (selectedId && !visibleWells().some((w) => w.id === selectedId)) closePopup();
      drawWells();
    });
  }
}

// ---- Render entry point --------------------------------------------------
function renderWells(payload) {
  wells = (payload && payload.wells) || [];
  layers = (payload && payload.layers) || { warehouses: [], crews: [] };
  hidden = new Set();
  selectedId = null;
  popupEl.classList.remove("on");

  const counts = {};
  for (const w of wells) counts[w.status] = (counts[w.status] || 0) + 1;
  drawLegend(counts);

  const region = payload && payload.region_label;
  const alerts = (payload && payload.wells_with_alerts) || 0;
  const prod = (payload && payload.total_production_bbl_d) || 0;
  subtitle.textContent =
    `${wells.length} well${wells.length === 1 ? "" : "s"}`
    + (region ? ` in ${region}` : " worldwide")
    + ` · ${alerts} with alerts · ${prod.toLocaleString("en-US")} bbl/day`;

  serverView = (payload && payload.view) || null;
  if (serverView && serverView.length === 4) {
    setView(viewBoxFromLonLat(serverView));
  } else if (wells.length) {
    // Fit to the wells' own bounds when no explicit view was given.
    const bb = payload && payload.bbox;
    if (bb && bb.length === 4) setView(viewBoxFromLonLat(bb, 0.18));
    else setView({ ...full });
  } else {
    setView({ ...full });
  }
  drawWells();
  drawLayers();
  // Show layer toggles only when the server provided that layer's data.
  const whBtn = document.getElementById("togglewh");
  const crewBtn = document.getElementById("togglecrew");
  if (whBtn) whBtn.style.display = layers.warehouses.length ? "" : "none";
  if (crewBtn) crewBtn.style.display = layers.crews.length ? "" : "none";
}

// ---- Interactions: zoom + pan --------------------------------------------
function zoomAt(factor, cx, cy) {
  const w = vb.w * factor, h = vb.h * factor;
  const x = cx - (cx - vb.x) * factor;
  const y = cy - (cy - vb.y) * factor;
  setView({ x, y, w, h });
}

function svgPoint(evt) {
  const rect = svg.getBoundingClientRect();
  const px = (evt.clientX - rect.left) / rect.width;
  const py = (evt.clientY - rect.top) / rect.height;
  return { x: vb.x + px * vb.w, y: vb.y + py * vb.h };
}

function wireInteractions() {
  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const p = svgPoint(e);
    zoomAt(e.deltaY > 0 ? 1.15 : 1 / 1.15, p.x, p.y);
  }, { passive: false });

  function handleSelect(clientX, clientY) {
    // Robust hit-test independent of pointer-capture quirks: read the topmost
    // element at the release point. (Relying on the click event's target fails
    // in the Copilot iframe because pan uses setPointerCapture.)
    const t = document.elementFromPoint(clientX, clientY);
    if (t && t.classList && t.classList.contains("warehouse")) {
      const w = layers.warehouses.find((x) => x.code === t.getAttribute("data-code"));
      if (w) { showWarehousePopup(w); return; }
    }
    if (t && t.classList && t.classList.contains("crew")) {
      const c = layers.crews.find((x) => x.base === t.getAttribute("data-base"));
      if (c) { showCrewPopup(c); return; }
    }
    if (t && t.classList && t.classList.contains("well")) {
      const w = wells.find((x) => x.id === t.getAttribute("data-id"));
      if (w) { showPopup(w); return; }
    }
    closePopup();
  }

  let dragging = false, moved = false, captured = false, last = null, start = null;
  svg.addEventListener("pointerdown", (e) => {
    dragging = true; moved = false; captured = false;
    last = { x: e.clientX, y: e.clientY };
    start = { x: e.clientX, y: e.clientY };
    svg.classList.add("grabbing");
  });
  svg.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    if (!moved && Math.abs(e.clientX - start.x) + Math.abs(e.clientY - start.y) > 4) {
      moved = true;
      // Only capture the pointer once an actual drag begins, so a plain click
      // keeps its real target and pans never "stick".
      try { svg.setPointerCapture(e.pointerId); captured = true; } catch (_) { /* ignore */ }
    }
    if (!moved) { last = { x: e.clientX, y: e.clientY }; return; }
    const rect = svg.getBoundingClientRect();
    const dx = (e.clientX - last.x) / rect.width * vb.w;
    const dy = (e.clientY - last.y) / rect.height * vb.h;
    last = { x: e.clientX, y: e.clientY };
    setView({ x: vb.x - dx, y: vb.y - dy, w: vb.w, h: vb.h });
  });
  const endDrag = (e) => {
    if (!dragging) return;
    dragging = false; svg.classList.remove("grabbing");
    if (captured) { try { svg.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ } captured = false; }
    if (!moved) handleSelect(e.clientX, e.clientY);
  };
  svg.addEventListener("pointerup", endDrag);
  svg.addEventListener("pointercancel", () => {
    dragging = false; captured = false; svg.classList.remove("grabbing");
  });

  const whBtn = document.getElementById("togglewh");
  if (whBtn) whBtn.addEventListener("click", (e) => {
    layerOn.warehouses = !layerOn.warehouses;
    e.currentTarget.classList.toggle("active", layerOn.warehouses);
    drawLayers();
  });
  const crewBtn = document.getElementById("togglecrew");
  if (crewBtn) crewBtn.addEventListener("click", (e) => {
    layerOn.crews = !layerOn.crews;
    e.currentTarget.classList.toggle("active", layerOn.crews);
    drawLayers();
  });

  document.getElementById("zoomin").addEventListener("click",
    () => zoomAt(1 / 1.4, vb.x + vb.w / 2, vb.y + vb.h / 2));
  document.getElementById("zoomout").addEventListener("click",
    () => zoomAt(1.4, vb.x + vb.w / 2, vb.y + vb.h / 2));
  document.getElementById("reset").addEventListener("click", () => {
    if (serverView && serverView.length === 4) setView(viewBoxFromLonLat(serverView));
    else setView({ ...full });
  });
}

// ---- Theme ---------------------------------------------------------------
function applyTheme(ctx) {
  if (!ctx) return;
  const theme = ctx.theme || (ctx.hostContext && ctx.hostContext.theme);
  if (theme === "light") {
    document.documentElement.style.setProperty("--bg", "#f3f6fa");
    document.documentElement.style.setProperty("--text", "#12222f");
    document.documentElement.style.setProperty("--muted", "#5a6b7a");
    document.documentElement.style.setProperty("--sea", "#dbe7f1");
    document.documentElement.style.setProperty("--land", "#c9d6e2");
    document.documentElement.style.setProperty("--land-stroke", "#9fb3c6");
  }
}

// ---- Payload extraction (structuredContent or JSON text) -----------------
function extractPayload(params) {
  if (!params) return null;
  if (params.structuredContent) return params.structuredContent;
  const content = params.content;
  if (content && content.length) {
    for (const c of content) {
      if (c.type === "text") {
        try { return JSON.parse(c.text); } catch (e) { /* ignore */ }
      }
    }
  }
  return null;
}

// ---- Boot ----------------------------------------------------------------
drawBaseMap();
wireInteractions();

(async () => {
  app = new App(
    { name: "drilling-hotspots-view", version: "1.0.0" },
    {},
    { autoResize: true },
  );
  app.ontoolresult = (params) => {
    const payload = extractPayload(params);
    if (payload) renderWells(payload);
  };
  app.onhostcontextchanged = (ctx) => applyTheme(ctx);

  try {
    await app.connect();
    applyTheme(app.getHostContext());
  } catch (err) {
    console.error("[wells-widget] connect failed:", err);
    if (window.__WELLS_DATA__) renderWells(window.__WELLS_DATA__);
  }
})();
