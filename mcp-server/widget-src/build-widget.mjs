// Bundles the widget View (main.js + ext-apps client + base-map outline) into a
// single self-contained HTML file at ../assets/widget.html, inlining the JS so
// the widget needs no network access (required by Copilot's sandbox CSP).
import { build } from "esbuild";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));

const result = await build({
  entryPoints: [join(HERE, "main.js")],
  bundle: true,
  format: "esm",
  minify: true,
  loader: { ".json": "json" },
  write: false,
  logLevel: "info",
  target: ["es2020"],
});

const js = result.outputFiles[0].text.replace(/<\/script/gi, "<\\/script");
const shell = readFileSync(join(HERE, "shell.html"), "utf-8");
const html = shell.replace("<!--BUNDLE-->", () => `<script type="module">\n${js}\n</script>`);

const out = join(HERE, "..", "assets", "widget.html");
writeFileSync(out, html, "utf-8");
console.log(`Wrote ${out} (${(html.length / 1024).toFixed(1)} KB)`);
