"""
viz.py — graph viewer generator.

Writes a single HTML file with graph JSON embedded directly into the page. The
viewer uses D3.js from the CDN for force-directed layout, with no sibling JSON
fetch and no upload step.
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
<title>mygraph — visualizer</title>
<style>
  :root {
    --bg: #0f1115;
    --fg: #e6e8ea;
    --muted: #8a9099;
    --panel: #181b21;
    --accent: #d2b48c;
  }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg);
               font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
               overflow: hidden; }
  #header { padding: 8px 14px; border-bottom: 1px solid #222;
            display: flex; align-items: center; gap: 14px; font-size: 12px; }
  #header strong { color: var(--accent); letter-spacing: 0; }
  #header .legend { display: flex; gap: 10px; flex-wrap: wrap; }
  #header .legend span { display: inline-flex; align-items: center; gap: 4px; }
  #header .legend i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  #stage { width: 100vw; height: calc(100vh - 38px); }
  svg { width: 100%; height: 100%; cursor: grab; }
  .link { stroke: #3a3f47; stroke-opacity: 0.55; }
  .link.high { stroke-opacity: 0.9; }
  .link.medium { stroke-opacity: 0.6; }
  .link.low   { stroke-opacity: 0.3; stroke-dasharray: 3 3; }
  .node circle { stroke: #0f1115; stroke-width: 1.5; cursor: pointer; }
  .node text { fill: var(--fg); font-size: 10px; pointer-events: none;
               text-shadow: 0 0 3px #0f1115, 0 0 3px #0f1115, 0 0 3px #0f1115; }
  .edge-label { fill: var(--muted); font-size: 9px; pointer-events: none; }
  #sitrep { position: fixed; top: 50px; left: 12px; width: min(312px, calc(100vw - 24px));
            max-height: calc(100vh - 64px); overflow: auto; background: rgba(24, 27, 33, 0.88);
            border: 1px solid #2a2f37; border-radius: 6px; font-size: 12px;
            box-shadow: 0 12px 44px rgba(0,0,0,.24); }
  #sitrep .head { display: flex; align-items: center; justify-content: space-between;
                  gap: 10px; padding: 10px 12px; border-bottom: 1px solid #2a2f37; }
  #sitrep .title { color: var(--accent); font-weight: 700; text-transform: uppercase; }
  #sitrep .state { color: var(--muted); font-size: 10px; text-transform: uppercase; }
  #sitrep .metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
                     border-bottom: 1px solid #2a2f37; }
  #sitrep .metric { min-height: 56px; padding: 10px 12px; border-right: 1px solid #2a2f37;
                    border-bottom: 1px solid #2a2f37; }
  #sitrep .metric:nth-child(even) { border-right: 0; }
  #sitrep .metric:nth-last-child(-n+2) { border-bottom: 0; }
  #sitrep .value { color: var(--accent); font-size: 20px; line-height: 1; }
  #sitrep .label { margin-top: 6px; color: var(--muted); font-size: 10px; text-transform: uppercase; }
  #sitrep .block { padding: 11px 12px; border-top: 1px solid #2a2f37; }
  #sitrep .block:first-of-type { border-top: 0; }
  #sitrep .block-title { margin-bottom: 8px; color: var(--muted); font-size: 10px; text-transform: uppercase; }
  #sitrep .row { display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 7px 0;
                 border-top: 1px solid rgba(138, 144, 153, 0.16); color: var(--fg); }
  #sitrep .row:first-child { border-top: 0; }
  #sitrep button.row { width: 100%; border-right: 0; border-left: 0; border-bottom: 0;
                       background: transparent; text-align: left; cursor: pointer; font: inherit; }
  #sitrep button.row:hover { color: #fff; }
  #sitrep .row-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #sitrep .row-meta { color: var(--muted); font-size: 10px; text-transform: uppercase; }
  #sitrep .type-bars { display: grid; gap: 7px; }
  #sitrep .type-bar { display: grid; grid-template-columns: 72px 1fr 24px; gap: 8px; align-items: center; }
  #sitrep .type-name, #sitrep .type-count { color: var(--muted); font-size: 10px; text-transform: uppercase; }
  #sitrep .bar-track { height: 6px; background: rgba(138, 144, 153, 0.18); border-radius: 999px; overflow: hidden; }
  #sitrep .bar-fill { height: 100%; background: var(--accent); }
  #panel { position: fixed; top: 50px; right: 12px; width: 360px; max-height: 80vh;
           overflow: auto; background: var(--panel); border: 1px solid #2a2f37;
           border-radius: 6px; padding: 12px 14px; font-size: 12px; line-height: 1.45;
           display: none; }
  #panel.open { display: block; }
  #panel h3 { margin: 0 0 4px 0; color: var(--accent); font-size: 13px; }
  #panel .meta { color: var(--muted); font-size: 11px; }
  #panel .body { margin: 8px 0; }
  #panel .section { margin-top: 10px; }
  #panel .section-title { color: var(--muted); text-transform: uppercase;
                          letter-spacing: 0; font-size: 10px; margin-bottom: 4px; }
  #panel ul { margin: 0; padding-left: 16px; }
  #panel a { color: #87b7e0; text-decoration: none; cursor: pointer; }
  #panel a:hover { text-decoration: underline; }
  .pill { display: inline-block; padding: 0 6px; border-radius: 3px;
          background: #2a2f37; color: var(--muted); font-size: 10px; margin-left: 4px; }
  #close { float: right; cursor: pointer; color: var(--muted); }
  @media (max-width: 860px) {
    #sitrep { display: none; }
    #panel { left: 12px; right: 12px; width: auto; }
  }
</style>

<div id="header">
  <strong>mygraph</strong>
  <span id="counts">loading…</span>
  <span class="legend" id="legend"></span>
  <span style="margin-left:auto; color: var(--muted)">click a node · drag to pan · scroll to zoom</span>
</div>
<div id="stage"><svg aria-label="knowledge graph"></svg></div>
<aside id="sitrep" aria-label="graph sitrep"></aside>
<div id="panel"></div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const GRAPH_DATA = __GRAPH_JSON__;
const TYPE_COLORS = {
  person:    "#e07b7b",
  topic:     "#7bb0e0",
  idea:      "#d2b48c",
  project:   "#7be0a8",
  goal:      "#b07be0",
  question:  "#e0c87b",
  decision:  "#7be0c8",
  reference: "#e07bb0",
  source:    "#8a9099",
};
const TYPE_RADIUS = { source: 5, topic: 6, person: 8, project: 9, goal: 9,
                      idea: 8, question: 7, decision: 7, reference: 7 };

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"]/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"
  }[c]));
}

(function() {
  const data = GRAPH_DATA;
  const nodes = Object.values(data.nodes || {}).map(n => ({ ...n }));
  const originalEdges = data.edges || [];
  const edges = originalEdges.map(e => ({ ...e, source: e.src, target: e.dst }));
  const nodeById = new Map(nodes.map(n => [n.id, n]));
  document.getElementById("counts").textContent = `${nodes.length} nodes · ${edges.length} edges`;

  const legend = document.getElementById("legend");
  Object.keys(TYPE_COLORS).forEach(type => {
    const span = document.createElement("span");
    span.innerHTML = `<i style="background:${TYPE_COLORS[type]}"></i>${escapeHtml(type)}`;
    legend.appendChild(span);
  });
  renderSitrep();

  if (typeof d3 === "undefined") {
    document.getElementById("counts").textContent = "failed to load D3.js";
    return;
  }

  const svg = d3.select("svg");
  const viewport = svg.append("g");
  svg.call(d3.zoom()
    .scaleExtent([0.2, 4])
    .on("zoom", ev => viewport.attr("transform", ev.transform)));

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(edges).id(d => d.id).distance(80).strength(0.5))
    .force("charge", d3.forceManyBody().strength(-160))
    .force("center", d3.forceCenter(window.innerWidth / 2, (window.innerHeight - 38) / 2))
    .force("collide", d3.forceCollide().radius(d => (TYPE_RADIUS[d.type] || 7) + 4));

  const link = viewport.append("g").attr("class", "links").selectAll("line")
    .data(edges).join("line")
    .attr("class", d => `link ${d.confidence || "medium"}`);

  const edgeLabel = viewport.append("g").attr("class", "edge-labels").selectAll("text")
    .data(edges).join("text")
    .attr("class", "edge-label")
    .text(d => d.type);

  const node = viewport.append("g").attr("class", "nodes").selectAll("g.node")
    .data(nodes).join("g")
    .attr("class", "node")
    .call(drag(sim));

  node.append("circle")
    .attr("r", d => TYPE_RADIUS[d.type] || 7)
    .attr("fill", d => TYPE_COLORS[d.type] || "#888");
  node.append("text")
    .attr("dx", 11)
    .attr("dy", 3)
    .text(d => d.label || d.id);

  node.on("click", (ev, d) => {
    ev.stopPropagation();
    openPanel(d);
  });
  svg.on("click", () => document.getElementById("panel").classList.remove("open"));

  sim.on("tick", () => {
    link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    edgeLabel.attr("x", d => (d.source.x + d.target.x) / 2)
             .attr("y", d => (d.source.y + d.target.y) / 2);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });

  function drag(sim) {
    return d3.drag()
      .on("start", (ev, d) => {
        if (!ev.active) sim.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (ev, d) => {
        d.fx = ev.x;
        d.fy = ev.y;
      })
      .on("end", (ev, d) => {
        if (!ev.active) sim.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });
  }

  function countBy(items, keyFn) {
    const counts = new Map();
    items.forEach(item => {
      const key = keyFn(item) || "unknown";
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    return counts;
  }

  function shortLabel(value, max = 42) {
    const text = String(value || "");
    return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
  }

  function renderSitrep() {
    const sitrep = document.getElementById("sitrep");
    const typeCounts = countBy(nodes, n => n.type);
    const confidenceCounts = countBy(nodes, n => n.confidence);
    const highConfidence = confidenceCounts.get("high") || 0;
    const mentioned = new Set(originalEdges.filter(e => e.type === "MENTIONED_IN").map(e => e.src));
    const nonSource = nodes.filter(n => n.type !== "source").length;
    const provenance = nonSource ? Math.round((mentioned.size / nonSource) * 100) : 100;
    const degree = new Map(nodes.map(n => [n.id, { in: 0, out: 0, total: 0 }]));
    originalEdges.forEach(edge => {
      if (degree.has(edge.src)) {
        degree.get(edge.src).out += 1;
        degree.get(edge.src).total += 1;
      }
      if (degree.has(edge.dst)) {
        degree.get(edge.dst).in += 1;
        degree.get(edge.dst).total += 1;
      }
    });
    const topNodes = nodes
      .map(node => ({ node, degree: degree.get(node.id) || { total: 0 } }))
      .sort((a, b) => b.degree.total - a.degree.total || String(a.node.id).localeCompare(String(b.node.id)))
      .slice(0, 5);
    const latest = nodes
      .slice()
      .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))
      .slice(0, 4);
    const maxType = Math.max(1, ...typeCounts.values());
    const topTypes = Array.from(typeCounts.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 5);

    sitrep.innerHTML = `
      <div class="head">
        <div class="title">SITREP</div>
        <div class="state">embedded graph</div>
      </div>
      <div class="metrics">
        <div class="metric"><div class="value">${nodes.length}</div><div class="label">nodes</div></div>
        <div class="metric"><div class="value">${edges.length}</div><div class="label">edges</div></div>
        <div class="metric"><div class="value">${provenance}%</div><div class="label">provenance</div></div>
        <div class="metric"><div class="value">${highConfidence}</div><div class="label">high confidence</div></div>
      </div>
      <div class="block">
        <div class="block-title">Top Connected</div>
        ${topNodes.map(({ node, degree }) => `
          <button class="row" data-id="${escapeHtml(node.id)}">
            <span class="row-label">${escapeHtml(shortLabel(node.label || node.id))}</span>
            <span class="row-meta">${escapeHtml(node.type)} / ${degree.total}</span>
          </button>
        `).join("")}
      </div>
      <div class="block">
        <div class="block-title">Node Mix</div>
        <div class="type-bars">
          ${topTypes.map(([type, count]) => `
            <div class="type-bar">
              <span class="type-name">${escapeHtml(type)}</span>
              <span class="bar-track"><span class="bar-fill" style="width:${Math.round((count / maxType) * 100)}%"></span></span>
              <span class="type-count">${count}</span>
            </div>
          `).join("")}
        </div>
      </div>
      <div class="block">
        <div class="block-title">Latest Signal</div>
        ${latest.map(node => `
          <button class="row" data-id="${escapeHtml(node.id)}">
            <span class="row-label">${escapeHtml(shortLabel(node.label || node.id))}</span>
            <span class="row-meta">${escapeHtml(node.type)}</span>
          </button>
        `).join("")}
      </div>
    `;
    sitrep.querySelectorAll("[data-id]").forEach(el => {
      el.addEventListener("click", ev => {
        ev.stopPropagation();
        const node = nodeById.get(el.dataset.id);
        if (node) openPanel(node);
      });
    });
  }

  function openPanel(n) {
    const panel = document.getElementById("panel");
    const out = originalEdges.filter(e => e.src === n.id);
    const inc = originalEdges.filter(e => e.dst === n.id);
    const prov = originalEdges.filter(e =>
      (e.type === "MENTIONED_IN" || e.type === "MADE_AT") &&
      (e.src === n.id || e.dst === n.id));
    panel.classList.add("open");
    panel.innerHTML = `
      <span id="close">×</span>
      <h3>${escapeHtml(n.label || n.id)}</h3>
      <div class="meta">${escapeHtml(n.type)} · <code>${escapeHtml(n.id)}</code>
        <span class="pill">${escapeHtml(n.confidence || "?")}</span></div>
      ${n.body ? `<div class="body">${escapeHtml(n.body)}</div>` : ""}
      ${prov.length ? `<div class="section">
        <div class="section-title">provenance</div>
        <ul>${prov.map(e => {
          const sid = e.src === n.id ? e.dst : e.src;
          const ex = e.excerpt ? `<div class="meta">"${escapeHtml(e.excerpt)}"</div>` : "";
          return `<li><a data-id="${escapeHtml(sid)}">${escapeHtml(sid)}</a>${ex}</li>`;
        }).join("")}</ul></div>` : ""}
      ${out.length ? `<div class="section">
        <div class="section-title">outgoing (${out.length})</div>
        <ul>${out.map(e =>
          `<li>${escapeHtml(e.type)} → <a data-id="${escapeHtml(e.dst)}">${escapeHtml(e.dst)}</a></li>`).join("")}</ul></div>` : ""}
      ${inc.length ? `<div class="section">
        <div class="section-title">incoming (${inc.length})</div>
        <ul>${inc.map(e =>
          `<li><a data-id="${escapeHtml(e.src)}">${escapeHtml(e.src)}</a> → ${escapeHtml(e.type)}</li>`).join("")}</ul></div>` : ""}
    `;
    document.getElementById("close").onclick = () => panel.classList.remove("open");
    panel.querySelectorAll("a[data-id]").forEach(a => {
      a.onclick = () => {
        const target = nodeById.get(a.dataset.id);
        if (target) openPanel(target);
      };
    });
  }
})();

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
