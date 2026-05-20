"""
viz.py — offline graph viewer generator.

Writes a single HTML file with graph JSON embedded directly into the page. The
viewer has no CDN dependency, no sibling JSON fetch, and no upload step.
"""

from __future__ import annotations

import json
import sys
import webbrowser
from dataclasses import asdict
from pathlib import Path

from mygraph import Graph, resolve_graph_path

HERE = Path(__file__).parent
HTML_PATH = HERE / "mygraph_viz.html"


HTML_TEMPLATE = r"""<!doctype html>
<meta charset="utf-8" />
<title>mygraph viewer</title>
<style>
  :root {
    --bg: #101214;
    --fg: #edf0f2;
    --muted: #9ba3ad;
    --line: #2c333a;
    --panel: #191d22;
    --accent: #72d1b0;
    --warn: #e5c07b;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; width: 100%; height: 100%; overflow: hidden;
    background: var(--bg); color: var(--fg);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  header { height: 44px; display: flex; align-items: center; gap: 16px;
    padding: 0 14px; border-bottom: 1px solid var(--line); font-size: 13px; }
  header strong { color: var(--accent); }
  #counts, #hint { color: var(--muted); }
  #hint { margin-left: auto; }
  #stage { width: 100vw; height: calc(100vh - 44px); }
  svg { width: 100%; height: 100%; cursor: grab; user-select: none; }
  .link { stroke: #52606d; stroke-opacity: 0.5; stroke-width: 1.2; }
  .link.low { stroke-dasharray: 4 4; stroke-opacity: 0.35; }
  .link.medium { stroke-opacity: 0.42; }
  .edge-label { fill: var(--muted); font-size: 9px; pointer-events: none; }
  .node circle { stroke: #0a0c0e; stroke-width: 1.5; cursor: pointer; }
  .node text { fill: var(--fg); font-size: 10px; pointer-events: none;
    text-shadow: 0 1px 2px #000, 0 0 4px #000; }
  .node.selected circle { stroke: var(--accent); stroke-width: 3; }
  #panel { position: fixed; right: 12px; top: 56px; width: min(390px, calc(100vw - 24px));
    max-height: calc(100vh - 72px); overflow: auto; background: var(--panel);
    border: 1px solid var(--line); border-radius: 8px; padding: 14px; display: none;
    box-shadow: 0 18px 60px rgba(0,0,0,.35); font-size: 13px; line-height: 1.45; }
  #panel.open { display: block; }
  #panel h2 { margin: 0 26px 4px 0; font-size: 16px; color: var(--accent); }
  #panel code { color: var(--muted); }
  #panel .meta { color: var(--muted); font-size: 12px; }
  #panel .body { margin: 10px 0; }
  #panel .section-title { margin-top: 14px; color: var(--muted); font-size: 11px;
    text-transform: uppercase; letter-spacing: .08em; }
  #panel ul { margin: 6px 0 0 0; padding-left: 18px; }
  #panel li { margin-bottom: 5px; }
  #panel button { position: absolute; top: 10px; right: 10px; border: 0;
    background: transparent; color: var(--muted); font-size: 22px; cursor: pointer; }
  #panel a { color: #9cc9ff; cursor: pointer; text-decoration: none; }
  #panel a:hover { text-decoration: underline; }
  .pill { display: inline-block; margin-left: 4px; padding: 1px 6px;
    border-radius: 999px; background: #263039; color: var(--muted); font-size: 11px; }
  .pill.low { color: #ffb4a8; }
  .pill.medium { color: var(--warn); }
</style>
<header>
  <strong>mygraph</strong>
  <span id="counts"></span>
  <span id="hint">click nodes · drag canvas · scroll to zoom</span>
</header>
<div id="stage"><svg id="graph" viewBox="0 0 1200 760" aria-label="knowledge graph"></svg></div>
<aside id="panel"></aside>
<script>
const GRAPH_DATA = __GRAPH_JSON__;
const COLORS = {
  person: "#ef7d7d", topic: "#78aee8", idea: "#e3c56f", project: "#76d99d",
  goal: "#c18be8", question: "#f0a06d", decision: "#72d1b0",
  reference: "#dc83bd", source: "#9ba3ad"
};
const RADII = { source: 6, topic: 8, person: 9, project: 10, goal: 10,
  idea: 9, question: 8, decision: 8, reference: 8 };
const nodes = Object.values(GRAPH_DATA.nodes || {});
const edges = GRAPH_DATA.edges || [];
const nodeById = new Map(nodes.map(n => [n.id, n]));
const svg = document.getElementById("graph");
const panel = document.getElementById("panel");
document.getElementById("counts").textContent = `${nodes.length} nodes · ${edges.length} edges`;

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"]/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"
  }[c]));
}

function layout() {
  const groups = {};
  for (const node of nodes) (groups[node.type] ||= []).push(node);
  const typeOrder = Object.keys(groups).sort();
  const centerX = 600, centerY = 380;
  const ringGap = Math.max(76, Math.min(118, 440 / Math.max(1, typeOrder.length)));
  typeOrder.forEach((type, ringIndex) => {
    const ring = groups[type];
    const radius = 70 + ringIndex * ringGap;
    ring.forEach((node, i) => {
      const angle = (Math.PI * 2 * i / Math.max(1, ring.length)) + ringIndex * 0.45;
      node.x = centerX + Math.cos(angle) * radius;
      node.y = centerY + Math.sin(angle) * radius;
    });
  });
}

function make(tag, attrs = {}, parent = svg) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  parent.appendChild(el);
  return el;
}

function render() {
  layout();
  svg.innerHTML = "";
  const root = make("g", { id: "viewport" });
  for (const edge of edges) {
    const src = nodeById.get(edge.src), dst = nodeById.get(edge.dst);
    if (!src || !dst) continue;
    make("line", { class: `link ${edge.confidence || "medium"}`,
      x1: src.x, y1: src.y, x2: dst.x, y2: dst.y }, root);
    make("text", { class: "edge-label", x: (src.x + dst.x) / 2, y: (src.y + dst.y) / 2 }, root)
      .textContent = edge.type;
  }
  for (const node of nodes) {
    const g = make("g", { class: "node", transform: `translate(${node.x},${node.y})`,
      "data-id": node.id }, root);
    make("circle", { r: RADII[node.type] || 8, fill: COLORS[node.type] || "#aaa" }, g);
    make("text", { x: 13, y: 4 }, g).textContent = node.label || node.id;
    g.addEventListener("click", ev => { ev.stopPropagation(); openPanel(node.id); });
  }
  enablePanZoom(root);
}

function relatedEdges(id) {
  return edges.filter(e => e.src === id || e.dst === id);
}

function openPanel(id) {
  const node = nodeById.get(id);
  if (!node) return;
  document.querySelectorAll(".node").forEach(el => el.classList.toggle("selected", el.dataset.id === id));
  const rel = relatedEdges(id);
  const provenance = rel.filter(e => e.type === "MENTIONED_IN" || e.type === "MADE_AT");
  panel.classList.add("open");
  panel.innerHTML = `
    <button aria-label="Close">×</button>
    <h2>${escapeHtml(node.label || node.id)}</h2>
    <div class="meta">${escapeHtml(node.type)} · <code>${escapeHtml(node.id)}</code>
      <span class="pill ${escapeHtml(node.confidence || "")}">${escapeHtml(node.confidence || "?")}</span>
    </div>
    ${node.body ? `<div class="body">${escapeHtml(node.body)}</div>` : ""}
    ${provenance.length ? `<div class="section-title">provenance</div><ul>${provenance.map(e => {
      const other = e.src === id ? e.dst : e.src;
      return `<li><a data-id="${escapeHtml(other)}">${escapeHtml(other)}</a>${e.excerpt ? `<div class="meta">"${escapeHtml(e.excerpt)}"</div>` : ""}</li>`;
    }).join("")}</ul>` : ""}
    <div class="section-title">neighbors</div>
    <ul>${rel.map(e => {
      const other = e.src === id ? e.dst : e.src;
      const dir = e.src === id ? "to" : "from";
      return `<li>${escapeHtml(e.type)} ${dir} <a data-id="${escapeHtml(other)}">${escapeHtml(other)}</a></li>`;
    }).join("") || "<li>none</li>"}</ul>
  `;
  panel.querySelector("button").onclick = () => panel.classList.remove("open");
  panel.querySelectorAll("a[data-id]").forEach(a => a.onclick = () => openPanel(a.dataset.id));
}

function enablePanZoom(root) {
  let scale = 1, tx = 0, ty = 0, dragging = false, start = null;
  const apply = () => root.setAttribute("transform", `translate(${tx},${ty}) scale(${scale})`);
  svg.addEventListener("mousedown", ev => { dragging = true; start = [ev.clientX - tx, ev.clientY - ty]; });
  window.addEventListener("mouseup", () => dragging = false);
  window.addEventListener("mousemove", ev => {
    if (!dragging) return;
    tx = ev.clientX - start[0]; ty = ev.clientY - start[1]; apply();
  });
  svg.addEventListener("wheel", ev => {
    ev.preventDefault();
    const next = Math.max(0.35, Math.min(3.5, scale * (ev.deltaY < 0 ? 1.08 : 0.92)));
    scale = next; apply();
  }, { passive: false });
  svg.addEventListener("click", () => panel.classList.remove("open"));
}

render();
</script>
"""


def _graph_payload(graph_path: Path) -> dict:
    g = Graph.load(str(graph_path))
    return {
        "nodes": {nid: asdict(node) for nid, node in g.nodes.items()},
        "edges": [asdict(edge) for edge in g.edges],
    }


def render_html(graph_path: Path, out_path: Path = HTML_PATH) -> Path:
    payload = _graph_payload(graph_path)
    graph_json = json.dumps(payload, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__GRAPH_JSON__", graph_json.replace("</script", "<\\/script"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def _value_arg(args: list[str], name: str) -> str | None:
    if name not in args:
        return None
    i = args.index(name)
    if i + 1 >= len(args):
        raise SystemExit(f"viz: {name} needs a path")
    return args[i + 1]


def run_viz(args: list[str]) -> int:
    graph_arg = _value_arg(args, "--graph")
    out_arg = _value_arg(args, "--out")
    graph_path = Path(graph_arg).expanduser().resolve() if graph_arg else Path(resolve_graph_path())
    out = Path(out_arg).expanduser().resolve() if out_arg else HTML_PATH
    written = render_html(graph_path, out)
    print(f"viz: wrote {written}")
    if "--no-open" not in args:
        webbrowser.open(written.resolve().as_uri())
        print("viz: opened in default browser")
    return 0


if __name__ == "__main__":
    sys.exit(run_viz(sys.argv[1:]))
