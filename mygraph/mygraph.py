"""
mygraph.py — personal knowledge graph (v0 schema, v1 ingest/check/export/viz).

Single-file core, stdlib-only. Read SPEC.md → V1_DESIGN.md → V1_PLAN.md.

Usage:
    python mygraph.py seed                                # v0: populate from known nodes
    python mygraph.py summary                             # stats overview
    python mygraph.py query "h1b"                         # search + neighbors + provenance
    python mygraph.py path goal:my-goal project:knowledge-worker
    python mygraph.py dump                                # raw JSON
    python mygraph.py reset                               # delete graph file

    python mygraph.py ingest <path/to/file.md>            # v1 M1: 5-stage extractor pipeline
    python mygraph.py check [--provenance|--stale-edges|--pairs N|--source-candidates DIR]
    python mygraph.py export --ttl                        # v1 M3: emit mygraph.ttl
    python mygraph.py viz                                 # v1 M4: open custom force-directed HTML

Graph file: ./mygraph.json (next to this script).
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
GRAPH_PATH = os.path.join(HERE, "mygraph.json")

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

    def __post_init__(self):
        assert self.type in NODE_TYPES, f"unknown node type: {self.type}"
        assert self.confidence in CONFIDENCE, f"bad confidence: {self.confidence}"


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

    def __post_init__(self):
        assert self.type in EDGE_TYPES, f"unknown edge type: {self.type}"
        assert self.confidence in CONFIDENCE, f"bad confidence: {self.confidence}"


# ---------- store -------------------------------------------------------------

class Graph:
    def __init__(self, nodes: Optional[dict[str, Node]] = None,
                 edges: Optional[list[Edge]] = None):
        self.nodes: dict[str, Node] = nodes or {}
        self.edges: list[Edge] = edges or []

    @classmethod
    def load(cls, path: str = GRAPH_PATH) -> "Graph":
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

    def save(self, path: str = GRAPH_PATH) -> None:
        data = {
            "nodes": {nid: asdict(n) for nid, n in self.nodes.items()},
            "edges": [asdict(e) for e in self.edges],
        }
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
    """EXAMPLE seed: personal graph snapshot from the author's initial setup (2026-05-08).

    Replace or extend this with your own nodes to bootstrap your graph.
    Every node points back to at least one Source. The three sources here are:
      - inspiration.md (conversation export)
      - cowin.md (project write-up)
      - claude-2026-05-08-knowledge-worker (bootstrap conversation)
    """
    g = Graph.load()

    # -- sources
    s_insp = Node(id="source:inspiration-md", type="source",
                  label="inspiration.md",
                  body="Gemini conversation about GraphRAG + RL + knowledge worker, exported 2026-05-08")
    s_cowin = Node(id="source:cowin-md", type="source",
                   label="cowin.md",
                   body="Rahul's post about the CoWIN email notifier, ~500 users across 22 Indian states during second COVID wave.")
    s_chat = Node(id="source:claude-2026-05-08-knowledge-worker", type="source",
                  label="Claude chat 2026-05-08 — knowledge worker",
                  body="This conversation. Where the spec and v0 prototype were sketched.")
    # M0.3: inspiration.md as a formal Source (referenced as origin of CogGRAG/HippoRAG/Graph-R1).
    s_insp_md = Node(id="source:inspiration-md-file", type="source",
                     label="inspiration.md (workspace file)",
                     body="The local inspiration.md at the project root. Origin of references to CogGRAG, HippoRAG, Graph-R1, HyperGraphPro.")
    for s in (s_insp, s_cowin, s_chat, s_insp_md):
        g.add_node(s)

    # -- people
    rahul = Node(id="person:rahul", type="person", label="Rahul",
                 body="Knowledge worker at a biotech company, on H1B with green card pending. Long-term entrepreneurial goal. Third-generation entrepreneurial family.")
    saumya = Node(id="person:saumya-shikhar", type="person", label="Saumya Shikhar",
                  body="Friend and ex-colleague who built the original CoWIN web platform that inspired Rahul's email notifier.")
    dad = Node(id="person:dad", type="person", label="Dad",
               body="Writer. Spiritual, meditates. Said: 'it's all just a mere happening, like a drama or a play.'",
               confidence="medium")
    for p in (rahul, saumya, dad):
        g.add_node(p)

    # -- topics
    topics = [
        ("land-evaluation", "Land evaluation"),
        ("knowledge-graphs", "Knowledge Graphs"),
        ("rag", "RAG"),
        ("graphrag", "GraphRAG"),
        ("reinforcement-learning", "Reinforcement Learning"),
        ("fine-tuning", "Fine-tuning"),
        ("claude-code", "Claude Code"),
        ("h1b", "H1B"),
        ("green-card", "Green Card"),
        ("taxes", "Taxes"),
        ("finances", "Finances"),
        ("flow-theory", "Flow theory"),
        ("biotech", "Biotech"),
        ("entrepreneurship", "Entrepreneurship"),
        ("medium-publishing", "Medium publishing"),
        ("python", "Python"),
        ("agentic-systems", "Agentic systems"),
    ]
    for s, lab in topics:
        g.add_node(Node(id=f"topic:{s}", type="topic", label=lab))

    # -- references
    coggrag = Node(id="reference:coggrag", type="reference",
                   label="CogGRAG (arXiv:2503.06567)",
                   body="Human Cognition Inspired RAG with Knowledge Graph for Complex Problem Solving. Decomposition + exploratory retrieval + dual-process verification.",
                   confidence="medium")  # we haven't independently verified the abstract
    hipporag = Node(id="reference:hipporag", type="reference",
                    label="HippoRAG",
                    body="Neurobiologically-inspired RAG using PageRank over a KG, 2024.",
                    confidence="medium")
    graphr1 = Node(id="reference:graph-r1", type="reference",
                   label="Graph-R1 (claimed arXiv:2507.21892)",
                   body="Per inspiration.md: end-to-end agentic GraphRAG with multi-turn retrieval. Existence not independently verified.",
                   confidence="low")
    flow = Node(id="reference:csikszentmihalyi-flow", type="reference",
                label="Csikszentmihalyi — Flow theory (Planyway summary)",
                body="https://planyway.com/blog/mihaly-csikszentmihalyi-flow-theory")
    for r in (coggrag, hipporag, graphr1, flow):
        g.add_node(r)

    # -- ideas
    idea_kgw = Node(
        id="idea:kg-rag-ft-knowledge-worker",
        type="idea",
        label="KG + RAG + small fine-tune ≈ knowledge worker",
        body=("Knowledge graphs provide associative structure, RAG provides recall, "
              "and a small fine-tune (or strong system prompt) provides taste / voice. "
              "Together they approximate how a domain knowledge worker reasons. "
              "Originally framed as 'mimic the brain'; engineering-wise, that framing is a hook, not a compass."),
        confidence="high",
    )
    idea_rahul_centered = Node(
        id="idea:rahul-centered-graph",
        type="idea",
        label="Personal AI memory should be person-centered, not conversation-centered",
        body=("Vanilla 'chat memory' indexes conversation chunks. The durable thing is the person's "
              "concepts, decisions, and open questions — conversations are evidence, not substance."),
        confidence="high",
    )
    idea_provenance = Node(
        id="idea:provenance-or-bust",
        type="idea",
        label="Provenance-or-bust",
        body="Every node and claim must trace back to a literal source excerpt, or it's slop. Anti-AI-slop spine of the project.",
        confidence="high",
    )
    idea_rl_dessert = Node(
        id="idea:rl-is-dessert",
        type="idea",
        label="RL is dessert, not dinner",
        body="At v0, RL on a personal KG is unjustified. KG + RAG + good prompting earns most of the value. RL only after a clear ceiling.",
        confidence="high",
    )
    idea_one_project = Node(
        id="idea:abc-is-one-project-sequenced",
        type="idea",
        label="A, B, C are one project sequenced",
        body=("Work project, Medium article, and personal local tool are not three competing tracks. "
              "Build B (the personal tool) first; A and C fall out as artifacts and writing material."),
        confidence="high",
    )
    idea_land_eval = Node(
        id="idea:land-evaluation-as-rb-test-case",
        type="idea",
        label="land_evaluation as both an Idea and a v1 Source folder",
        body=("Per SPEC §9 (resolved 2026-05-08): the land_evaluation folder at "
              "~/Desktop/ideas/land_evaluation is treated as (a) a Source folder we "
              "ingest from at v1, and (b) an Idea node — 'apply Rahul-Brain methodology "
              "to land_evaluation.' Folder access deferred until ingest run."),
        confidence="high",
    )
    for i in (idea_kgw, idea_rahul_centered, idea_provenance, idea_rl_dessert,
              idea_one_project, idea_land_eval):
        g.add_node(i)

    # -- projects
    rb = Node(id="project:rahul-brain", type="project",
              label="Rahul Brain",
              body="A personal knowledge graph that survives between Claude conversations. v0 = JSON-backed, single Python file, schema-led.")
    cowin = Node(id="project:cowin-notifier", type="project",
                 label="CoWIN email notifier",
                 body="During India's second COVID wave, Rahul built an email notification system on top of the Indian govt vaccination API. ~500 users across 22 states signed up within a day. Hit policy/email-platform limits, stopped onboarding. Per Rahul: 'technically a failure; from a solution point of view, it helped people.'")
    for p in (rb, cowin):
        g.add_node(p)

    # -- goals
    goals = [
        Node(id="goal:green-card", type="goal", label="Green card",
             body="Strengthen US footing. A real technical artifact + writing supports NIW-type evidence."),
        Node(id="goal:entrepreneurship", type="goal", label="Entrepreneurship",
             body="Long-term aim. Third-generation entrepreneurial family."),
        Node(id="goal:flow", type="goal", label="Live in flow",
             body="Csikszentmihalyi's challenge-zone. Rahul yearns for flow especially."),
        Node(id="goal:not-ai-slop", type="goal", label="Not AI slop",
             body="Anything we publish has to be honest, verifiable, and add original value. The provenance-or-bust principle is in service of this goal."),
    ]
    for go in goals:
        g.add_node(go)

    # -- questions
    qs = [
        Node(id="question:medium-or-venue", type="question",
             label="Medium or a more formal venue for the writeup?",
             body="Open."),
        Node(id="question:work-project-or-side-project", type="question",
             label="Is Rahul Brain a work project, a side project, or both?",
             body="Tonight's lean: side project first, work-project later if it generalizes."),
        Node(id="question:storage-jsonl-vs-kuzu-vs-graphify", type="question",
             label="JSON vs Kùzu vs graphify.net for storage layer?",
             body="v0 = JSON. Reassess when JSON gets painful. graphify.net unverified by Claude tonight; user to evaluate."),
    ]
    for q in qs:
        g.add_node(q)

    # -- decisions
    decs = [
        Node(id="decision:v0-json-store", type="decision",
             label="v0 uses JSON, not Kùzu",
             body="Reduce stack to stdlib so we ship tonight."),
        Node(id="decision:rahul-centered-not-conversation-centered", type="decision",
             label="Graph centers on Rahul (durable concepts), not conversations",
             body="Conversations are Sources; nodes are concepts."),
        Node(id="decision:both-spec-and-prototype", type="decision",
             label="Ship spec AND prototype in this session",
             body="User asked for both; they're cheap together."),
    ]
    for d in decs:
        g.add_node(d)

    # ============== edges ==============
    # every node gets a MENTIONED_IN to its primary source(s).

    def mentioned(node_id: str, source_id: str, excerpt: str = "", conf: str = "high"):
        g.add_edge(Edge(src=node_id, dst=source_id, type="MENTIONED_IN",
                        source_id=source_id, excerpt=excerpt, confidence=conf))

    # -- provenance to inspiration.md
    mentioned("idea:kg-rag-ft-knowledge-worker", "source:inspiration-md",
              excerpt="in essence I want to mimic knowledge worker like how it is in the brain.")
    mentioned("reference:coggrag", "source:inspiration-md",
              excerpt="Human Cognition Inspired RAG with Knowledge Graph for Complex Problem Solving (arXiv:2503.06567)")
    mentioned("reference:hipporag", "source:inspiration-md",
              excerpt="Hippocampal Retrieval (HippoRAG)")
    mentioned("reference:graph-r1", "source:inspiration-md",
              excerpt="Graph-R1 (2025): An end-to-end agentic framework", conf="low")
    # M0.3: bind references to the local inspiration.md file Source as well.
    mentioned("reference:coggrag", "source:inspiration-md-file",
              excerpt="Human Cognition Inspired RAG with Knowledge Graph for Complex Problem Solving (arXiv:2503.06567)")
    mentioned("reference:hipporag", "source:inspiration-md-file",
              excerpt="Hippocampal Retrieval (HippoRAG)")
    mentioned("reference:graph-r1", "source:inspiration-md-file",
              excerpt="Graph-R1 (2025): An end-to-end agentic framework modeling retrieval as a multi-turn interaction", conf="low")
    mentioned("topic:graphrag", "source:inspiration-md",
              excerpt="graph rag with reinforcement learning")
    mentioned("topic:reinforcement-learning", "source:inspiration-md")
    mentioned("topic:knowledge-graphs", "source:inspiration-md")
    mentioned("topic:rag", "source:inspiration-md")
    mentioned("topic:agentic-systems", "source:inspiration-md")

    # -- provenance to cowin.md
    mentioned("project:cowin-notifier", "source:cowin-md",
              excerpt="around 500 users from 22 states across India opted for the service within one day")
    mentioned("person:saumya-shikhar", "source:cowin-md",
              excerpt="my friend and ex-colleague, Saumya Shikhar")
    mentioned("topic:python", "source:cowin-md", excerpt="#python")

    # -- provenance to tonight's chat
    mentioned("person:rahul", "source:claude-2026-05-08-knowledge-worker",
              excerpt="I am also a worker in a biotech company on my H1B visa with green card, but long term have an entrepreneurial goal.")
    mentioned("person:dad", "source:claude-2026-05-08-knowledge-worker",
              excerpt="my dad is a writer and he is spirtual and meditates")
    mentioned("project:rahul-brain", "source:claude-2026-05-08-knowledge-worker",
              excerpt="i want to be part of a good AI project, and this is under utilized")
    mentioned("idea:rahul-centered-graph", "source:claude-2026-05-08-knowledge-worker",
              excerpt="if i'm building a knowledge worker, for myself, won't i want to *build* information about \"Rahul\" or \"rahul's ideas\"?")
    mentioned("idea:provenance-or-bust", "source:claude-2026-05-08-knowledge-worker",
              excerpt="Not AI Slop. maybe")
    mentioned("idea:rl-is-dessert", "source:claude-2026-05-08-knowledge-worker",
              excerpt="RL is dessert, not dinner")
    mentioned("idea:abc-is-one-project-sequenced", "source:claude-2026-05-08-knowledge-worker",
              excerpt="A, B, and C are not three projects. They're one project sequenced.")
    mentioned("idea:land-evaluation-as-rb-test-case", "source:claude-2026-05-08-knowledge-worker",
              excerpt="this is also an idea/inspiration. I changed the folder structure for you but mostly for ME!")
    mentioned("topic:land-evaluation", "source:claude-2026-05-08-knowledge-worker",
              excerpt="land_evaluation")
    mentioned("goal:green-card", "source:claude-2026-05-08-knowledge-worker",
              excerpt="This will help me in my green card application - article or whatever.")
    mentioned("goal:entrepreneurship", "source:claude-2026-05-08-knowledge-worker",
              excerpt="long term have an entrepreneurial goal")
    mentioned("goal:flow", "source:claude-2026-05-08-knowledge-worker",
              excerpt="we as humans yearn for the moments of flow -especially me-")
    mentioned("goal:not-ai-slop", "source:claude-2026-05-08-knowledge-worker",
              excerpt="Not AI Slop. maybe")
    mentioned("topic:claude-code", "source:claude-2026-05-08-knowledge-worker",
              excerpt="Granted I've not been using claude code even though i paid for it")
    mentioned("topic:h1b", "source:claude-2026-05-08-knowledge-worker", excerpt="H1B visa")
    mentioned("topic:green-card", "source:claude-2026-05-08-knowledge-worker", excerpt="green card")
    mentioned("topic:taxes", "source:claude-2026-05-08-knowledge-worker", excerpt="finances and taxes")
    mentioned("topic:finances", "source:claude-2026-05-08-knowledge-worker", excerpt="finances and taxes")
    mentioned("topic:biotech", "source:claude-2026-05-08-knowledge-worker", excerpt="biotech company")
    mentioned("topic:flow-theory", "source:claude-2026-05-08-knowledge-worker")
    mentioned("topic:medium-publishing", "source:claude-2026-05-08-knowledge-worker",
              excerpt="OR I can prove something and publish a medium article")
    mentioned("topic:fine-tuning", "source:claude-2026-05-08-knowledge-worker")
    mentioned("reference:csikszentmihalyi-flow", "source:claude-2026-05-08-knowledge-worker",
              excerpt="https://planyway.com/blog/mihaly-csikszentmihalyi-flow-theory")
    mentioned("question:medium-or-venue", "source:claude-2026-05-08-knowledge-worker")
    mentioned("question:work-project-or-side-project", "source:claude-2026-05-08-knowledge-worker")
    mentioned("question:storage-jsonl-vs-kuzu-vs-graphify", "source:claude-2026-05-08-knowledge-worker",
              excerpt="there's graphify https://graphify.net/")

    # -- relational edges
    SRC = "source:claude-2026-05-08-knowledge-worker"

    def rel(s, d, t, src=SRC, ex="", conf="high"):
        g.add_edge(Edge(src=s, dst=d, type=t, source_id=src, excerpt=ex, confidence=conf))

    # ideas Rahul holds
    for idea_id in ("idea:kg-rag-ft-knowledge-worker", "idea:rahul-centered-graph",
                    "idea:provenance-or-bust", "idea:rl-is-dessert",
                    "idea:abc-is-one-project-sequenced"):
        rel("person:rahul", idea_id, "HAS_IDEA")

    # idea → topics
    rel("idea:kg-rag-ft-knowledge-worker", "topic:knowledge-graphs", "RELATES_TO")
    rel("idea:kg-rag-ft-knowledge-worker", "topic:rag", "RELATES_TO")
    rel("idea:kg-rag-ft-knowledge-worker", "topic:fine-tuning", "RELATES_TO")
    rel("idea:kg-rag-ft-knowledge-worker", "topic:agentic-systems", "RELATES_TO")
    rel("idea:rahul-centered-graph", "topic:knowledge-graphs", "RELATES_TO")
    rel("idea:provenance-or-bust", "topic:medium-publishing", "RELATES_TO")
    rel("idea:rl-is-dessert", "topic:reinforcement-learning", "RELATES_TO")
    rel("idea:land-evaluation-as-rb-test-case", "topic:land-evaluation", "RELATES_TO")
    rel("idea:land-evaluation-as-rb-test-case", "project:rahul-brain", "RELATES_TO",
        ex="apply Rahul-Brain methodology to land_evaluation")

    # idea → references
    rel("idea:kg-rag-ft-knowledge-worker", "reference:coggrag", "SUPPORTED_BY", src="source:inspiration-md")
    rel("idea:kg-rag-ft-knowledge-worker", "reference:hipporag", "SUPPORTED_BY", src="source:inspiration-md")
    rel("idea:kg-rag-ft-knowledge-worker", "reference:graph-r1", "SUPPORTED_BY",
        src="source:inspiration-md", conf="low")

    # ideas in tension
    rel("idea:rl-is-dessert", "idea:kg-rag-ft-knowledge-worker", "CHALLENGES",
        ex="scopes the original 'KG+RAG+RL' framing — argues RL is unnecessary at v0")

    # project → goals
    rel("project:rahul-brain", "goal:green-card", "SERVES",
        ex="A real artifact + writeup is stronger NIW evidence than the article alone.")
    rel("project:rahul-brain", "goal:entrepreneurship", "SERVES")
    rel("project:rahul-brain", "goal:flow", "SERVES",
        ex="Sized for the challenge-zone — non-trivial but tractable in a sitting.")
    rel("project:rahul-brain", "goal:not-ai-slop", "SERVES")

    # project → topics
    rel("project:rahul-brain", "topic:knowledge-graphs", "INVOLVES")
    rel("project:rahul-brain", "topic:rag", "INVOLVES")
    rel("project:rahul-brain", "topic:python", "INVOLVES")
    rel("project:rahul-brain", "topic:agentic-systems", "INVOLVES")

    # project → people
    rel("project:rahul-brain", "person:rahul", "INVOLVES")
    rel("project:cowin-notifier", "person:saumya-shikhar", "INVOLVES",
        src="source:cowin-md",
        ex="I would like to thank Saumya for the inspiration")
    rel("project:cowin-notifier", "person:rahul", "INVOLVES", src="source:cowin-md")
    rel("project:cowin-notifier", "topic:python", "INVOLVES", src="source:cowin-md")
    rel("project:cowin-notifier", "goal:entrepreneurship", "SERVES", src="source:cowin-md",
        ex="3rd generation entrepreneurial family")

    # questions → topics/projects
    rel("question:medium-or-venue", "topic:medium-publishing", "ABOUT")
    rel("question:work-project-or-side-project", "project:rahul-brain", "ABOUT")
    rel("question:storage-jsonl-vs-kuzu-vs-graphify", "project:rahul-brain", "ABOUT")

    # decisions → source
    rel("decision:v0-json-store", SRC, "MADE_AT")
    rel("decision:rahul-centered-not-conversation-centered", SRC, "MADE_AT")
    rel("decision:both-spec-and-prototype", SRC, "MADE_AT")

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

    print(f"mygraph — {GRAPH_PATH}")
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
    with open(GRAPH_PATH) as f:
        print(f.read())


def reset() -> None:
    if os.path.exists(GRAPH_PATH):
        os.remove(GRAPH_PATH)
        print(f"Deleted {GRAPH_PATH}")
    else:
        print("No graph file to delete.")


def list_nodes(type_: str) -> None:
    """Return ALL nodes of a given type. Solves the 'incomplete listing' eval miss
    (e.g. Q8 from the Copilot audit, where 'did i decide on implementing?' returned
    2 of 3 decisions). When you ask for a type, you get every member of that type."""
    # Accept plural ("decisions" → "decision")
    t = type_.lower().rstrip("s")
    if t not in NODE_TYPES:
        print(f"Unknown type '{type_}'. Valid: {', '.join(sorted(NODE_TYPES))}")
        return
    g = Graph.load()
    matches = [n for n in g.nodes.values() if n.type == t]
    if not matches:
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
  python mygraph.py seed
  python mygraph.py summary
  python mygraph.py query <string>
  python mygraph.py list <type>           # all nodes of a type (decision, goal, idea, ...)
  python mygraph.py path <node_id> <node_id>
  python mygraph.py state "<entry>"       # append mood/state to state_log.jsonl (sidecar)
  python mygraph.py dump
  python mygraph.py reset
  python mygraph.py ingest <path/to/file.md> [--non-interactive] [--auto-accept-high]
                                              [--candidates-file <path>]
                                              [--backend claude|ollama] [--model <name>]
  python mygraph.py check [--provenance] [--stale-edges] [--pairs N]
                          [--source-candidates <dir>]
  python mygraph.py export --ttl [--out <path>]
  python mygraph.py viz [--no-open]
"""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(USAGE)
        return 1
    cmd = argv[1]
    if cmd == "seed":
        g = seed()
        print(f"Seeded. {len(g.nodes)} nodes, {len(g.edges)} edges → {GRAPH_PATH}")
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
            print("Need a state entry. Example: python mygraph.py state \"manic, 1:48am, coffee\"")
            return 1
        state(" ".join(argv[2:]))
        return 0
    if cmd == "ingest":
        from ingest import run_ingest
        return run_ingest(argv[2:])
    if cmd == "check":
        from check import run_check
        return run_check(argv[2:])
    if cmd == "export":
        from owl_io import run_export
        return run_export(argv[2:])
    if cmd == "viz":
        from viz import run_viz
        return run_viz(argv[2:])
    print(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
