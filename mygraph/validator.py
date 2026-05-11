"""
validator.py — Stage 2 of the v1 ingest pipeline.

Takes the extractor's candidates.json and runs deterministic checks:
  - shape (per the extractor's tool_schema)
  - excerpt verification (`high` confidence MUST substring-match the source markdown,
    after whitespace normalization)
  - orphan edge check (src/dst must resolve to existing node OR another candidate)
  - ID format (`^[a-z]+:[a-z0-9-]+$`)

Output: a validated payload (same shape as input) plus a manifest of
  accepted / demoted-with-reason / rejected-with-reason.

No external deps. Lightweight schema check (we control both producer and consumer).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mygraph import Graph, NODE_TYPES, EDGE_TYPES

ID_RE = re.compile(r"^[a-z]+:[a-z0-9-]+$")
WS_RE = re.compile(r"\s+")


def _norm(s: str) -> str:
    return WS_RE.sub(" ", s).strip().lower()


@dataclass
class Manifest:
    accepted_nodes: list[dict] = field(default_factory=list)
    accepted_edges: list[dict] = field(default_factory=list)
    demoted_nodes: list[tuple[dict, str]] = field(default_factory=list)
    rejected_nodes: list[tuple[dict, str]] = field(default_factory=list)
    rejected_edges: list[tuple[dict, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"  accepted : {len(self.accepted_nodes)} nodes / {len(self.accepted_edges)} edges\n"
            f"  demoted  : {len(self.demoted_nodes)} nodes\n"
            f"  rejected : {len(self.rejected_nodes)} nodes / {len(self.rejected_edges)} edges"
        )


def _check_shape(payload: dict) -> list[str]:
    errs = []
    if not isinstance(payload, dict):
        return ["payload is not a dict"]
    if "source" not in payload or not isinstance(payload["source"], dict):
        errs.append("missing source object")
    else:
        for k in ("id", "label", "body"):
            if k not in payload["source"]:
                errs.append(f"source missing field: {k}")
    for key in ("nodes", "edges"):
        if key not in payload or not isinstance(payload[key], list):
            errs.append(f"missing {key} list")
    return errs


def validate(payload: dict, source_text: str) -> tuple[dict, Manifest]:
    """Return (validated_payload, manifest). validated_payload mutates confidences and drops rejects."""
    shape_errs = _check_shape(payload)
    if shape_errs:
        raise ValueError("validator: malformed payload → " + "; ".join(shape_errs))

    g = Graph.load()
    manifest = Manifest()
    src_norm = _norm(source_text)

    # validate Source
    src = payload["source"]
    if not ID_RE.match(src["id"]) or not src["id"].startswith("source:"):
        raise ValueError(f"validator: invalid source id: {src['id']!r}")

    # validate nodes
    valid_nodes: list[dict] = []
    candidate_ids: set[str] = {src["id"]}
    for node in payload.get("nodes", []):
        nid = node.get("id", "")
        if not ID_RE.match(nid):
            manifest.rejected_nodes.append((node, "id_format"))
            continue
        if node.get("type") not in NODE_TYPES:
            manifest.rejected_nodes.append((node, f"bad_type:{node.get('type')}"))
            continue
        if node.get("confidence") not in {"high", "medium", "low"}:
            manifest.rejected_nodes.append((node, "bad_confidence"))
            continue
        # provenance-or-bust: high → must have excerpt + must substring-match source
        excerpt = (node.get("excerpt") or "").strip()
        if node["confidence"] == "high":
            if not excerpt:
                node["confidence"] = "low"
                manifest.demoted_nodes.append((node, "no_excerpt"))
            elif _norm(excerpt) not in src_norm:
                node["confidence"] = "low"
                manifest.demoted_nodes.append((node, "excerpt_not_in_source"))
        candidate_ids.add(nid)
        valid_nodes.append(node)
        manifest.accepted_nodes.append(node)

    # validate edges
    valid_edges: list[dict] = []
    for edge in payload.get("edges", []):
        if edge.get("type") not in EDGE_TYPES:
            manifest.rejected_edges.append((edge, f"bad_type:{edge.get('type')}"))
            continue
        if edge.get("confidence") not in {"high", "medium", "low"}:
            manifest.rejected_edges.append((edge, "bad_confidence"))
            continue
        for endpoint_key in ("src", "dst"):
            ep = edge.get(endpoint_key, "")
            if not ID_RE.match(ep):
                manifest.rejected_edges.append((edge, f"{endpoint_key}_id_format"))
                break
            if ep not in g.nodes and ep not in candidate_ids:
                manifest.rejected_edges.append((edge, f"orphan_{endpoint_key}:{ep}"))
                break
        else:
            valid_edges.append(edge)
            manifest.accepted_edges.append(edge)

    validated = dict(payload)
    validated["nodes"] = valid_nodes
    validated["edges"] = valid_edges
    return validated, manifest


def main():
    import json
    import sys
    if len(sys.argv) < 3:
        print("Usage: python validator.py <candidates.json> <source.md>")
        return 1
    payload = json.loads(Path(sys.argv[1]).read_text())
    src_text = Path(sys.argv[2]).read_text()
    _, manifest = validate(payload, src_text)
    print(manifest.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
