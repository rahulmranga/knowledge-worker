"""
mygraph.py — personal knowledge graph (v0 schema, v1 ingest/check/export/viz).

Single-file core, stdlib-only. Read SPEC.md → V1_DESIGN.md → V1_PLAN.md.

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
    resolved = os.path.abspath(os.path.expanduser(raw))
    if os.path.isdir(resolved):
        resolved = os.path.join(resolved, "mygraph.json")
    return resolved


GRAPH_PATH = resolve_graph_path()

# ---------- node + edge types -------------------------------------------------

NODE_TYPES = {
    "person", "topic", "idea", "project", "goal",
    "question", "decision", "reference", "source",
}

EDGE_TYPES = {
    "HAS_IDEA", "RELATES_TO", "SUPPORTED_BY", "CHALLENGES",
    "SERVES", "INVOLVES", "ABOUT", "ENABLED_BY", "MENTIONED_IN", "MADE_AT",
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
        with open(path) as f:
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
        with open(path, "w") as f:
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
        return "  ⚠ medium (paraphrase)"
    if c == "low":
        return "  ⚠ LOW — UNVERIFIED"
    return f"  ⚠ {c}"


# ---------- seed --------------------------------------------------------------

def seed() -> Graph:
    """Write the fictional launch demo graph to the active graph path.

    The seed intentionally avoids private-owner facts so generated public
    examples can be committed safely.
    """
    g = Graph()
    demo_time = "2026-06-09T12:00:00+00:00"

    def node(id_: str, type_: str, label: str, body: str,
             confidence: str = "high") -> Node:
        return Node(
            id=id_,
            type=type_,
            label=label,
            body=body,
            confidence=confidence,
            created_at=demo_time,
        )

    nodes = [
        node("source:product-brief", "source", "product-brief.md",
             "Fictional brief for reviewable, provenance-backed memory."),
        node("source:research-notes", "source", "research-notes.md",
             "Fictional research notes connecting evidence, typed relationships, and retrieval."),
        node("source:privacy-review", "source", "privacy-review.md",
             "Fictional privacy review for local storage and scoped context sharing."),
        node("source:user-interviews", "source", "user-interviews.md",
             "Fictional interview synthesis about continuity across AI sessions. Candidate: evidence-backed packs may improve handoffs."),
        node("source:architecture-note", "source", "architecture-note.md",
             "Fictional architecture note for JSON storage, RDF export, and typed graph structure. Candidate: local storage may support reviewable research."),
        node("source:launch-plan", "source", "launch-plan.md",
             "Fictional public-alpha plan centered on ranked memory audit output. Candidate: typed relationships may clarify privacy boundaries."),
        node("person:demo-owner", "person", "Demo Owner",
             "A fictional graph owner used only for public examples."),
        node("project:memory-workbench", "project", "Memory Workbench",
             "A local toolkit for reviewed, source-backed AI memory."),
        node("project:research-assistant", "project", "Research Assistant",
             "A fictional assistant that keeps claims connected to evidence."),
        node("project:launch-demo", "project", "Public Launch Demo",
             "A public-safe demonstration of memory governance workflows."),
        node("goal:trusted-ai-assistance", "goal", "Trusted AI assistance",
             "Make assistant responses easier to verify and continue across sessions."),
        node("goal:private-context-sharing", "goal", "Private context sharing",
             "Share only the bounded context needed for a task."),
        node("goal:evidence-backed-research", "goal", "Evidence-backed research",
             "Keep research claims connected to supporting and challenging evidence."),
        node("goal:public-alpha", "goal", "Public alpha",
             "Publish a useful, fictional demonstration without exposing private memory."),
        node("decision:json-first", "decision", "Use JSON first",
             "Start with a transparent JSON graph before adding database infrastructure."),
        node("decision:review-before-merge", "decision", "Review before merge",
             "Human approval is required before proposed memory becomes durable."),
        node("decision:provenance-required", "decision", "Require provenance",
             "Every durable claim needs a source identifier and literal excerpt."),
        node("decision:scoped-exports", "decision", "Export scoped context",
             "Share bounded context packs instead of the full graph."),
        node("decision:ranked-audit-first", "decision", "Ranked audit before graph canvas",
             "Lead with important concepts, bridges, weak claims, and proof trails."),
        node("decision:local-default", "decision", "Keep private memory local",
             "Private graph data stays local unless the owner explicitly exports a slice."),
        node("decision:defer-sql", "decision", "Defer SQL storage",
             "Move beyond JSON only when graph size or concurrency requires it."),
        node("decision:fictional-demo-only", "decision", "Use fictional demo data",
             "The public repository must demonstrate behavior without private facts."),
        node("idea:context-memory", "idea", "Context memory",
             "Durable concepts preserve continuity better than loose transcript chunks."),
        node("idea:provenance-first", "idea", "Provenance first",
             "Every durable claim should point back to source evidence."),
        node("idea:human-promotion-loop", "idea", "Human promotion loop",
             "AI proposes memory changes and a person decides what becomes durable."),
        node("idea:memory-audit", "idea", "Memory Audit",
             "Ranked graph analytics make important, bridging, and weak memory inspectable."),
        node("idea:context-packs", "idea", "Context packs",
             "Export only the cited graph slice needed by another AI tool."),
        node("idea:local-first-storage", "idea", "Local-first storage",
             "Keep the canonical graph in files controlled by the owner."),
        node("idea:typed-relationships", "idea", "Typed relationships",
             "Named edges preserve why concepts are connected."),
        node("idea:evidence-backfill", "idea", "Evidence backfill",
             "Central claims should accumulate supporting or challenging evidence over time."),
        node("idea:privacy-boundary", "idea", "Explicit privacy boundary",
             "Public infrastructure and private memory should remain separate."),
        node("idea:reviewable-research", "idea", "Reviewable research memory",
             "Research synthesis should retain claims, sources, and uncertainty."),
        node("idea:audited-context-bridge", "idea", "Audited context bridge",
             "Memory Audit should identify the safest, most relevant concepts for context export."),
        node("idea:evidence-governance-bridge", "idea", "Evidence governance bridge",
             "Evidence quality should influence which memories are promoted and reused."),
        node("reference:coggrag", "reference", "CogGRAG",
             "A public reference about cognition-inspired graph retrieval.", confidence="medium"),
        node("reference:hipporag", "reference", "HippoRAG",
             "A public reference about associative graph memory for language models.", confidence="medium"),
        node("reference:rdf", "reference", "RDF 1.1 Concepts",
             "A public standard for representing graph statements."),
        node("reference:local-first", "reference", "Local-first software",
             "A public reference for software that prioritizes local data ownership."),
        node("reference:pagerank", "reference", "PageRank",
             "A public reference for ranking nodes using graph link structure."),
        node("topic:knowledge-graphs", "topic", "Knowledge graphs",
             "Structured concepts and typed relationships."),
        node("topic:local-first", "topic", "Local-first software",
             "Software that keeps user data under local control."),
        node("topic:provenance", "topic", "Provenance",
             "Traceability from durable claims back to source excerpts."),
        node("topic:research-workflow", "topic", "Research workflow",
             "Processes for collecting, testing, and revising evidence."),
        node("topic:graph-analytics", "topic", "Graph analytics",
             "Network measures for importance, bridges, communities, and weak claims."),
        node("topic:context-governance", "topic", "Context governance",
             "Rules for deciding what memory another tool should receive."),
        node("question:storage-backend", "question", "When should storage move beyond JSON?",
             "Keep JSON until size or concurrency makes a database necessary."),
        node("question:launch-signal", "question", "What proves the public demo is useful?",
             "Measure substantive conversations and repository interest after launch."),
    ]
    for node in nodes:
        g.add_node(node)

    def edge(src: str, dst: str, type_: str, source_id: str,
             excerpt: str = "", confidence: str = "high") -> None:
        g.add_edge(Edge(
            src=src,
            dst=dst,
            type=type_,
            source_id=source_id,
            excerpt=excerpt,
            confidence=confidence,
            created_at=demo_time,
            last_seen=demo_time,
        ))

    provenance = {
        "person:demo-owner": ("source:product-brief", "The fictional demo owner wants memory that can be reviewed before reuse."),
        "project:memory-workbench": ("source:product-brief", "Build a local workbench for reviewed, source-backed memory."),
        "project:research-assistant": ("source:research-notes", "The research assistant should keep claims connected to evidence."),
        "project:launch-demo": ("source:launch-plan", "Publish a public-safe demonstration using fictional graph data."),
        "goal:trusted-ai-assistance": ("source:user-interviews", "People want AI sessions to continue without losing the reasoning behind prior work."),
        "goal:private-context-sharing": ("source:privacy-review", "Share only the bounded context needed for the current task."),
        "goal:evidence-backed-research": ("source:research-notes", "Research claims should remain connected to supporting and challenging evidence."),
        "goal:public-alpha": ("source:launch-plan", "Ship a useful public alpha without exposing private memory."),
        "decision:json-first": ("source:architecture-note", "Use JSON first; add a database only when size or concurrency requires it."),
        "decision:review-before-merge": ("source:product-brief", "A person reviews proposed memory before it becomes durable."),
        "decision:provenance-required": ("source:product-brief", "Every durable claim requires a source identifier and literal excerpt."),
        "decision:scoped-exports": ("source:privacy-review", "Export a bounded context slice instead of the whole private graph."),
        "decision:ranked-audit-first": ("source:launch-plan", "Lead the demo with ranked audit panels before the graph canvas."),
        "decision:local-default": ("source:privacy-review", "Keep private graph data local unless the owner explicitly exports it."),
        "decision:defer-sql": ("source:architecture-note", "Defer SQL storage until JSON becomes the limiting factor."),
        "decision:fictional-demo-only": ("source:launch-plan", "Use fictional data for every committed public demo artifact."),
        "idea:context-memory": ("source:user-interviews", "Durable concepts preserve continuity better than loose transcript chunks."),
        "idea:provenance-first": ("source:product-brief", "Every durable claim needs source evidence."),
        "idea:human-promotion-loop": ("source:product-brief", "AI proposes memory changes and a person decides what becomes durable."),
        "idea:memory-audit": ("source:launch-plan", "Rank important concepts, bridge ideas, weak claims, and proof trails."),
        "idea:context-packs": ("source:privacy-review", "Export only the cited graph slice needed by another AI tool."),
        "idea:local-first-storage": ("source:privacy-review", "Keep the canonical graph in files controlled by the owner."),
        "idea:typed-relationships": ("source:research-notes", "Named edges preserve why research concepts are connected."),
        "idea:evidence-backfill": ("source:research-notes", "Central claims should accumulate supporting or challenging evidence over time."),
        "idea:privacy-boundary": ("source:privacy-review", "Public infrastructure and private memory must remain separate."),
        "idea:reviewable-research": ("source:research-notes", "Research synthesis should retain claims, sources, and uncertainty."),
        "idea:audited-context-bridge": ("source:product-brief", "Use Memory Audit to identify safe, relevant concepts for context export."),
        "idea:evidence-governance-bridge": ("source:research-notes", "Evidence quality should influence which memories are promoted and reused."),
        "reference:coggrag": ("source:research-notes", "CogGRAG is a public reference for cognition-inspired graph retrieval."),
        "reference:hipporag": ("source:research-notes", "HippoRAG is a public reference for associative graph memory."),
        "reference:rdf": ("source:architecture-note", "RDF 1.1 defines a standard model for graph statements."),
        "reference:local-first": ("source:privacy-review", "Local-first software prioritizes local data ownership."),
        "reference:pagerank": ("source:launch-plan", "PageRank ranks nodes using graph link structure."),
        "topic:knowledge-graphs": ("source:architecture-note", "Use structured concepts and typed relationships."),
        "topic:local-first": ("source:privacy-review", "Keep user data under local control."),
        "topic:provenance": ("source:product-brief", "Trace durable claims back to source excerpts."),
        "topic:research-workflow": ("source:research-notes", "Collect, test, and revise evidence over time."),
        "topic:graph-analytics": ("source:launch-plan", "Use network measures for importance, bridges, communities, and weak claims."),
        "topic:context-governance": ("source:privacy-review", "Decide what memory another tool should receive."),
        "question:storage-backend": ("source:architecture-note", "When should storage move beyond JSON?"),
        "question:launch-signal": ("source:launch-plan", "What proves the public demo is useful?"),
    }
    for node_id, (source_id, excerpt) in provenance.items():
        edge(node_id, source_id, "MENTIONED_IN", source_id, excerpt)

    semantic_edges = [
        ("person:demo-owner", "idea:context-memory", "HAS_IDEA", "source:user-interviews"),
        ("person:demo-owner", "idea:provenance-first", "HAS_IDEA", "source:product-brief"),
        ("person:demo-owner", "idea:memory-audit", "HAS_IDEA", "source:launch-plan"),
        ("person:demo-owner", "idea:context-packs", "HAS_IDEA", "source:privacy-review"),
        ("project:memory-workbench", "goal:trusted-ai-assistance", "SERVES", "source:product-brief"),
        ("project:memory-workbench", "goal:private-context-sharing", "SERVES", "source:privacy-review"),
        ("project:research-assistant", "goal:evidence-backed-research", "SERVES", "source:research-notes"),
        ("project:launch-demo", "goal:public-alpha", "SERVES", "source:launch-plan"),
        ("project:memory-workbench", "topic:provenance", "INVOLVES", "source:product-brief"),
        ("project:memory-workbench", "topic:context-governance", "INVOLVES", "source:privacy-review"),
        ("project:research-assistant", "topic:research-workflow", "INVOLVES", "source:research-notes"),
        ("project:launch-demo", "topic:graph-analytics", "INVOLVES", "source:launch-plan"),
        ("idea:context-memory", "topic:knowledge-graphs", "RELATES_TO", "source:user-interviews"),
        ("idea:provenance-first", "topic:provenance", "RELATES_TO", "source:product-brief"),
        ("idea:human-promotion-loop", "topic:provenance", "RELATES_TO", "source:product-brief"),
        ("idea:memory-audit", "topic:graph-analytics", "RELATES_TO", "source:launch-plan"),
        ("idea:context-packs", "topic:context-governance", "RELATES_TO", "source:privacy-review"),
        ("idea:local-first-storage", "topic:local-first", "RELATES_TO", "source:privacy-review"),
        ("idea:typed-relationships", "topic:knowledge-graphs", "RELATES_TO", "source:research-notes"),
        ("idea:evidence-backfill", "topic:research-workflow", "RELATES_TO", "source:research-notes"),
        ("idea:privacy-boundary", "topic:context-governance", "RELATES_TO", "source:privacy-review"),
        ("idea:reviewable-research", "topic:research-workflow", "RELATES_TO", "source:research-notes"),
        ("idea:provenance-first", "goal:trusted-ai-assistance", "SERVES", "source:product-brief"),
        ("goal:trusted-ai-assistance", "idea:provenance-first", "ENABLED_BY", "source:product-brief"),
        ("idea:human-promotion-loop", "goal:trusted-ai-assistance", "SERVES", "source:product-brief"),
        ("goal:trusted-ai-assistance", "idea:human-promotion-loop", "ENABLED_BY", "source:product-brief"),
        ("idea:context-packs", "goal:private-context-sharing", "SERVES", "source:privacy-review"),
        ("goal:private-context-sharing", "idea:context-packs", "ENABLED_BY", "source:privacy-review"),
        ("idea:evidence-backfill", "goal:evidence-backed-research", "SERVES", "source:research-notes"),
        ("goal:evidence-backed-research", "idea:evidence-backfill", "ENABLED_BY", "source:research-notes"),
        ("idea:memory-audit", "goal:public-alpha", "SERVES", "source:launch-plan"),
        ("goal:public-alpha", "idea:memory-audit", "ENABLED_BY", "source:launch-plan"),
        ("decision:review-before-merge", "idea:human-promotion-loop", "ENABLED_BY", "source:product-brief"),
        ("decision:provenance-required", "idea:provenance-first", "ENABLED_BY", "source:product-brief"),
        ("decision:scoped-exports", "idea:context-packs", "ENABLED_BY", "source:privacy-review"),
        ("decision:ranked-audit-first", "idea:memory-audit", "ENABLED_BY", "source:launch-plan"),
        ("decision:local-default", "idea:local-first-storage", "ENABLED_BY", "source:privacy-review"),
        ("decision:json-first", "idea:local-first-storage", "ENABLED_BY", "source:architecture-note"),
        ("decision:defer-sql", "idea:local-first-storage", "ENABLED_BY", "source:architecture-note"),
        ("decision:fictional-demo-only", "idea:privacy-boundary", "ENABLED_BY", "source:launch-plan"),
        ("decision:json-first", "question:storage-backend", "ABOUT", "source:architecture-note"),
        ("decision:ranked-audit-first", "question:launch-signal", "ABOUT", "source:launch-plan"),
        ("idea:typed-relationships", "reference:coggrag", "SUPPORTED_BY", "source:research-notes"),
        ("idea:typed-relationships", "reference:hipporag", "SUPPORTED_BY", "source:research-notes"),
        ("idea:local-first-storage", "reference:local-first", "SUPPORTED_BY", "source:privacy-review"),
        ("idea:memory-audit", "reference:pagerank", "SUPPORTED_BY", "source:launch-plan"),
        ("idea:provenance-first", "reference:rdf", "RELATES_TO", "source:architecture-note"),
        ("idea:audited-context-bridge", "idea:memory-audit", "RELATES_TO", "source:product-brief"),
        ("idea:audited-context-bridge", "idea:context-packs", "RELATES_TO", "source:product-brief"),
        ("idea:audited-context-bridge", "goal:private-context-sharing", "SERVES", "source:product-brief"),
        ("idea:evidence-governance-bridge", "idea:evidence-backfill", "RELATES_TO", "source:research-notes"),
        ("idea:evidence-governance-bridge", "idea:provenance-first", "RELATES_TO", "source:research-notes"),
        ("idea:evidence-governance-bridge", "goal:evidence-backed-research", "SERVES", "source:research-notes"),
    ]
    for src, dst, type_, source_id in semantic_edges:
        edge(src, dst, type_, source_id)

    edge(
        "idea:evidence-backfill",
        "idea:context-packs",
        "RELATES_TO",
        "source:user-interviews",
        "Candidate: evidence-backed packs may improve handoffs.",
        "low",
    )
    edge(
        "idea:local-first-storage",
        "idea:reviewable-research",
        "RELATES_TO",
        "source:architecture-note",
        "Candidate: local storage may support reviewable research.",
        "low",
    )
    edge(
        "idea:typed-relationships",
        "idea:privacy-boundary",
        "RELATES_TO",
        "source:launch-plan",
        "Candidate: typed relationships may clarify privacy boundaries.",
        "low",
    )

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

    print(f"mygraph — {resolve_graph_path()}")
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
        print(f"⚠ {len(non_high)} of {len(hits)} matched node(s) are NOT high-confidence — see flags below.")
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
                arrow = "→" if direction == "out" else "←"
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
                print(f"      ← {source_id}{tag}")
        # If the node is non-high, repeat the warning at the end too — paraphrase guard
        if node.confidence != "high":
            print(f"    ⚠ Treat content as confidence={node.confidence}; do not quote as verbatim source.")
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
    with open(resolve_graph_path()) as f:
        print(f.read())


def reset() -> None:
    path = resolve_graph_path()
    if os.path.exists(path):
        os.remove(path)
        print(f"Deleted {path}")
    else:
        print("No graph file to delete.")


def list_nodes(type_: str) -> None:
    """Return ALL nodes of a given type. Solves the 'incomplete listing' eval miss
    (e.g. Q8 from the Copilot audit, where 'did i decide on implementing?' returned
    2 of 3 decisions). When you ask for a type, you get every member of that type."""
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
        print(f"⚠ {len(non_high)} of {len(matches)} are NOT high-confidence.")
    print(f"All {t}s ({len(matches)}):\n")
    for n in sorted(matches, key=lambda x: x.label):
        print(f"  [{n.type}] {n.id}{conf_tag(n.confidence)}")
        print(f"    {n.label}")
        if n.body:
            body = n.body if len(n.body) < 200 else n.body[:200] + "…"
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
    with open(log, "a") as f:
        f.write(json.dumps(record) + "\n")
    print(f"Logged state → {log}")
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
        print(f"Seeded. {len(g.nodes)} nodes, {len(g.edges)} edges → {resolve_graph_path()}")
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
    print(USAGE)
    return 1


def cli() -> int:
    return main(sys.argv)


if __name__ == "__main__":
    sys.exit(cli())
