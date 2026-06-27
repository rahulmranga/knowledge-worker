"""
mygraph.py — personal knowledge graph (v0 schema, v1 ingest/check/export/viz).

Single-file core, stdlib-only. Read SPEC.md and DESIGN.md.

Usage:
    mykg seed                                             # populate fictional demo graph
    mykg summary                                          # stats overview
    mykg query "provenance"                               # search + neighbors + provenance
    mykg path goal:my-goal project:knowledge-worker
    mykg dump                                             # raw JSON
    mykg reset                                            # delete graph file

    mykg ingest <path/to/file.md>                         # v1 M1: 5-stage extractor pipeline
    mykg check [--provenance|--stale-edges|--pairs N|--source-candidates DIR]
    mykg export --ttl                                     # v1 M3: emit Turtle
    mykg context                                          # LLM-ready context snapshot
    mykg viz                                              # v1 M4: write offline HTML viewer
    mykg audit                                            # memory audit analytics + optional HTML
    mykg discover                                         # derived-edge proposals + second-order analytics
    mykg deep-dive <source.md> --out-dir <dir>            # pre-ingest reasoning workspace

Graph file: ./mygraph.json by default, or MYGRAPH_PATH=/absolute/path.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GRAPH_PATH = os.path.join(HERE, "mygraph.json")


def resolve_graph_path(path: Optional[str] = None) -> str:
    raw = path or os.environ.get("MYGRAPH_PATH") or DEFAULT_GRAPH_PATH
    return os.path.abspath(os.path.expanduser(raw))


GRAPH_PATH = resolve_graph_path()

# ---------- node + edge types -------------------------------------------------

NODE_TYPES = {
    "person", "topic", "idea", "project", "goal",
    "question", "decision", "reference", "source",
}

EDGE_TYPES = {
    "HAS_IDEA", "RELATES_TO", "SUPPORTED_BY", "CHALLENGES",
    "SERVES", "INVOLVES", "ABOUT", "MENTIONED_IN", "MADE_AT",
}

CONFIDENCE = {"high", "medium", "low"}


@dataclass
class Node:
    id: str
    type: str
    label: str
    body: str = ""
    confidence: str = "high"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Graph files are external input. The ingest validator keeps new extracted
    # nodes on the public schema, but loading must tolerate legacy/private types.


@dataclass
class Edge:
    src: str
    dst: str
    type: str
    source_id: str         # which Source node this edge was extracted from
    excerpt: str = ""      # literal quote if available
    confidence: str = "high"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------- store -------------------------------------------------------------

class Graph:
    def __init__(self, nodes: Optional[dict[str, Node]] = None,
                 edges: Optional[list[Edge]] = None):
        self.nodes: dict[str, Node] = nodes or {}
        self.edges: list[Edge] = edges or []

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Graph":
        path = resolve_graph_path(path)
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # forward-compat: drop unknown fields, default missing optional fields
        node_fields = {f.name for f in Node.__dataclass_fields__.values()}
        edge_fields = {f.name for f in Edge.__dataclass_fields__.values()}
        nodes = {
            nid: Node(**{k: v for k, v in n.items() if k in node_fields})
            for nid, n in data.get("nodes", {}).items()
        }
        edges = []
        for e in data.get("edges", []):
            kw = {k: v for k, v in e.items() if k in edge_fields}
            # back-compat: pre-v1 edges lack last_seen → seed with created_at
            if "last_seen" not in kw and "created_at" in kw:
                kw["last_seen"] = kw["created_at"]
            edges.append(Edge(**kw))
        return cls(nodes=nodes, edges=edges)

    def save(self, path: Optional[str] = None) -> None:
        path = resolve_graph_path(path)
        data = {
            "nodes": {nid: asdict(n) for nid, n in self.nodes.items()},
            "edges": [asdict(e) for e in self.edges],
        }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)

    # --- mutation -------------------------------------------------------------

    def add_node(self, node: Node) -> Node:
        # idempotent: same id overwrites label/body if they changed but keeps created_at
        if node.id in self.nodes:
            existing = self.nodes[node.id]
            existing.label = node.label
            existing.body = node.body or existing.body
            existing.confidence = node.confidence
            return existing
        self.nodes[node.id] = node
        return node

    def add_edge(self, edge: Edge) -> Edge:
        # idempotent: dedupe on (src, dst, type, source_id)
        for e in self.edges:
            if (e.src, e.dst, e.type, e.source_id) == (edge.src, edge.dst, edge.type, edge.source_id):
                return e
        # require both endpoints to exist
        if edge.src not in self.nodes:
            raise ValueError(f"edge src missing: {edge.src}")
        if edge.dst not in self.nodes:
            raise ValueError(f"edge dst missing: {edge.dst}")
        self.edges.append(edge)
        return edge

    # --- introspection --------------------------------------------------------

    def neighbors(self, node_id: str) -> list[tuple[Edge, Node, str]]:
        """Return (edge, other_node, direction) tuples for a given node."""
        out = []
        for e in self.edges:
            if e.src == node_id and e.dst in self.nodes:
                out.append((e, self.nodes[e.dst], "out"))
            elif e.dst == node_id and e.src in self.nodes:
                out.append((e, self.nodes[e.src], "in"))
        return out

    def search(self, needle: str) -> list[Node]:
        n = needle.lower().strip()
        hits = []
        for node in self.nodes.values():
            if (n in node.id.lower()
                or n in node.label.lower()
                or n in node.body.lower()):
                hits.append(node)
        return sorted(hits, key=lambda x: (x.type, x.label))

    def shortest_path(self, src_id: str, dst_id: str) -> Optional[list[str]]:
        """BFS over the undirected projection."""
        if src_id not in self.nodes or dst_id not in self.nodes:
            return None
        adj: dict[str, set[str]] = {nid: set() for nid in self.nodes}
        for e in self.edges:
            adj[e.src].add(e.dst)
            adj[e.dst].add(e.src)
        from collections import deque
        q = deque([(src_id, [src_id])])
        seen = {src_id}
        while q:
            cur, path = q.popleft()
            if cur == dst_id:
                return path
            for nxt in adj[cur]:
                if nxt in seen:
                    continue
                seen.add(nxt)
                q.append((nxt, path + [nxt]))
        return None

    def provenance(self, node_id: str) -> list[tuple[str, str]]:
        """Return [(source_id, excerpt)] for everything that ties this node back to a source."""
        out = []
        for e in self.edges:
            if (e.src == node_id and e.type == "MENTIONED_IN") or \
               (e.dst == node_id and e.type == "MENTIONED_IN"):
                source_id = e.dst if e.src == node_id else e.src
                out.append((source_id, e.excerpt))
            elif e.type == "MADE_AT" and e.src == node_id:
                out.append((e.dst, e.excerpt))
        return out


# ---------- helpers -----------------------------------------------------------

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def nid(type_: str, label: str) -> str:
    return f"{type_}:{slug(label)}"


def conf_tag(c: str) -> str:
    """Visual flag for non-high confidence. Empty for high (no clutter)."""
    if c == "high":
        return ""
    if c == "medium":
        return "  WARN medium (paraphrase)"
    if c == "low":
        return "  WARN LOW - UNVERIFIED"
    return f"  WARN {c}"


# ---------- seed --------------------------------------------------------------

def seed() -> Graph:
    """Write a fictional demo graph to the active graph path.

    The seed intentionally avoids private-owner facts so generated public
    examples can be committed safely. It spans three fictional work eras
    (a hardware build, a newsletter, and the knowledge-worker toolkit) with
    fixed timestamps, so audit/discover output over the demo graph is
    deterministic and shows multiple communities, bridge ideas, stale
    memories, and low-confidence candidate edges.
    """
    g = Graph()

    # Three eras: (created_at, last_seen). Era 1 is old enough to go stale.
    ERA1 = ("2026-03-08T10:00:00+00:00", "2026-03-30T10:00:00+00:00")
    ERA2 = ("2026-05-02T10:00:00+00:00", "2026-05-12T10:00:00+00:00")
    ERA3 = ("2026-05-28T10:00:00+00:00", "2026-06-08T10:00:00+00:00")

    def node(id: str, type_: str, label: str, body: str,
             era: tuple[str, str] = ERA3, confidence: str = "high") -> None:
        g.add_node(Node(id=id, type=type_, label=label, body=body,
                        confidence=confidence, created_at=era[0]))

    # --- era 3: knowledge-worker (the original demo core, unchanged ids) ---
    node("source:demo-notes", "source", "demo-notes.md",
         "Fictional project notes used to demonstrate provenance-backed memory.")
    node("source:architecture-note", "source", "architecture-note.md",
         "Fictional architecture note for the public demo graph.")
    node("person:demo-owner", "person", "Demo Owner",
         "A fictional graph owner used only for public examples.")
    node("project:knowledge-worker", "project", "knowledge-worker",
         "A local-first toolkit for source-backed AI memory.")
    node("idea:context-memory", "idea", "Context memory",
         "AI sessions improve when durable context is stored as concepts instead of loose transcript chunks.")
    node("idea:provenance-first", "idea", "Provenance first",
         "Every durable claim should point back to source evidence.")
    node("idea:scoped-exports", "idea", "Scoped exports",
         "Share a task-sized slice of the graph with an AI, never the whole thing.")
    node("idea:promotion-queue", "idea", "Promotion queue",
         "AI proposes candidate memories; a human review queue decides what is promoted.")
    node("idea:single-owner-tools", "idea", "Single-owner tools",
         "Tools built for exactly one user can cut every scope corner that team software cannot.")
    node("goal:trusted-ai-assistance", "goal", "Trusted AI assistance",
         "Make assistant responses easier to verify and continue across sessions.")
    node("question:storage-backend", "question", "When should storage move beyond JSON?",
         "Open question: keep JSON until size or concurrency makes it awkward.")
    node("question:when-to-automate-ingest", "question", "When should ingest become automatic?",
         "Open question: manual review catches errors, but does not scale past a few notes a week.")
    node("decision:json-first", "decision", "Use JSON first",
         "Start with a simple JSON store before introducing a database.")
    node("decision:markdown-sources", "decision", "Ingest Markdown sources only",
         "Markdown keeps source notes diffable and human-reviewable.")
    node("decision:public-demo-data-only", "decision", "Only fictional data in public examples",
         "The public repo ships fictional demo data; real graphs stay local.")
    node("topic:knowledge-graphs", "topic", "Knowledge graphs",
         "Structured concepts and relationships for durable context.")
    node("topic:local-first", "topic", "Local-first software",
         "Software that keeps user data local unless the owner chooses otherwise.")
    node("topic:provenance", "topic", "Provenance",
         "Where a claim came from and whether it can be traced to evidence.")
    node("reference:coggrag", "reference", "CogGRAG",
         "A public reference about cognition-inspired graph retrieval.", confidence="medium")
    node("reference:graphrag-survey", "reference", "GraphRAG survey",
         "A survey of graph-based retrieval-augmented generation systems.", confidence="medium")
    node("reference:local-first-paper", "reference", "Local-first software paper",
         "The essay defining local-first software principles.")

    # --- era 1: garden-sensors (an older fictional hardware build) ---------
    node("source:greenhouse-journal", "source", "greenhouse-journal.md",
         "Fictional build journal for a small greenhouse sensor project.", ERA1)
    node("source:hardware-retro", "source", "hardware-retro.md",
         "Fictional retrospective on the greenhouse sensor hardware.", ERA1)
    node("project:garden-sensors", "project", "garden-sensors",
         "A fictional ESP32 sensor network for a backyard greenhouse.", ERA1)
    node("goal:automated-greenhouse", "goal", "Automated greenhouse",
         "Keep greenhouse plants alive with minimal manual checking.", ERA1)
    node("idea:drip-irrigation-loop", "idea", "Drip irrigation loop",
         "Close the loop: soil moisture readings drive the drip valve directly.", ERA1)
    node("idea:low-power-mesh", "idea", "Low-power sensor mesh",
         "Deep-sleep ESP32 nodes could run a mesh for months on small batteries.", ERA1)
    node("idea:sensor-data-as-memory", "idea", "Sensor data as memory",
         "Sensor logs are provenance too: a reading is a source excerpt about the world.", ERA1)
    node("decision:esp32-over-rpi", "decision", "Use ESP32 boards instead of a Raspberry Pi",
         "Microcontrollers beat a full computer for battery-powered sensing.", ERA1)
    node("decision:solar-power-budget", "decision", "Size the solar panel to winter output",
         "Plan the power budget around the worst month, not the average.", ERA1, confidence="medium")
    node("question:battery-life-winter", "question", "Will batteries survive winter?",
         "Open question: cold halves battery capacity; the mesh may not last the season.", ERA1)
    node("topic:embedded-systems", "topic", "Embedded systems",
         "Small computers with hard power and memory constraints.", ERA1)
    node("topic:sensor-networks", "topic", "Sensor networks",
         "Many small devices reporting measurements over a shared protocol.", ERA1)
    node("reference:esp32-deep-sleep-guide", "reference", "ESP32 deep-sleep guide",
         "A public guide to microcontroller deep-sleep power budgets.", ERA1)

    # --- era 2: field-notes (a fictional newsletter about the projects) ----
    node("source:newsletter-plan", "source", "newsletter-plan.md",
         "Fictional planning note for a monthly build-log newsletter.", ERA2)
    node("source:quarterly-review", "source", "quarterly-review.md",
         "Fictional quarterly review of all side projects.", ERA2)
    node("project:field-notes", "project", "field-notes",
         "A fictional monthly newsletter documenting the owner's builds.", ERA2)
    node("goal:publish-monthly", "goal", "Publish monthly",
         "Ship one newsletter issue every month without heroics.", ERA2)
    node("goal:sustainable-side-projects", "goal", "Sustainable side projects",
         "Keep hobby projects fun and finished instead of abandoned.", ERA2)
    node("idea:write-what-you-build", "idea", "Write what you build",
         "Each project becomes newsletter material; writing pressure improves the build.", ERA2)
    node("idea:show-the-graph", "idea", "Show the graph",
         "Publish the project knowledge graph itself as the newsletter artifact.", ERA2)
    node("idea:weekly-shipping-log", "idea", "Weekly shipping log",
         "A small weekly log makes the monthly issue almost write itself.", ERA2)
    node("idea:boring-tech-default", "idea", "Boring tech by default",
         "Choose boring technology unless the project IS the experiment.", ERA2)
    node("decision:monthly-cadence", "decision", "Commit to a monthly cadence",
         "Monthly is slow enough to sustain and fast enough to matter.", ERA2)
    node("decision:plain-text-newsletter", "decision", "Plain-text newsletter format",
         "No templates, no images: plain text ships on time.", ERA2)
    node("decision:one-project-per-quarter", "decision", "One active project per quarter",
         "Serialize side projects instead of running them in parallel.", ERA2)
    node("question:audience-growth", "question", "Does the newsletter need an audience?",
         "Open question: writing for zero readers may not stay motivating.", ERA2)
    node("topic:technical-writing", "topic", "Technical writing",
         "Explaining systems in prose, for readers and future self.", ERA2)
    node("reference:digital-garden-essay", "reference", "Digital garden essay",
         "A public essay on publishing evolving notes instead of finished posts.",
         ERA2, confidence="medium")

    def edge(src: str, dst: str, type_: str, source_id: str,
             excerpt: str = "", confidence: str = "high",
             era: tuple[str, str] = ERA3) -> None:
        g.add_edge(Edge(src=src, dst=dst, type=type_, source_id=source_id,
                        excerpt=excerpt, confidence=confidence,
                        created_at=era[0], last_seen=era[1]))

    src_demo = "source:demo-notes"
    src_arch = "source:architecture-note"
    src_journal = "source:greenhouse-journal"
    src_retro = "source:hardware-retro"
    src_plan = "source:newsletter-plan"
    src_review = "source:quarterly-review"

    # --- provenance: every non-source node is MENTIONED_IN a source --------
    for node_id, excerpt in [
        ("person:demo-owner", "The demo owner wants assistant memory that survives across sessions."),
        ("project:knowledge-worker", "Build a local-first toolkit for source-backed AI memory."),
        ("idea:context-memory", "Store durable concepts instead of loose transcript chunks."),
        ("idea:provenance-first", "Every durable claim needs source evidence."),
        ("idea:scoped-exports", "Export a task-sized slice, never the whole graph."),
        ("idea:single-owner-tools", "Software for one user can cut every corner."),
        ("goal:trusted-ai-assistance", "Make assistant responses easier to verify and continue."),
        ("decision:public-demo-data-only", "Only fictional data ships in public examples."),
        ("topic:knowledge-graphs", "Use a graph of concepts and relationships."),
        ("topic:local-first", "Keep owner data local unless explicitly exported."),
        ("reference:local-first-paper", "The local-first paper defines the storage principles."),
    ]:
        edge(node_id, src_demo, "MENTIONED_IN", src_demo, excerpt)

    for node_id, excerpt in [
        ("question:storage-backend", "When should storage move beyond JSON?"),
        ("question:when-to-automate-ingest", "Manual review is the bottleneck; when does ingest become automatic?"),
        ("decision:json-first", "Use JSON first; add a database only when needed."),
        ("decision:markdown-sources", "Ingest Markdown only; it stays diffable and reviewable."),
        ("idea:promotion-queue", "Candidates wait in a review queue until the owner promotes them."),
        ("topic:provenance", "Track where every claim came from."),
        ("reference:coggrag", "CogGRAG is a public reference for graph retrieval."),
        ("reference:graphrag-survey", "The GraphRAG survey maps the retrieval landscape."),
        ("idea:sensor-data-as-memory", "Sensor readings could enter the graph as provenance-backed observations."),
    ]:
        edge(node_id, src_arch, "MENTIONED_IN", src_arch, excerpt)

    for node_id, excerpt in [
        ("project:garden-sensors", "Garden sensors: a small ESP32 build for the greenhouse."),
        ("goal:automated-greenhouse", "The greenhouse should mostly look after itself."),
        ("idea:drip-irrigation-loop", "Let soil moisture drive the drip valve directly."),
        ("idea:sensor-data-as-memory", "A sensor log line is an excerpt about the world."),
        ("decision:solar-power-budget", "Size the panel for December, not for June."),
        ("topic:sensor-networks", "A handful of nodes reporting over one protocol."),
        ("topic:provenance", "Sensor logs are evidence: timestamped, source-attributed readings."),
    ]:
        edge(node_id, src_journal, "MENTIONED_IN", src_journal, excerpt, era=ERA1)

    for node_id, excerpt in [
        ("idea:low-power-mesh", "Deep-sleep nodes might run for months on small cells."),
        ("decision:esp32-over-rpi", "The Pi drew too much power; ESP32 boards won."),
        ("question:battery-life-winter", "Cold weather halves capacity; winter is the real test."),
        ("topic:embedded-systems", "Hard power budgets change every design choice."),
        ("reference:esp32-deep-sleep-guide", "The deep-sleep guide documents real-world power draw."),
    ]:
        edge(node_id, src_retro, "MENTIONED_IN", src_retro, excerpt, era=ERA1)

    for node_id, excerpt in [
        ("project:field-notes", "Field notes: a monthly build-log newsletter."),
        ("project:garden-sensors", "The greenhouse build is the first newsletter arc."),
        ("goal:publish-monthly", "One issue a month, no heroics."),
        ("idea:write-what-you-build", "Every project doubles as newsletter material."),
        ("idea:show-the-graph", "Publish the knowledge graph as the artifact."),
        ("idea:weekly-shipping-log", "A weekly log makes the monthly issue write itself."),
        ("decision:monthly-cadence", "Monthly is sustainable; weekly was not."),
        ("decision:plain-text-newsletter", "Plain text ships on time."),
        ("topic:technical-writing", "Writing about systems clarifies them."),
        ("reference:digital-garden-essay", "The digital-garden essay argues for evolving notes."),
    ]:
        edge(node_id, src_plan, "MENTIONED_IN", src_plan, excerpt, era=ERA2)

    for node_id, excerpt in [
        ("goal:sustainable-side-projects", "Projects should end finished, not abandoned."),
        ("idea:write-what-you-build", "Writing pressure kept the sensor build honest."),
        ("idea:boring-tech-default", "Boring tech unless the project is the experiment."),
        ("decision:one-project-per-quarter", "Serialize projects; parallel ones all stall."),
        ("project:garden-sensors", "The sensor project consumed the whole quarter."),
        ("question:audience-growth", "Is writing for zero readers sustainable?"),
    ]:
        edge(node_id, src_review, "MENTIONED_IN", src_review, excerpt, era=ERA2)

    # --- semantic edges: era 3 (knowledge-worker) ---------------------------
    edge("person:demo-owner", "idea:context-memory", "HAS_IDEA", src_demo)
    edge("person:demo-owner", "idea:provenance-first", "HAS_IDEA", src_demo)
    edge("project:knowledge-worker", "goal:trusted-ai-assistance", "SERVES", src_demo)
    edge("project:knowledge-worker", "topic:knowledge-graphs", "INVOLVES", src_demo)
    edge("project:knowledge-worker", "topic:local-first", "INVOLVES", src_demo)
    edge("idea:context-memory", "topic:knowledge-graphs", "RELATES_TO", src_demo)
    edge("idea:provenance-first", "goal:trusted-ai-assistance", "SERVES", src_demo)
    edge("decision:json-first", "question:storage-backend", "ABOUT", src_arch)
    edge("idea:context-memory", "reference:coggrag", "SUPPORTED_BY", src_arch,
         excerpt="CogGRAG is a public reference for graph retrieval.", confidence="medium")
    edge("idea:scoped-exports", "topic:local-first", "RELATES_TO", src_demo)
    edge("idea:scoped-exports", "goal:trusted-ai-assistance", "SERVES", src_demo)
    edge("idea:scoped-exports", "reference:local-first-paper", "SUPPORTED_BY", src_demo)
    edge("idea:promotion-queue", "topic:provenance", "RELATES_TO", src_arch)
    edge("idea:promotion-queue", "reference:graphrag-survey", "SUPPORTED_BY", src_arch,
         confidence="medium")
    edge("idea:single-owner-tools", "topic:local-first", "RELATES_TO", src_demo)
    edge("idea:provenance-first", "topic:provenance", "RELATES_TO", src_arch)
    edge("decision:markdown-sources", "topic:provenance", "ABOUT", src_arch)
    edge("decision:public-demo-data-only", "goal:trusted-ai-assistance", "SERVES", src_demo)
    edge("decision:public-demo-data-only", "topic:local-first", "RELATES_TO", src_demo)

    # --- semantic edges: era 1 (garden-sensors) -----------------------------
    edge("project:garden-sensors", "goal:automated-greenhouse", "SERVES", src_journal, era=ERA1)
    edge("project:garden-sensors", "topic:embedded-systems", "INVOLVES", src_retro, era=ERA1)
    edge("project:garden-sensors", "topic:sensor-networks", "INVOLVES", src_journal, era=ERA1)
    edge("person:demo-owner", "idea:drip-irrigation-loop", "HAS_IDEA", src_journal, era=ERA1)
    edge("idea:drip-irrigation-loop", "goal:automated-greenhouse", "SERVES", src_journal, era=ERA1)
    edge("idea:low-power-mesh", "topic:sensor-networks", "RELATES_TO", src_retro,
         confidence="low", era=ERA1)
    edge("idea:low-power-mesh", "reference:esp32-deep-sleep-guide", "SUPPORTED_BY",
         src_retro, excerpt="The deep-sleep guide documents real-world power draw.", era=ERA1)
    edge("question:battery-life-winter", "idea:low-power-mesh", "CHALLENGES", src_retro, era=ERA1)
    edge("decision:esp32-over-rpi", "topic:embedded-systems", "ABOUT", src_retro, era=ERA1)
    edge("decision:solar-power-budget", "goal:automated-greenhouse", "SERVES", src_journal,
         confidence="medium", era=ERA1)
    # bridge: the hardware project reaches into the memory toolkit's domain
    edge("idea:sensor-data-as-memory", "topic:knowledge-graphs", "RELATES_TO", src_arch)
    edge("idea:sensor-data-as-memory", "topic:sensor-networks", "RELATES_TO", src_journal, era=ERA1)

    # --- semantic edges: era 2 (field-notes) --------------------------------
    edge("project:field-notes", "goal:publish-monthly", "SERVES", src_plan, era=ERA2)
    edge("project:field-notes", "topic:technical-writing", "INVOLVES", src_plan, era=ERA2)
    edge("person:demo-owner", "idea:write-what-you-build", "HAS_IDEA", src_plan, era=ERA2)
    edge("idea:weekly-shipping-log", "goal:publish-monthly", "SERVES", src_plan, era=ERA2)
    edge("idea:weekly-shipping-log", "topic:technical-writing", "RELATES_TO", src_plan, era=ERA2)
    edge("idea:show-the-graph", "reference:digital-garden-essay", "SUPPORTED_BY",
         src_plan, confidence="low", era=ERA2)
    # bridge: the newsletter idea reaches into the memory toolkit's domain
    edge("idea:show-the-graph", "topic:knowledge-graphs", "RELATES_TO", src_plan, era=ERA2)
    edge("idea:boring-tech-default", "goal:sustainable-side-projects", "SERVES", src_review, era=ERA2)
    edge("decision:monthly-cadence", "goal:publish-monthly", "SERVES", src_plan, era=ERA2)
    edge("decision:plain-text-newsletter", "topic:technical-writing", "ABOUT", src_plan, era=ERA2)
    edge("decision:one-project-per-quarter", "goal:sustainable-side-projects", "SERVES",
         src_review, era=ERA2)
    edge("question:audience-growth", "goal:publish-monthly", "CHALLENGES", src_review, era=ERA2)

    g.save()
    return g


# ---------- summary / query ---------------------------------------------------

def summary() -> None:
    g = Graph.load()
    by_type: dict[str, int] = {}
    for n in g.nodes.values():
        by_type[n.type] = by_type.get(n.type, 0) + 1
    edge_by_type: dict[str, int] = {}
    for e in g.edges:
        edge_by_type[e.type] = edge_by_type.get(e.type, 0) + 1

    print(f"mygraph - {resolve_graph_path()}")
    print(f"  {len(g.nodes)} nodes, {len(g.edges)} edges")
    print()
    print("  Nodes by type:")
    for t in sorted(by_type):
        print(f"    {t:<12} {by_type[t]}")
    print()
    print("  Edges by type:")
    for t in sorted(edge_by_type):
        print(f"    {t:<14} {edge_by_type[t]}")


def query(needle: str) -> None:
    g = Graph.load()
    hits = g.search(needle)
    if not hits:
        print(f"No nodes match '{needle}'.")
        return

    # Surface non-high confidence summary at the top
    non_high = [n for n in hits if n.confidence != "high"]
    if non_high:
        print(f"WARN {len(non_high)} of {len(hits)} matched node(s) are NOT high-confidence - see flags below.")
    print(f"Matches for '{needle}':\n")

    for node in hits:
        # Prominent confidence flag on the header line
        print(f"  [{node.type}] {node.id}{conf_tag(node.confidence)}")
        print(f"    label: {node.label}")
        if node.body:
            print(f"    body : {node.body}")
        # Edges, with confidence flag for non-high edges
        nbrs = g.neighbors(node.id)
        if nbrs:
            print(f"    edges:")
            for e, other, direction in nbrs:
                arrow = "->" if direction == "out" else "<-"
                ex = f"  // \"{e.excerpt}\"" if e.excerpt else ""
                edge_flag = conf_tag(e.confidence)
                target_flag = conf_tag(other.confidence)
                print(f"      {arrow} {e.type:<13} {other.id}{target_flag}{ex}{edge_flag}")
        # Provenance
        prov = g.provenance(node.id)
        if prov:
            print(f"    provenance:")
            for source_id, ex in prov:
                tag = f' "{ex}"' if ex else ""
                print(f"      <- {source_id}{tag}")
        # If the node is non-high, repeat the warning at the end too.
        if node.confidence != "high":
            print(f"    WARN Treat content as confidence={node.confidence}; do not quote as verbatim source.")
        print()


def path(a: str, b: str) -> None:
    g = Graph.load()
    p = g.shortest_path(a, b)
    if not p:
        print(f"No path between {a} and {b}.")
        return
    print(f"Path from {a} to {b}:")
    for node_id in p:
        n = g.nodes[node_id]
        print(f"  [{n.type}] {n.label}  ({n.id})")


def dump() -> None:
    with open(resolve_graph_path(), encoding="utf-8") as f:
        print(f.read())


def reset() -> None:
    path = resolve_graph_path()
    if os.path.exists(path):
        os.remove(path)
        print(f"Deleted {path}")
    else:
        print("No graph file to delete.")


def list_nodes(type_: str) -> None:
    """Return ALL nodes of a given type, so type listings are always complete
    (search-style retrieval can silently miss members of a category)."""
    # Accept plural ("decisions" → "decision")
    t = type_.lower().rstrip("s")
    g = Graph.load()
    matches = [n for n in g.nodes.values() if n.type == t]
    if not matches:
        if t not in NODE_TYPES:
            observed = sorted(NODE_TYPES | {n.type for n in g.nodes.values()})
            print(f"No nodes of type '{t}'. Known/observed: {', '.join(observed)}")
            return
        print(f"No nodes of type '{t}'.")
        return
    non_high = [n for n in matches if n.confidence != "high"]
    if non_high:
        print(f"WARN {len(non_high)} of {len(matches)} are NOT high-confidence.")
    print(f"All {t}s ({len(matches)}):\n")
    for n in sorted(matches, key=lambda x: x.label):
        print(f"  [{n.type}] {n.id}{conf_tag(n.confidence)}")
        print(f"    {n.label}")
        if n.body:
            body = n.body if len(n.body) < 200 else n.body[:200] + "..."
            print(f"    {body}")
        print()


def state(entry: str) -> None:
    """Append a manual mood/state entry to state_log.jsonl. Sidecar — does NOT
    touch the main graph (per SPEC §5 sidecar track)."""
    log = os.path.join(HERE, "state_log.jsonl")
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "entry": entry,
    }
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print(f"Logged state -> {log}")
    print(f"  {record['ts']}: {entry}")


# ---------- CLI ---------------------------------------------------------------

USAGE = """\
Usage:
  mykg seed
  mykg summary
  mykg query <string>
  mykg list <type>           # all nodes of a type (decision, goal, idea, ...)
  mykg path <node_id> <node_id>
  mykg state "<entry>"       # append mood/state to state_log.jsonl (sidecar)
  mykg dump
  mykg reset
  mykg ingest <path/to/file.md> [--non-interactive] [--auto-accept-high]
                                [--candidates-file <path>]
                                [--backend claude|openai|ollama] [--model <name>]
  mykg check [--provenance] [--stale-edges] [--pairs N]
             [--source-candidates <dir>]
  mykg export --ttl [--out <path>]
  mykg context [--out <path>] [--max-ideas N]
  mykg viz [--graph <path>] [--out <path>] [--no-open]
  mykg audit [--graph <path>] [--out analytics.json] [--html memory_audit.html]
  mykg discover [--graph <path>] [--out discovery.json]
               [--candidates <path>] [--limit N] [--stale-days N]
  mykg deep-dive <source.md> --out-dir <workspace>
  mykg deep-dive inspect <workspace>
  mykg deep-dive add-to-graph <workspace>
"""


def main(argv: Optional[list[str]] = None) -> int:
    argv = sys.argv if argv is None else argv
    if len(argv) < 2:
        print(USAGE)
        return 1
    cmd = argv[1]
    if cmd in {"-h", "--help", "help"}:
        print(USAGE)
        return 0
    if cmd == "seed":
        g = seed()
        print(f"Seeded. {len(g.nodes)} nodes, {len(g.edges)} edges -> {resolve_graph_path()}")
        return 0
    if cmd == "summary":
        summary()
        return 0
    if cmd == "query":
        if len(argv) < 3:
            print("Need a query string.")
            return 1
        query(" ".join(argv[2:]))
        return 0
    if cmd == "path":
        if len(argv) < 4:
            print("Need two node ids.")
            return 1
        path(argv[2], argv[3])
        return 0
    if cmd == "dump":
        dump()
        return 0
    if cmd == "reset":
        reset()
        return 0
    if cmd == "list":
        if len(argv) < 3:
            print("Need a node type. Valid: " + ", ".join(sorted(NODE_TYPES)))
            return 1
        list_nodes(argv[2])
        return 0
    if cmd == "state":
        if len(argv) < 3:
            print("Need a state entry. Example: mykg state \"focused, 10:30am, coffee\"")
            return 1
        state(" ".join(argv[2:]))
        return 0
    if cmd == "ingest":
        if __package__:
            from .ingest import run_ingest
        else:
            from ingest import run_ingest
        return run_ingest(argv[2:])
    if cmd == "check":
        if __package__:
            from .check import run_check
        else:
            from check import run_check
        return run_check(argv[2:])
    if cmd == "export":
        if __package__:
            from .owl_io import run_export
        else:
            from owl_io import run_export
        return run_export(argv[2:])
    if cmd in {"context", "export_context"}:
        if __package__:
            from .export_context import run_export_context
        else:
            from export_context import run_export_context
        return run_export_context(argv[2:])
    if cmd == "viz":
        if __package__:
            from .viz import run_viz
        else:
            from viz import run_viz
        return run_viz(argv[2:])
    if cmd == "audit":
        if __package__:
            from .memory_audit import run_audit
        else:
            from memory_audit import run_audit
        return run_audit(argv[2:])
    if cmd == "discover":
        if __package__:
            from .discover import run_discover
        else:
            from discover import run_discover
        return run_discover(argv[2:])
    if cmd == "deep-dive":
        if __package__:
            from .deep_dive import run_deep_dive
        else:
            from deep_dive import run_deep_dive
        return run_deep_dive(argv[2:])
    print(USAGE)
    return 1


def cli() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        return main(sys.argv)
    except BrokenPipeError:
        # Piped output closed early (e.g. `mykg query x | head`); exit quietly.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(cli())
