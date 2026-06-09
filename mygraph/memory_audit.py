"""
memory_audit.py - read-only graph analytics and Memory Audit HTML.

Usage:
  mykg audit --out analytics.json
  mykg audit --out analytics.json --html memory_audit.html

The audit is intentionally local and deterministic. It uses the public Graph API
instead of reading graph JSON directly, keeps source/provenance edges separate
from semantic graph analytics, and writes generated artifacts only when asked.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from .mygraph import Edge, Graph
except ImportError:  # direct script execution: python mygraph/memory_audit.py
    from mygraph import Edge, Graph


PROVENANCE_EDGE_TYPES = {"MENTIONED_IN", "MADE_AT"}
BACK_REFERENCE_EDGE_TYPES = {"ENABLED_BY"}
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _semantic_ids(g: Graph) -> list[str]:
    return sorted(nid for nid, node in g.nodes.items() if node.type != "source")


def _semantic_edges(g: Graph, ids: set[str]) -> list[Edge]:
    return [
        edge
        for edge in g.edges
        if edge.src in ids
        and edge.dst in ids
        and edge.type not in PROVENANCE_EDGE_TYPES
    ]


def _idea_flow_edges(edges: Iterable[Edge]) -> list[Edge]:
    """Keep causal back-references from canceling forward idea-flow signals."""
    return [edge for edge in edges if edge.type not in BACK_REFERENCE_EDGE_TYPES]


def _source_projection_edges(g: Graph, ids: set[str]) -> set[tuple[str, str]]:
    """Connect non-source nodes that share a source, without adding source nodes.

    These edges are an audit-time projection only. They keep provenance useful
    for topology while avoiding source nodes dominating centrality.
    """
    by_source: dict[str, set[str]] = defaultdict(set)
    for edge in g.edges:
        if edge.type not in PROVENANCE_EDGE_TYPES:
            continue
        src = g.nodes.get(edge.src)
        dst = g.nodes.get(edge.dst)
        if src and src.type == "source" and edge.dst in ids:
            by_source[edge.src].add(edge.dst)
        elif dst and dst.type == "source" and edge.src in ids:
            by_source[edge.dst].add(edge.src)

    projected = set()
    for members in by_source.values():
        ordered = sorted(members)
        for left, right in zip(ordered, ordered[1:]):
            projected.add((left, right))
    return projected


def _build_adjacency(ids: Iterable[str], edges: Iterable[Edge]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    directed = {nid: set() for nid in ids}
    undirected = {nid: set() for nid in ids}
    for edge in edges:
        if edge.src not in directed or edge.dst not in directed:
            continue
        directed[edge.src].add(edge.dst)
        undirected[edge.src].add(edge.dst)
        undirected[edge.dst].add(edge.src)
    return directed, undirected


def _add_projection(
    directed: dict[str, set[str]],
    undirected: dict[str, set[str]],
    projected_edges: Iterable[tuple[str, str]],
) -> None:
    for left, right in projected_edges:
        if left not in directed or right not in directed:
            continue
        directed[left].add(right)
        directed[right].add(left)
        undirected[left].add(right)
        undirected[right].add(left)


def _degree(undirected: dict[str, set[str]]) -> dict[str, int]:
    return {nid: len(neighbors) for nid, neighbors in undirected.items()}


def _directed_counts(ids: Iterable[str], edges: Iterable[Edge]) -> tuple[dict[str, int], dict[str, int]]:
    in_degree = {nid: 0 for nid in ids}
    out_degree = {nid: 0 for nid in ids}
    for edge in edges:
        if edge.src not in out_degree or edge.dst not in in_degree:
            continue
        out_degree[edge.src] += 1
        in_degree[edge.dst] += 1
    return in_degree, out_degree


def _directed_edge_types(ids: Iterable[str], edges: Iterable[Edge]) -> tuple[dict[str, Counter], dict[str, Counter]]:
    in_types = {nid: Counter() for nid in ids}
    out_types = {nid: Counter() for nid in ids}
    for edge in edges:
        if edge.src in out_types and edge.dst in in_types:
            out_types[edge.src][edge.type] += 1
            in_types[edge.dst][edge.type] += 1
    return in_types, out_types


def _pagerank(
    ids: list[str],
    directed: dict[str, set[str]],
    damping: float = 0.85,
    iterations: int = 100,
    tolerance: float = 1.0e-12,
) -> dict[str, float]:
    n = len(ids)
    if n == 0:
        return {}
    score = {nid: 1.0 / n for nid in ids}
    base = (1.0 - damping) / n
    for _ in range(iterations):
        next_score = {nid: base for nid in ids}
        sink_mass = sum(score[nid] for nid in ids if not directed[nid])
        sink_share = damping * sink_mass / n
        for nid in ids:
            next_score[nid] += sink_share
        for src in ids:
            targets = directed[src]
            if not targets:
                continue
            share = damping * score[src] / len(targets)
            for dst in targets:
                next_score[dst] += share
        delta = sum(abs(next_score[nid] - score[nid]) for nid in ids)
        score = next_score
        if delta < tolerance:
            break
    return score


def _betweenness(ids: list[str], adjacency: dict[str, set[str]]) -> dict[str, float]:
    """Brandes betweenness centrality for an undirected, unweighted graph."""
    centrality = {nid: 0.0 for nid in ids}
    for source in ids:
        stack: list[str] = []
        predecessors = {nid: [] for nid in ids}
        sigma = {nid: 0.0 for nid in ids}
        sigma[source] = 1.0
        distance = {nid: -1 for nid in ids}
        distance[source] = 0
        queue = deque([source])

        while queue:
            current = queue.popleft()
            stack.append(current)
            for neighbor in adjacency[current]:
                if distance[neighbor] < 0:
                    queue.append(neighbor)
                    distance[neighbor] = distance[current] + 1
                if distance[neighbor] == distance[current] + 1:
                    sigma[neighbor] += sigma[current]
                    predecessors[neighbor].append(current)

        delta = {nid: 0.0 for nid in ids}
        while stack:
            node_id = stack.pop()
            for predecessor in predecessors[node_id]:
                if sigma[node_id]:
                    share = (sigma[predecessor] / sigma[node_id]) * (1.0 + delta[node_id])
                    delta[predecessor] += share
            if node_id != source:
                centrality[node_id] += delta[node_id]

    # Undirected paths are counted twice.
    for nid in centrality:
        centrality[nid] /= 2.0
    n = len(ids)
    if n > 2:
        scale = 2.0 / ((n - 1) * (n - 2))
        for nid in centrality:
            centrality[nid] *= scale
    return centrality


def _edge_betweenness(ids: list[str], adjacency: dict[str, set[str]]) -> dict[tuple[str, str], float]:
    """Brandes edge betweenness for undirected community splitting."""
    edge_scores: dict[tuple[str, str], float] = defaultdict(float)
    for source in ids:
        stack: list[str] = []
        predecessors = {nid: [] for nid in ids}
        sigma = {nid: 0.0 for nid in ids}
        sigma[source] = 1.0
        distance = {nid: -1 for nid in ids}
        distance[source] = 0
        queue = deque([source])

        while queue:
            current = queue.popleft()
            stack.append(current)
            for neighbor in adjacency[current]:
                if distance[neighbor] < 0:
                    queue.append(neighbor)
                    distance[neighbor] = distance[current] + 1
                if distance[neighbor] == distance[current] + 1:
                    sigma[neighbor] += sigma[current]
                    predecessors[neighbor].append(current)

        delta = {nid: 0.0 for nid in ids}
        while stack:
            node_id = stack.pop()
            for predecessor in predecessors[node_id]:
                if not sigma[node_id]:
                    continue
                contribution = (sigma[predecessor] / sigma[node_id]) * (1.0 + delta[node_id])
                edge_scores[tuple(sorted((predecessor, node_id)))] += contribution
                delta[predecessor] += contribution

    for edge_key in list(edge_scores):
        edge_scores[edge_key] /= 2.0
    return dict(edge_scores)


def _connected_components(ids: Iterable[str], adjacency: dict[str, set[str]]) -> list[list[str]]:
    remaining = set(ids)
    components: list[list[str]] = []
    while remaining:
        start = min(remaining)
        queue = deque([start])
        remaining.remove(start)
        component = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda c: (-len(c), c[0] if c else ""))


def _core_numbers(ids: list[str], adjacency: dict[str, set[str]]) -> dict[str, int]:
    remaining = set(ids)
    core = {nid: 0 for nid in ids}
    k = 0
    while remaining:
        removed_at_k = []
        changed = True
        while changed:
            changed = False
            for nid in sorted(remaining):
                degree = sum(1 for neighbor in adjacency[nid] if neighbor in remaining)
                if degree <= k:
                    removed_at_k.append(nid)
                    remaining.remove(nid)
                    changed = True
        if removed_at_k:
            for nid in removed_at_k:
                core[nid] = k
        else:
            k += 1
    return core


def _community_partition(
    ids: list[str],
    adjacency: dict[str, set[str]],
    max_communities: int = 12,
) -> dict[str, int]:
    if not ids:
        return {}
    target = min(max_communities, max(1, round(math.sqrt(len(ids)))))
    current = {nid: set(neighbors) for nid, neighbors in adjacency.items()}
    components = _connected_components(ids, current)
    max_removals = sum(len(neighbors) for neighbors in current.values()) // 2
    removals = 0

    while len(components) < target and removals < max_removals:
        splittable = [component for component in components if len(component) > 2]
        if not splittable:
            break
        largest = splittable[0]
        subgraph = {nid: current[nid] & set(largest) for nid in largest}
        edge_scores = _edge_betweenness(largest, subgraph)
        if not edge_scores:
            break
        edge_to_remove = sorted(edge_scores.items(), key=lambda item: (-item[1], item[0]))[0][0]
        a, b = edge_to_remove
        current[a].discard(b)
        current[b].discard(a)
        removals += 1
        components = _connected_components(ids, current)

    partition = {}
    for community_id, members in enumerate(components):
        for nid in members:
            partition[nid] = community_id
    return partition


def _confidence_is_weak(confidence: str | None) -> bool:
    return (confidence or "high") != "high"


def _node_record(g: Graph, node_id: str, **metrics: object) -> dict:
    node = g.nodes[node_id]
    record = {
        "id": node.id,
        "type": node.type,
        "label": node.label,
        "confidence": node.confidence,
    }
    record.update(metrics)
    return record


def _edge_record(g: Graph, edge: Edge, index: int | None = None) -> dict:
    record = {
        "src": edge.src,
        "dst": edge.dst,
        "type": edge.type,
        "source_id": edge.source_id,
        "confidence": edge.confidence,
        "excerpt": edge.excerpt,
    }
    if index is not None:
        record["index"] = index
    if edge.src in g.nodes:
        record["src_label"] = g.nodes[edge.src].label
        record["src_type"] = g.nodes[edge.src].type
    if edge.dst in g.nodes:
        record["dst_label"] = g.nodes[edge.dst].label
        record["dst_type"] = g.nodes[edge.dst].type
    return record


def _ranked_nodes(
    g: Graph,
    scores: dict[str, float],
    degree: dict[str, int],
    core: dict[str, int],
    communities: dict[str, int],
    limit: int,
    *,
    include_zero: bool = False,
) -> list[dict]:
    ranked = sorted(
        scores.items(),
        key=lambda item: (-item[1], -degree.get(item[0], 0), g.nodes[item[0]].label.lower()),
    )
    out = []
    for node_id, score in ranked:
        if not include_zero and score <= 0:
            continue
        out.append(
            _node_record(
                g,
                node_id,
                score=score,
                degree=degree.get(node_id, 0),
                core_number=core.get(node_id, 0),
                community=communities.get(node_id),
            )
        )
        if len(out) >= limit:
            break
    return out


def _provenance_coverage(g: Graph) -> dict:
    mentioned = set()
    mentioned_with_excerpt = set()
    provenance_edges = []
    for edge in g.edges:
        if edge.type not in PROVENANCE_EDGE_TYPES:
            continue
        provenance_edges.append(edge)
        if edge.src in g.nodes and g.nodes[edge.src].type != "source":
            mentioned.add(edge.src)
            if edge.excerpt:
                mentioned_with_excerpt.add(edge.src)
        if edge.dst in g.nodes and g.nodes[edge.dst].type != "source":
            mentioned.add(edge.dst)
            if edge.excerpt:
                mentioned_with_excerpt.add(edge.dst)

    non_source_nodes = [nid for nid, node in g.nodes.items() if node.type != "source"]
    missing_nodes = [nid for nid in non_source_nodes if nid not in mentioned]
    edges_with_source_id = [edge for edge in g.edges if edge.source_id]
    edges_missing_source_id = [edge for edge in g.edges if not edge.source_id]
    provenance_with_excerpt = [edge for edge in provenance_edges if edge.excerpt]

    def ratio(numerator: int, denominator: int) -> float:
        return 1.0 if denominator == 0 else numerator / denominator

    return {
        "node_coverage": ratio(len(mentioned), len(non_source_nodes)),
        "excerpt_coverage": ratio(len(provenance_with_excerpt), len(provenance_edges)),
        "edge_source_coverage": ratio(len(edges_with_source_id), len(g.edges)),
        "non_source_nodes": len(non_source_nodes),
        "nodes_with_provenance": len(mentioned),
        "nodes_with_provenance_excerpt": len(mentioned_with_excerpt),
        "missing_nodes": [_node_record(g, nid) for nid in sorted(missing_nodes)],
        "edges_total": len(g.edges),
        "edges_with_source_id": len(edges_with_source_id),
        "edges_missing_source_id": [
            _edge_record(g, edge, index)
            for index, edge in enumerate(g.edges)
            if not edge.source_id
        ],
        "provenance_edges": len(provenance_edges),
        "provenance_edges_with_excerpt": len(provenance_with_excerpt),
    }


def _proof_trail(g: Graph, node_ids: list[str], limit: int) -> list[dict]:
    out = []
    seen = set()
    for node_id in node_ids:
        if node_id in seen or node_id not in g.nodes:
            continue
        seen.add(node_id)
        provenance = []
        for source_id, excerpt in g.provenance(node_id):
            source = g.nodes.get(source_id)
            provenance.append(
                {
                    "source_id": source_id,
                    "source_label": source.label if source else source_id,
                    "excerpt": excerpt,
                }
            )
        if not provenance:
            continue
        out.append(_node_record(g, node_id, provenance=provenance))
        if len(out) >= limit:
            break
    return out


def _weak_claims(g: Graph, coverage: dict, limit: int) -> list[dict]:
    claims = []
    for node_id, node in g.nodes.items():
        if node.type == "source" or not _confidence_is_weak(node.confidence):
            continue
        claims.append({"kind": "node_confidence", **_node_record(g, node_id)})
    for index, edge in enumerate(g.edges):
        if _confidence_is_weak(edge.confidence):
            claims.append({"kind": "edge_confidence", **_edge_record(g, edge, index)})
    for node in coverage["missing_nodes"]:
        claims.append({"kind": "missing_node_provenance", **node})
    for edge in coverage["edges_missing_source_id"]:
        claims.append({"kind": "missing_edge_source_id", **edge})

    def sort_key(claim: dict) -> tuple:
        confidence = claim.get("confidence")
        return (
            CONFIDENCE_RANK.get(str(confidence), -1),
            claim.get("kind", ""),
            claim.get("id") or claim.get("src") or "",
        )

    return sorted(claims, key=sort_key)[:limit]


def _idea_flow_records(
    g: Graph,
    ids: list[str],
    in_degree: dict[str, int],
    out_degree: dict[str, int],
    in_types: dict[str, Counter],
    out_types: dict[str, Counter],
    communities: dict[str, int],
    limit: int,
    *,
    mode: str,
) -> list[dict]:
    if mode not in {"attractor", "generator"}:
        raise ValueError(f"unknown idea flow mode: {mode}")

    idea_ids = [nid for nid in ids if g.nodes[nid].type == "idea"]

    def score(node_id: str) -> int:
        if mode == "attractor":
            return in_degree.get(node_id, 0) - out_degree.get(node_id, 0)
        return out_degree.get(node_id, 0) - in_degree.get(node_id, 0)

    ranked = sorted(
        idea_ids,
        key=lambda nid: (
            -score(nid),
            -max(in_degree.get(nid, 0), out_degree.get(nid, 0)),
            g.nodes[nid].label.lower(),
        ),
    )

    records = []
    for node_id in ranked:
        if mode == "attractor":
            if in_degree.get(node_id, 0) < 1 or score(node_id) <= 0:
                continue
            prompt = (
                "Is this a durable principle, an unresolved sink, or an over-compressed label? "
                "Write one next action."
            )
        else:
            if out_degree.get(node_id, 0) < 1 or score(node_id) <= 0:
                continue
            prompt = (
                "Which branch deserves leg work next? Choose one edge to operationalize, "
                "verify, or prune."
            )

        records.append(
            _node_record(
                g,
                node_id,
                score=float(score(node_id)),
                in_degree=in_degree.get(node_id, 0),
                out_degree=out_degree.get(node_id, 0),
                flow_balance=score(node_id),
                inbound_edge_types=dict(in_types.get(node_id, Counter())),
                outbound_edge_types=dict(out_types.get(node_id, Counter())),
                community=communities.get(node_id),
                prompt=prompt,
            )
        )
        if len(records) >= limit:
            break
    return records


def _weak_claim_queue(claims: list[dict], limit: int) -> list[dict]:
    queue = []
    for claim in claims[:limit]:
        prompt = "Choose: verify, downgrade, convert to question, ignore for now."
        if claim.get("kind") == "missing_node_provenance":
            prompt = "Find source evidence or keep this out of durable memory."
        elif claim.get("kind") == "missing_edge_source_id":
            prompt = "Attach a source id or remove this edge from the durable graph."
        elif claim.get("kind") == "edge_confidence":
            prompt = "Inspect this relationship: verify it, downgrade it, or turn it into an open question."
        queue.append(
            {
                **claim,
                "prompt": prompt,
                "review_options": ["verify", "downgrade", "convert_to_question", "ignore_for_now"],
            }
        )
    return queue


def _community_records(
    g: Graph,
    communities: dict[str, int],
    pagerank: dict[str, float],
    degree: dict[str, int],
    core: dict[str, int],
) -> list[dict]:
    grouped: dict[int, list[str]] = defaultdict(list)
    for node_id, community_id in communities.items():
        grouped[community_id].append(node_id)

    records = []
    for community_id, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        members = sorted(members)
        top_members = sorted(
            members,
            key=lambda nid: (-pagerank.get(nid, 0.0), -degree.get(nid, 0), g.nodes[nid].label.lower()),
        )[:12]
        records.append(
            {
                "id": community_id,
                "size": len(members),
                "types": dict(Counter(g.nodes[nid].type for nid in members)),
                "members": members,
                "top_members": [
                    _node_record(
                        g,
                        nid,
                        score=pagerank.get(nid, 0.0),
                        degree=degree.get(nid, 0),
                        core_number=core.get(nid, 0),
                    )
                    for nid in top_members
                ],
            }
        )
    return records


def build_memory_audit(g: Graph, *, limit: int = 25, max_communities: int = 12) -> dict:
    ids = _semantic_ids(g)
    id_set = set(ids)
    semantic_edges = _semantic_edges(g, id_set)
    projection_edges = _source_projection_edges(g, id_set)
    directed, undirected = _build_adjacency(ids, semantic_edges)
    _add_projection(directed, undirected, projection_edges)
    degree = _degree(undirected)
    pagerank = _pagerank(ids, directed)
    betweenness = _betweenness(ids, undirected)
    core = _core_numbers(ids, undirected)
    communities = _community_partition(ids, undirected, max_communities=max_communities)
    coverage = _provenance_coverage(g)
    semantic_in_degree, semantic_out_degree = _directed_counts(ids, semantic_edges)
    flow_edges = _idea_flow_edges(semantic_edges)
    flow_in_degree, flow_out_degree = _directed_counts(ids, flow_edges)
    flow_in_types, flow_out_types = _directed_edge_types(ids, flow_edges)

    important = _ranked_nodes(g, pagerank, degree, core, communities, limit, include_zero=True)
    bridges = _ranked_nodes(g, betweenness, degree, core, communities, limit)
    structural_core = _ranked_nodes(
        g,
        {nid: float(core.get(nid, 0)) for nid in ids},
        degree,
        core,
        communities,
        limit,
        include_zero=True,
    )
    proof_ids = [record["id"] for record in important] + [record["id"] for record in bridges]
    weak_claims = _weak_claims(g, coverage, limit)
    idea_attractors = _idea_flow_records(
        g,
        ids,
        flow_in_degree,
        flow_out_degree,
        flow_in_types,
        flow_out_types,
        communities,
        limit,
        mode="attractor",
    )
    idea_generators = _idea_flow_records(
        g,
        ids,
        flow_in_degree,
        flow_out_degree,
        flow_in_types,
        flow_out_types,
        communities,
        limit,
        mode="generator",
    )

    return {
        "schema_version": "memory-audit/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "nodes": len(g.nodes),
            "edges": len(g.edges),
            "semantic_nodes": len(ids),
            "semantic_edges": len(semantic_edges),
            "source_projection_edges": len(projection_edges),
            "audit_edges": len({tuple(sorted((edge.src, edge.dst))) for edge in semantic_edges} | projection_edges),
            "source_nodes": sum(1 for node in g.nodes.values() if node.type == "source"),
            "semantic_components": len(_connected_components(ids, undirected)) if ids else 0,
            "communities": len(set(communities.values())),
            "max_core_number": max(core.values()) if core else 0,
        },
        "counts": {
            "node_types": dict(Counter(node.type for node in g.nodes.values())),
            "edge_types": dict(Counter(edge.type for edge in g.edges)),
            "confidence": {
                "nodes": dict(Counter(node.confidence for node in g.nodes.values())),
                "edges": dict(Counter(edge.confidence for edge in g.edges)),
            },
        },
        "ranked": {
            "important_concepts": important,
            "bridge_ideas": bridges,
            "idea_attractors": idea_attractors,
            "idea_generators": idea_generators,
            "structural_core": structural_core,
            "weak_claims": weak_claims,
            "weak_claim_queue": _weak_claim_queue(weak_claims, limit),
            "proof_trail": _proof_trail(g, proof_ids, limit),
        },
        "centrality": {
            "pagerank": important,
            "betweenness": bridges,
            "core_number": structural_core,
            "semantic_in_degree": _ranked_nodes(
                g,
                {nid: float(semantic_in_degree.get(nid, 0)) for nid in ids},
                degree,
                core,
                communities,
                limit,
            ),
            "semantic_out_degree": _ranked_nodes(
                g,
                {nid: float(semantic_out_degree.get(nid, 0)) for nid in ids},
                degree,
                core,
                communities,
                limit,
            ),
        },
        "directed_flow": {
            "note": (
                "Directed flow uses semantic edges only. Provenance/source projection and "
                "back-reference edges are excluded so attractors and generators reflect "
                "relationship direction, not citation volume."
            ),
            "idea_attractors": idea_attractors,
            "idea_generators": idea_generators,
        },
        "legwork_queue": {
            "idea_attractors": idea_attractors,
            "idea_generators": idea_generators,
            "weak_claims": _weak_claim_queue(weak_claims, limit),
        },
        "communities": _community_records(g, communities, pagerank, degree, core),
        "low_confidence_edges": [
            _edge_record(g, edge, index)
            for index, edge in enumerate(g.edges)
            if _confidence_is_weak(edge.confidence)
        ],
        "provenance_coverage": coverage,
    }


def _graph_payload(g: Graph) -> dict:
    return {
        "nodes": {node_id: asdict(node) for node_id, node in g.nodes.items()},
        "edges": [asdict(edge) for edge in g.edges],
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Memory Audit</title>
<style>
  :root {
    --bg: #f6f7f9;
    --fg: #17202a;
    --muted: #667085;
    --line: #d7dde5;
    --panel: #ffffff;
    --accent: #0f766e;
    --blue: #2563eb;
    --amber: #a16207;
    --red: #b42318;
    --ink: #111827;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; background: var(--bg); color: var(--fg);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  body { overflow: hidden; }
  header { height: 56px; padding: 0 18px; display: flex; align-items: center; gap: 14px;
    border-bottom: 1px solid var(--line); background: #fff; }
  header h1 { margin: 0; font-size: 18px; letter-spacing: 0; }
  header .meta { color: var(--muted); font-size: 13px; }
  main { height: calc(100vh - 56px); display: grid; grid-template-columns: minmax(360px, 42%) 1fr; }
  #panels { overflow: auto; padding: 14px; display: grid; gap: 12px; align-content: start; }
  #map { min-width: 0; border-left: 1px solid var(--line); display: grid; grid-template-rows: auto 1fr;
    background: #eef2f6; }
  .metric-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
  .metric, .panel, #details { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
  .metric { padding: 10px 12px; min-width: 0; }
  .metric strong { display: block; font-size: 18px; line-height: 1.1; }
  .metric span { display: block; color: var(--muted); font-size: 12px; margin-top: 3px; overflow-wrap: anywhere; }
  .panel h2 { margin: 0; padding: 12px 12px 4px; font-size: 14px; color: var(--ink); }
  .panel ol, .panel ul { list-style: none; margin: 0; padding: 0 8px 8px; }
  .item { width: 100%; border: 0; background: transparent; text-align: left; padding: 8px;
    border-radius: 6px; cursor: pointer; display: grid; gap: 3px; color: var(--fg); }
  .item:hover, .item.selected { background: #edf7f5; }
  .item-title { font-size: 13px; font-weight: 700; overflow-wrap: anywhere; }
  .item-meta { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
  .score { color: var(--accent); font-variant-numeric: tabular-nums; }
  .weak .score { color: var(--red); }
  .toolbar { min-height: 48px; padding: 10px 12px; display: flex; align-items: center; justify-content: space-between;
    gap: 12px; border-bottom: 1px solid var(--line); background: #fff; }
  .toolbar strong { font-size: 14px; }
  .toolbar span { color: var(--muted); font-size: 12px; }
  #stage { position: relative; min-height: 0; }
  svg { width: 100%; height: 100%; display: block; }
  .edge { stroke: #96a1b2; stroke-width: 1.2; stroke-opacity: 0.46; }
  .edge.weak { stroke: var(--red); stroke-dasharray: 5 4; stroke-opacity: 0.7; }
  .node circle { stroke: #fff; stroke-width: 1.5; }
  .node text { fill: #1f2937; font-size: 11px; paint-order: stroke; stroke: #f8fafc; stroke-width: 4px;
    stroke-linecap: round; stroke-linejoin: round; pointer-events: none; }
  .node.dim { opacity: 0.35; }
  .node.selected circle { stroke: var(--accent); stroke-width: 4; }
  #details { position: absolute; left: 12px; bottom: 12px; width: min(460px, calc(100% - 24px));
    max-height: 40%; overflow: auto; padding: 12px; box-shadow: 0 16px 44px rgba(17,24,39,.14); }
  #details h3 { margin: 0 0 4px; font-size: 15px; }
  #details .body, #details li { font-size: 12px; line-height: 1.45; }
  #details .body { margin: 8px 0; }
  #details ul { margin: 6px 0 0; padding-left: 18px; }
  code { color: var(--muted); overflow-wrap: anywhere; }
  .pill { display: inline-flex; align-items: center; min-height: 18px; padding: 1px 6px; border-radius: 999px;
    background: #eef2f6; color: var(--muted); font-size: 11px; }
  .pill.low { color: var(--red); background: #fee4e2; }
  .pill.medium { color: var(--amber); background: #fef0c7; }
  @media (max-width: 900px) {
    body { overflow: auto; }
    main { height: auto; display: block; }
    #panels { overflow: visible; }
    #map { height: 720px; border-left: 0; border-top: 1px solid var(--line); }
    .metric-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
</style>
<body>
<header>
  <h1>Memory Audit</h1>
  <div class="meta" id="generated"></div>
</header>
<main>
  <section id="panels" aria-label="Ranked audit panels"></section>
  <section id="map" aria-label="Graph canvas">
    <div class="toolbar">
      <strong>Graph Canvas</strong>
      <span>Important and bridge nodes are labeled first. Select a panel row or node.</span>
    </div>
    <div id="stage">
      <svg id="graph" viewBox="0 0 1200 760" role="img" aria-label="Memory audit graph"></svg>
      <aside id="details"></aside>
    </div>
  </section>
</main>
<script>
const AUDIT = __AUDIT_JSON__;
const GRAPH = __GRAPH_JSON__;
const nodes = Object.values(GRAPH.nodes || {});
const edges = GRAPH.edges || [];
const nodeById = new Map(nodes.map(n => [n.id, n]));
const importantIds = new Set((AUDIT.ranked.important_concepts || []).slice(0, 10).map(n => n.id));
const bridgeIds = new Set((AUDIT.ranked.bridge_ideas || []).slice(0, 10).map(n => n.id));
const selected = { id: null };
const colors = {
  person: "#dc2626", topic: "#2563eb", idea: "#0f766e", project: "#7c3aed",
  goal: "#16a34a", question: "#a16207", decision: "#0891b2", reference: "#c026d3",
  source: "#64748b"
};

function esc(value) {
  return String(value || "").replace(/[&<>"]/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"
  }[c]));
}

function fmt(value, digits = 3) {
  if (typeof value !== "number") return "";
  return value.toFixed(digits);
}

function confidencePill(value) {
  return `<span class="pill ${esc(value || "")}">${esc(value || "?")}</span>`;
}

function nodeLine(record) {
  const score = typeof record.score === "number" ? `<span class="score">${fmt(record.score)}</span> ` : "";
  return `${score}${esc(record.type)} · <code>${esc(record.id)}</code> ${confidencePill(record.confidence)}`;
}

function claimTitle(claim) {
  if (claim.id) return claim.label || claim.id;
  return `${claim.src || "?"} -> ${claim.dst || "?"}`;
}

function claimMeta(claim) {
  if (claim.kind === "edge_confidence" || claim.kind === "missing_edge_source_id") {
    return `${claim.kind} · ${claim.type || "edge"} · ${claim.confidence || "unknown"}`;
  }
  return `${claim.kind} · ${claim.type || "node"} · ${claim.confidence || "unknown"}`;
}

function renderPanels() {
  document.getElementById("generated").textContent =
    `${AUDIT.stats.nodes} nodes · ${AUDIT.stats.edges} edges · generated ${AUDIT.generated_at}`;
  const coverage = AUDIT.provenance_coverage || {};
  const panels = document.getElementById("panels");
  panels.innerHTML = `
    <div class="metric-row">
      <div class="metric"><strong>${AUDIT.stats.semantic_nodes}</strong><span>semantic nodes</span></div>
      <div class="metric"><strong>${AUDIT.stats.communities}</strong><span>communities</span></div>
      <div class="metric"><strong>${AUDIT.stats.max_core_number}</strong><span>max k-core</span></div>
      <div class="metric"><strong>${Math.round((coverage.node_coverage || 0) * 100)}%</strong><span>provenance coverage</span></div>
    </div>
    ${rankedPanel("Important Concepts", AUDIT.ranked.important_concepts || [], "PageRank over semantic edges")}
    ${rankedPanel("Bridge Ideas", AUDIT.ranked.bridge_ideas || [], "Betweenness centrality")}
    ${flowPanel("Idea Attractors", AUDIT.ranked.idea_attractors || [], "High semantic in-degree, low out-degree")}
    ${flowPanel("Idea Generators", AUDIT.ranked.idea_generators || [], "High semantic out-degree, low in-degree")}
    ${weakPanel("Weak Claim Queue", AUDIT.ranked.weak_claim_queue || AUDIT.ranked.weak_claims || [])}
    ${proofPanel("Proof Trail", AUDIT.ranked.proof_trail || [])}
  `;
  panels.querySelectorAll("[data-node-id]").forEach(el => {
    el.addEventListener("click", () => selectNode(el.dataset.nodeId));
  });
}

function rankedPanel(title, records, subtitle) {
  const rows = records.slice(0, 12).map(record => `
    <li><button class="item" data-node-id="${esc(record.id)}">
      <span class="item-title">${esc(record.label || record.id)}</span>
      <span class="item-meta">${nodeLine(record)} · degree ${record.degree || 0} · core ${record.core_number || 0}</span>
    </button></li>`).join("");
  return `<section class="panel"><h2>${esc(title)}</h2><ol>${rows || `<li class="item-meta" style="padding:8px">None</li>`}</ol></section>`;
}

function flowPanel(title, records, subtitle) {
  const rows = records.slice(0, 12).map(record => `
    <li><button class="item" data-node-id="${esc(record.id)}">
      <span class="item-title">${esc(record.label || record.id)}</span>
      <span class="item-meta">${esc(subtitle)} · in ${record.in_degree || 0} · out ${record.out_degree || 0} · balance ${record.flow_balance || 0}</span>
      <span class="item-meta">${esc(record.prompt || "")}</span>
    </button></li>`).join("");
  return `<section class="panel"><h2>${esc(title)}</h2><ol>${rows || `<li class="item-meta" style="padding:8px">None</li>`}</ol></section>`;
}

function weakPanel(title, claims) {
  const rows = claims.slice(0, 14).map(claim => {
    const nodeId = claim.id || claim.src || claim.dst || "";
    return `<li><button class="item weak" data-node-id="${esc(nodeId)}">
      <span class="item-title">${esc(claimTitle(claim))}</span>
      <span class="item-meta"><span class="score">${esc(claim.confidence || "missing")}</span> ${esc(claimMeta(claim))}</span>
      <span class="item-meta">${esc(claim.prompt || "Choose a review action before this becomes durable memory.")}</span>
    </button></li>`;
  }).join("");
  return `<section class="panel"><h2>${esc(title)}</h2><ul>${rows || `<li class="item-meta" style="padding:8px">No weak claims found</li>`}</ul></section>`;
}

function proofPanel(title, records) {
  const rows = records.slice(0, 10).map(record => {
    const first = (record.provenance || [])[0] || {};
    return `<li><button class="item" data-node-id="${esc(record.id)}">
      <span class="item-title">${esc(record.label || record.id)}</span>
      <span class="item-meta">${esc(first.source_id || "no source")} ${first.excerpt ? "- " + esc(first.excerpt).slice(0, 120) : ""}</span>
    </button></li>`;
  }).join("");
  return `<section class="panel"><h2>${esc(title)}</h2><ul>${rows || `<li class="item-meta" style="padding:8px">No proof trails found</li>`}</ul></section>`;
}

function layoutNodes() {
  const communities = new Map();
  for (const community of AUDIT.communities || []) {
    for (const id of community.members || []) communities.set(id, community.id);
  }
  const cx = 600, cy = 380;
  const semantic = nodes.filter(n => n.type !== "source");
  const sources = nodes.filter(n => n.type === "source");
  semantic.forEach((node, index) => {
    const community = communities.get(node.id) || 0;
    const ring = 120 + (community % 5) * 72;
    const angle = (Math.PI * 2 * index / Math.max(1, semantic.length)) + community * 0.63;
    node.x = cx + Math.cos(angle) * ring;
    node.y = cy + Math.sin(angle) * ring;
  });
  sources.forEach((node, index) => {
    const angle = Math.PI * 2 * index / Math.max(1, sources.length);
    node.x = cx + Math.cos(angle) * 340;
    node.y = cy + Math.sin(angle) * 260;
  });
}

function make(tag, attrs, parent) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs || {})) el.setAttribute(key, value);
  parent.appendChild(el);
  return el;
}

function renderGraph() {
  layoutNodes();
  const svg = document.getElementById("graph");
  svg.innerHTML = "";
  const root = make("g", {}, svg);
  for (const edge of edges) {
    const src = nodeById.get(edge.src), dst = nodeById.get(edge.dst);
    if (!src || !dst) continue;
    make("line", {
      class: `edge ${(edge.confidence || "high") === "high" ? "" : "weak"}`,
      x1: src.x, y1: src.y, x2: dst.x, y2: dst.y
    }, root);
  }
  for (const node of nodes) {
    const group = make("g", { class: "node", transform: `translate(${node.x},${node.y})`, "data-id": node.id }, root);
    const radius = importantIds.has(node.id) ? 11 : bridgeIds.has(node.id) ? 10 : node.type === "source" ? 5 : 7;
    make("circle", { r: radius, fill: colors[node.type] || "#475569" }, group);
    if (importantIds.has(node.id) || bridgeIds.has(node.id)) {
      make("text", { x: radius + 5, y: 4 }, group).textContent = node.label || node.id;
    }
    group.addEventListener("click", ev => { ev.stopPropagation(); selectNode(node.id); });
  }
  svg.addEventListener("click", () => selectNode(null));
}

function selectNode(id) {
  selected.id = id;
  document.querySelectorAll("[data-node-id]").forEach(el => el.classList.toggle("selected", el.dataset.nodeId === id));
  document.querySelectorAll(".node").forEach(el => {
    const isSelected = id && el.dataset.id === id;
    el.classList.toggle("selected", isSelected);
    el.classList.toggle("dim", Boolean(id) && !isSelected);
  });
  renderDetails(id);
}

function renderDetails(id) {
  const details = document.getElementById("details");
  if (!id || !nodeById.has(id)) {
    details.innerHTML = `<h3>Select a memory</h3><div class="body">Ranked panels are the primary audit view. The canvas is for orientation.</div>`;
    return;
  }
  const node = nodeById.get(id);
  const rel = edges.filter(e => e.src === id || e.dst === id);
  const proof = rel.filter(e => e.type === "MENTIONED_IN" || e.type === "MADE_AT");
  details.innerHTML = `
    <h3>${esc(node.label || node.id)}</h3>
    <div class="item-meta">${esc(node.type)} · <code>${esc(node.id)}</code> ${confidencePill(node.confidence)}</div>
    ${node.body ? `<div class="body">${esc(node.body)}</div>` : ""}
    <div class="item-meta">Proof trail</div>
    <ul>${proof.map(e => `<li><code>${esc(e.src === id ? e.dst : e.src)}</code>${e.excerpt ? `: ${esc(e.excerpt)}` : ""}</li>`).join("") || "<li>No provenance edge found.</li>"}</ul>
  `;
}

renderPanels();
renderGraph();
renderDetails(null);
</script>
</body>
</html>
"""


def render_memory_audit_html(g: Graph, analytics: dict, out_path: Path) -> Path:
    audit_json = json.dumps(analytics, ensure_ascii=False)
    graph_json = json.dumps(_graph_payload(g), ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__AUDIT_JSON__", audit_json.replace("</script", "<\\/script"))
    html = html.replace("__GRAPH_JSON__", graph_json.replace("</script", "<\\/script"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def _write_json(data: dict, out: str) -> Path | None:
    if out == "-":
        print(json.dumps(data, indent=2, sort_keys=True))
        return None
    out_path = Path(out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def run_audit(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mykg audit")
    parser.add_argument("--graph", default=None, help="Graph JSON path. Defaults to MYGRAPH_PATH or local graph.")
    parser.add_argument("--out", default="analytics.json", help="Analytics JSON path, or '-' for stdout.")
    parser.add_argument("--html", default=None, help="Optional standalone Memory Audit HTML path.")
    parser.add_argument("--max-items", type=int, default=25, help="Ranked records per panel.")
    parser.add_argument("--max-communities", type=int, default=12, help="Maximum communities to derive.")
    parsed = parser.parse_args(args)

    g = Graph.load(parsed.graph)
    analytics = build_memory_audit(g, limit=parsed.max_items, max_communities=parsed.max_communities)
    written_json = _write_json(analytics, parsed.out)
    if written_json:
        print(f"audit: wrote {written_json}")
    if parsed.html:
        html_path = Path(parsed.html).expanduser().resolve()
        render_memory_audit_html(g, analytics, html_path)
        print(f"audit: wrote {html_path}")
    coverage = analytics["provenance_coverage"]
    status_stream = sys.stderr if parsed.out == "-" else sys.stdout
    print(
        "audit: "
        f"{analytics['stats']['semantic_nodes']} semantic nodes, "
        f"{analytics['stats']['communities']} communities, "
        f"{round(coverage['node_coverage'] * 100)}% provenance coverage",
        file=status_stream,
    )
    return 0


if __name__ == "__main__":
    sys.exit(run_audit(sys.argv[1:]))
