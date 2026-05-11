"""
viz.py — v1 M4 visualization launcher.

Writes a fresh `mygraph_viz.html` next to this script and opens it in the
default browser. The HTML is a single self-contained file (D3.js from CDN) that
fetches `mygraph.json` over file://.

Why custom HTML over WebVOWL/Gephi:
  - zero install
  - reads canonical JSON directly (no dependency on M3 TTL)
  - portable, version-controllable, customizable
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).parent
HTML_PATH = HERE / "mygraph_viz.html"
GRAPH_JSON = HERE / "mygraph.json"

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
  #header strong { color: var(--accent); letter-spacing: 0.04em; }
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
                          letter-spacing: 0.08em; font-size: 10px; margin-bottom: 4px; }
  #panel ul { margin: 0; padding-left: 16px; }
  #panel a { color: #87b7e0; text-decoration: none; cursor: pointer; }
  #panel a:hover { text-decoration: underline; }
  .pill { display: inline-block; padding: 0 6px; border-radius: 3px;
          background: #2a2f37; color: var(--muted); font-size: 10px; margin-left: 4px; }
  #close { float: right; cursor: pointer; color: var(--muted); }
</style>

<div id="header">
  <strong>mygraph</strong>
  <span id="counts">loading…</span>
  <span class="legend" id="legend"></span>
  <span style="margin-left:auto; color: var(--muted)">click a node · drag to pan · scroll to zoom</span>
</div>
<div id="stage"><svg></svg></div>
<div id="panel"></div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
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

(async function() {
  const res = await fetch("mygraph.json");
  if (!res.ok) {
    document.getElementById("counts").textContent = "failed to load mygraph.json";
    return;
  }
  const data = await res.json();
  const nodes = Object.values(data.nodes).map(n => ({...n}));
  const edges = data.edges.map(e => ({...e, source: e.src, target: e.dst}));
  document.getElementById("counts").textContent = `${nodes.length} nodes · ${edges.length} edges`;

  // legend
  const legend = document.getElementById("legend");
  Object.keys(TYPE_COLORS).forEach(t => {
    const span = document.createElement("span");
    span.innerHTML = `<i style="background:${TYPE_COLORS[t]}"></i>${t}`;
    legend.appendChild(span);
  });

  const svg = d3.select("svg");
  const g = svg.append("g");
  svg.call(d3.zoom().scaleExtent([0.2, 4]).on("zoom", ev => g.attr("transform", ev.transform)));

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(edges).id(d => d.id).distance(80).strength(0.5))
    .force("charge", d3.forceManyBody().strength(-160))
    .force("center", d3.forceCenter(window.innerWidth/2, (window.innerHeight-38)/2))
    .force("collide", d3.forceCollide().radius(d => (TYPE_RADIUS[d.type]||7) + 4));

  const link = g.append("g").attr("class","links").selectAll("line")
    .data(edges).join("line")
    .attr("class", d => `link ${d.confidence||"medium"}`);

  const edgeLabel = g.append("g").attr("class","edge-labels").selectAll("text")
    .data(edges).join("text").attr("class","edge-label").text(d => d.type);

  const node = g.append("g").attr("class","nodes").selectAll("g.node")
    .data(nodes).join("g").attr("class","node")
    .call(drag(sim));

  node.append("circle")
    .attr("r", d => TYPE_RADIUS[d.type] || 7)
    .attr("fill", d => TYPE_COLORS[d.type] || "#888");
  node.append("text")
    .attr("dx", 11).attr("dy", 3)
    .text(d => d.label);

  node.on("click", (ev, d) => openPanel(d, data));

  sim.on("tick", () => {
    link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
        .attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
    edgeLabel.attr("x",d=>(d.source.x+d.target.x)/2)
             .attr("y",d=>(d.source.y+d.target.y)/2);
    node.attr("transform", d=>`translate(${d.x},${d.y})`);
  });

  function drag(sim) {
    return d3.drag()
      .on("start",(ev,d)=>{ if(!ev.active) sim.alphaTarget(0.3).restart();
                            d.fx=d.x; d.fy=d.y; })
      .on("drag",(ev,d)=>{ d.fx=ev.x; d.fy=ev.y; })
      .on("end",(ev,d)=>{ if(!ev.active) sim.alphaTarget(0);
                          d.fx=null; d.fy=null; });
  }

  function openPanel(n, data) {
    const panel = document.getElementById("panel");
    const out = data.edges.filter(e => e.src === n.id);
    const inc = data.edges.filter(e => e.dst === n.id);
    const prov = data.edges.filter(e =>
      (e.type === "MENTIONED_IN" || e.type === "MADE_AT") &&
      (e.src === n.id || e.dst === n.id));
    panel.classList.add("open");
    panel.innerHTML = `
      <span id="close">×</span>
      <h3>${escape(n.label)}</h3>
      <div class="meta">${n.type} · <code>${n.id}</code>
        <span class="pill">${n.confidence||"?"}</span></div>
      ${n.body ? `<div class="body">${escape(n.body)}</div>` : ""}
      ${prov.length ? `<div class="section">
        <div class="section-title">provenance</div>
        <ul>${prov.map(e => {
          const sid = e.src === n.id ? e.dst : e.src;
          const ex = e.excerpt ? `<div class="meta">"${escape(e.excerpt)}"</div>` : "";
          return `<li><a data-id="${sid}">${sid}</a>${ex}</li>`;
        }).join("")}</ul></div>` : ""}
      ${out.length ? `<div class="section">
        <div class="section-title">outgoing (${out.length})</div>
        <ul>${out.map(e =>
          `<li>${e.type} → <a data-id="${e.dst}">${e.dst}</a></li>`).join("")}</ul></div>` : ""}
      ${inc.length ? `<div class="section">
        <div class="section-title">incoming (${inc.length})</div>
        <ul>${inc.map(e =>
          `<li><a data-id="${e.src}">${e.src}</a> → ${e.type}</li>`).join("")}</ul></div>` : ""}
    `;
    document.getElementById("close").onclick = () => panel.classList.remove("open");
    panel.querySelectorAll("a[data-id]").forEach(a => {
      a.onclick = () => {
        const target = nodes.find(x => x.id === a.dataset.id);
        if (target) openPanel(target, data);
      };
    });
  }
  function escape(s){ return String(s||"").replace(/[&<>]/g,
    c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
})();
</script>
"""


def render_html(out_path: Path = HTML_PATH) -> Path:
    out_path.write_text(HTML_TEMPLATE)
    return out_path


def run_viz(args: list[str]) -> int:
    out = render_html()
    print(f"viz: wrote {out}")
    if "--no-open" not in args:
        try:
            webbrowser.open(f"file://{out.resolve()}")
            print("viz: opened in default browser")
        except Exception as e:
            print(f"viz: could not auto-open ({e}). Open this file manually: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(run_viz(sys.argv[1:]))
