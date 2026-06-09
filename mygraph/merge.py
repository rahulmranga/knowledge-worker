"""
merge.py — Stage 4 of the v1 ingest pipeline.

Idempotent merge of approved candidates into the graph. Slug-based IDs already
make `add_node` / `add_edge` idempotent (per v0). We add:

  - Source node: always merges cleanly (Stage 1 emits it).
  - MENTIONED_IN edge from each new concept node to the Source (auto-injected if
    the extractor didn't include it).
  - Body-diff: if a candidate ID matches an existing node but the body differs,
    we surface the diff and prompt keep_old / replace / append. Logged as a
    review eval_record.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from pathlib import Path

from mygraph import Graph, Node, Edge
try:
    from .eval_log import append as eval_append
except ImportError:  # direct script execution
    from eval_log import append as eval_append


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _diff(old: str, new: str) -> str:
    return "\n".join(difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile="existing", tofile="candidate", lineterm=""))


def _resolve_body_conflict(existing: Node, cand: dict, interactive: bool) -> str:
    if not interactive:
        # default to keep_old in non-interactive mode (safest)
        eval_append({"kind": "merge_body_conflict", "candidate_id": cand["id"],
                     "resolution": "keep_old_auto"})
        return existing.body
    print(f"\n[merge] body conflict for {cand['id']}:")
    print(_diff(existing.body, cand.get("body", "")))
    choice = ""
    while choice not in {"k", "r", "a"}:
        try:
            choice = input("  [k]eep old / [r]eplace / [a]ppend > ").strip().lower()
        except EOFError:
            choice = "k"
    eval_append({"kind": "merge_body_conflict", "candidate_id": cand["id"],
                 "resolution": {"k": "keep_old", "r": "replace", "a": "append"}[choice]})
    if choice == "k":
        return existing.body
    if choice == "r":
        return cand.get("body", "")
    return (existing.body + "\n\n--- (appended) ---\n" + cand.get("body", "")).strip()


def _is_enabled_by_candidate(g: Graph, edge: Edge) -> bool:
    src = g.nodes.get(edge.src)
    dst = g.nodes.get(edge.dst)
    return bool(
        edge.type == "SERVES"
        and src
        and dst
        and src.type == "idea"
        and dst.type in {"decision", "goal"}
    )


def merge(approved: dict, interactive: bool = True) -> tuple[int, int]:
    """
    Merge approved nodes/edges into the graph. Returns (nodes_added, edges_added).
    """
    g = Graph.load()
    src = approved["source"]
    src_id = src["id"]

    # 1. Source node always merges
    src_existed = src_id in g.nodes
    g.add_node(Node(id=src_id, type="source", label=src["label"],
                    body=src.get("body", ""), confidence="high"))
    nodes_added = 0 if src_existed else 1

    # 2. Concept nodes
    for cand in approved.get("nodes", []):
        nid = cand["id"]
        if nid in g.nodes:
            existing = g.nodes[nid]
            new_body = cand.get("body", "")
            if new_body and new_body.strip() != (existing.body or "").strip():
                resolved = _resolve_body_conflict(existing, cand, interactive)
                existing.body = resolved
            existing.label = cand.get("label", existing.label)
            existing.confidence = cand.get("confidence", existing.confidence)
        else:
            g.add_node(Node(id=nid, type=cand["type"], label=cand["label"],
                            body=cand.get("body", ""),
                            confidence=cand.get("confidence", "medium")))
            nodes_added += 1

    # 3. Edges (extractor-emitted)
    edges_added = 0
    for cand in approved.get("edges", []):
        try:
            e = Edge(src=cand["src"], dst=cand["dst"], type=cand["type"],
                     source_id=src_id, excerpt=cand.get("excerpt", ""),
                     confidence=cand.get("confidence", "medium"))
        except (AssertionError, ValueError) as exc:
            eval_append({"kind": "merge_edge_skipped", "edge": cand, "reason": str(exc)})
            continue
        before = len(g.edges)
        g.add_edge(e)
        if len(g.edges) > before:
            edges_added += 1
        else:
            # de-duped: refresh last_seen on the existing edge
            for existing in g.edges:
                if (existing.src, existing.dst, existing.type, existing.source_id) == \
                   (e.src, e.dst, e.type, e.source_id):
                    existing.last_seen = _now()
                    break

        # Preserve idea flow while adding a navigable back-reference.
        if _is_enabled_by_candidate(g, e):
            reverse = Edge(src=e.dst, dst=e.src, type="ENABLED_BY",
                           source_id=src_id, excerpt=e.excerpt,
                           confidence=e.confidence)
            before = len(g.edges)
            g.add_edge(reverse)
            if len(g.edges) > before:
                edges_added += 1

    # 4. Auto-inject MENTIONED_IN for any approved node missing one to this source
    new_concept_ids = {n["id"] for n in approved.get("nodes", [])}
    has_mentioned = {(e.src, e.dst, e.type) for e in g.edges if e.type == "MENTIONED_IN"}
    for nid in new_concept_ids:
        if nid == src_id:
            continue
        if (nid, src_id, "MENTIONED_IN") in has_mentioned:
            continue
        # find the candidate to grab its excerpt
        cand = next((n for n in approved.get("nodes", []) if n["id"] == nid), {})
        e = Edge(src=nid, dst=src_id, type="MENTIONED_IN",
                 source_id=src_id, excerpt=cand.get("excerpt", ""),
                 confidence=cand.get("confidence", "medium"))
        before = len(g.edges)
        g.add_edge(e)
        if len(g.edges) > before:
            edges_added += 1

    g.save()
    return nodes_added, edges_added
