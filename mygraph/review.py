"""
review.py — Stage 3 of the v1 ingest pipeline.

Interactive terminal loop over validated candidates. Keys:
  [a]ccept   merge into the graph
  [r]eject   skip; record the rejection
  [e]dit     pop $EDITOR on the candidate JSON, then re-validate this candidate
  [s]kip     defer to next session
  [q]uit     stop reviewing (already-merged stay merged)

Idempotent: re-running on the same source_id skips already-merged node IDs.

Non-interactive modes (for headless testing / dispatch):
  --auto-accept-high   accept everything with confidence == "high"
  --auto-accept-all    accept every accepted candidate
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from mygraph import Graph
from validator import validate
from eval_log import append as eval_append


def _print_node(node: dict) -> None:
    print(f"\n[{node['type']}] {node['id']}")
    print(f"  label     : {node['label']}")
    if node.get("body"):
        print(f"  body      : {node['body']}")
    print(f"  confidence: {node.get('confidence')}")
    if node.get("excerpt"):
        print(f"  excerpt   : \"{node['excerpt']}\"")


def _print_edge(edge: dict) -> None:
    print(f"\n[edge] {edge['src']} --{edge['type']}--> {edge['dst']}")
    print(f"  confidence: {edge.get('confidence')}")
    if edge.get("excerpt"):
        print(f"  excerpt   : \"{edge['excerpt']}\"")


def _edit_in_editor(payload: dict) -> dict:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as f:
        json.dump(payload, f, indent=2)
        path = f.name
    try:
        subprocess.run([editor, path], check=False)
        with open(path) as f:
            return json.load(f)
    finally:
        os.unlink(path)


def _already_merged_ids(g: Graph, source_id: str) -> set[str]:
    """Nodes that already have a MENTIONED_IN edge to this source."""
    out = set()
    for e in g.edges:
        if e.type == "MENTIONED_IN" and e.dst == source_id:
            out.add(e.src)
        elif e.type == "MENTIONED_IN" and e.src == source_id:
            out.add(e.dst)
    return out


def _ask(prompt: str, valid: set[str]) -> str:
    while True:
        try:
            ans = input(prompt).strip().lower()
        except EOFError:
            return "q"
        if ans in valid:
            return ans
        print(f"  ? choose one of: {sorted(valid)}")


def review(validated: dict, source_text: str,
           auto_accept_high: bool = False,
           auto_accept_all: bool = False) -> dict:
    """
    Returns the user-approved subset of `validated` (same shape).
    Edges whose endpoints aren't approved get filtered after node decisions.
    """
    g = Graph.load()
    src = validated["source"]
    already = _already_merged_ids(g, src["id"])

    approved_nodes: list[dict] = []
    decisions: list[dict] = []  # for eval_log

    auto = auto_accept_all or auto_accept_high
    for node in validated.get("nodes", []):
        if node["id"] in already:
            decisions.append({"kind": "review", "verdict": "skip_already_merged",
                              "candidate_id": node["id"], "source_id": src["id"],
                              "extractor_confidence": node.get("confidence")})
            continue
        if auto:
            verdict = "accept" if (auto_accept_all or node.get("confidence") == "high") else "skip"
            user_edit = None
        else:
            _print_node(node)
            choice = _ask("  [a]ccept [r]eject [e]dit [s]kip [q]uit > ",
                          {"a", "r", "e", "s", "q"})
            user_edit = None
            if choice == "q":
                break
            if choice == "e":
                edited = _edit_in_editor(node)
                # re-validate just this candidate against the source
                subset = {"source": src, "nodes": [edited], "edges": []}
                v_payload, _ = validate(subset, source_text)
                if v_payload["nodes"]:
                    node = v_payload["nodes"][0]
                    user_edit = edited
                    _print_node(node)
                    choice = _ask("  After edit: [a]ccept [r]eject [s]kip > ", {"a", "r", "s"})
                else:
                    print("  (edit failed validation, skipping)")
                    choice = "s"
            verdict = {"a": "accept", "r": "reject", "s": "skip"}.get(choice, "skip")
        decisions.append({"kind": "review", "verdict": verdict,
                          "candidate_id": node["id"], "source_id": src["id"],
                          "extractor_confidence": node.get("confidence"),
                          "user_edit": user_edit})
        if verdict == "accept":
            approved_nodes.append(node)

    approved_node_ids = {n["id"] for n in approved_nodes} | set(g.nodes.keys()) | {src["id"]}
    approved_edges: list[dict] = []
    for edge in validated.get("edges", []):
        if edge["src"] in approved_node_ids and edge["dst"] in approved_node_ids:
            approved_edges.append(edge)

    for d in decisions:
        eval_append(d)

    return {"source": src, "nodes": approved_nodes, "edges": approved_edges,
            "_meta": validated.get("_meta", {})}
