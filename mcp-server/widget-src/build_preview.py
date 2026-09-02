"""Build a standalone preview of the wells map widget for local browser testing.

Fetches a real payload from the running server's /wells endpoint (or uses a
bundled sample), injects it as ``window.__WELLS_DATA__`` into a copy of the
built widget.html, and writes ``preview.html`` in this folder. Open it directly
in a browser to see the widget render with data (the MCP Apps connect() call
fails outside Copilot and the widget falls back to __WELLS_DATA__).

    python build_preview.py [--url http://localhost:8010/wells?area=all]
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIDGET = HERE.parent / "assets" / "widget.html"


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8010/wells")
    args = ap.parse_args()

    payload = fetch(args.url)
    html = WIDGET.read_text(encoding="utf-8")
    inject = (f"<script>window.__WELLS_DATA__ = "
              f"{json.dumps(payload)};</script>\n")
    # The built widget.html has already inlined the bundle, so inject the data
    # right before the module script so __WELLS_DATA__ exists when it runs.
    marker = '<script type="module">'
    html = html.replace(marker, inject + marker, 1)
    out = HERE / "preview.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({len(html)/1024:.0f} KB) with {payload.get('count')} wells")


if __name__ == "__main__":
    main()
