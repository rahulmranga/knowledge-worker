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
    """Write a small fictional demo graph to the active graph path.

    The seed intentionally avoids private-owner facts so generated public
    examples can be committed safely.
    """
    g = Graph()

    nodes = [
        Node(id="source:demo-notes", type="source", label="demo-notes.md",
             body="Fictional project notes used to demonstrate provenance-backed memory."),
        Node(id="source:architecture-note", type="source", label="architecture-note.md",
             body="Fictional architecture note for the public demo graph."),
        Node(id="person:demo-owner", type="person", label="Demo Owner",
             body="A fictional graph owner used only for public examples."),
        Node(id="project:knowledge-worker", type="project", label="knowledge-worker",
             body="A local-first toolkit for source-backed AI memory."),
        Node(id="idea:context-memory", type="idea", label="Context memory",
             body="AI sessions improve when durable context is stored as concepts instead of loose transcript chunks."),
        Node(id="idea:provenance-first", type="idea", label="Provenance first",
             body="Every durable claim should point back to source evidence."),
        Node(id="goal:trusted-ai-assistance", type="goal", label="Trusted AI assistance",
             body="Make assistant responses easier to verify and continue across sessions."),
        Node(id="question:storage-backend", type="question", label="When should storage move beyond JSON?",
             body="Open question: keep JSON until size or concurrency makes it awkward."),
        Node(id="decision:json-first", type="decision", label="Use JSON first",
             body="Start with a simple JSON store before introducing a database."),
        Node(id="topic:knowledge-graphs", type="topic", label="Knowledge graphs",
             body="Structured concepts and relationships for durable context."),
        Node(id="topic:local-first", type="topic", label="Local-first software",
             body="Software that keeps user data local unless the owner chooses otherwise."),
        Node(id="reference:coggrag", type="reference", label="CogGRAG",
             body="A public reference about cognition-inspired graph retrieval.", confidence="medium"),
    ]
    for node in nodes:
        g.add_node(node)

    def edge(src: str, dst: str, type_: str, source_id: str,
             excerpt: str = "", confidence: str = "high") -> None:
        g.add_edge(Edge(src=src, dst=dst, type=type_, source_id=source_id,
                        excerpt=excerpt, confidence=confidence))

    src_demo = "source:demo-notes"
    src_arch = "source:architecture-note"
    for node_id, excerpt in [
        ("person:demo-owner", "The demo owner wants assistant memory that survives across sessions."),
        ("project:knowledge-worker", "Build a local-first toolkit for source-backed AI memory."),
        ("idea:context-memory", "Store durable concepts instead of loose transcript chunks."),
        ("idea:provenance-first", "Every durable claim needs source evidence."),
        ("goal:trusted-ai-assistance", "Make assistant responses easier to verify and continue."),
        ("topic:knowledge-graphs", "Use a graph of concepts and relationships."),
        ("topic:local-first", "Keep owner data local unless explicitly exported."),
    ]:
        edge(node_id, src_demo, "MENTIONED_IN", src_demo, excerpt)

    for node_id, excerpt in [
        ("question:storage-backend", "When should storage move beyond JSON?"),
        ("decision:json-first", "Use JSON first; add a database only when needed."),
        ("reference:coggrag", "CogGRAG is a public reference for graph retrieval."),
    ]:
        edge(node_id, src_arch, "MENTIONED_IN", src_arch, excerpt)

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
    print(USAGE)
    return 1


def cli() -> int:
    return main(sys.argv)


if __name__ == "__main__":
    sys.exit(cli())
