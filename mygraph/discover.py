"""
discover.py - second-order network analytics and derived-edge proposals.

Usage:
  mykg discover
  mykg discover --out discovery.json --candidates discovery.candidates.json

Where `mykg audit` ranks what already exists, `mykg discover` infers what the
graph implies but does not yet say. It runs seven read-only analyses:

  staleness_radar     important nodes whose evidence has gone cold
  co_mentions         pairs that recur across sources with no direct edge
  serves_candidates   ideas/decisions structurally close to a goal they
                      do not yet SERVE
  related_candidates  Adamic-Adar link prediction over the semantic graph
  question_debt       open questions with no answering decision or evidence
  corroboration       claims that hang on a single source
  bridges             cross-community connectors after removing hub "spines"
  tensions            nodes that are both supported and challenged, and
                      conflicts between contributions to the same goal

Every result is a PROPOSAL. Discover never mutates the graph: derived edges
(CO_MENTIONED_WITH, SERVES_CANDIDATE, RELATES_TO, BRIDGES, TENSION_WITH) are
written to a candidates file for human review — AI proposes, provenance
verifies, the owner promotes.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    from .mygraph import Edge, Graph
    from .memory_audit import (
        PROVENANCE_EDGE_TYPES,
        _add_projection,
        _betweenness,
        _build_adjacency,
        _community_partition,
        _pagerank,
        _semantic_edges,
        _semantic_ids,
        _source_projection_edges,
    )
except ImportError:  # direct script execution: python mygraph/discover.py
    from mygraph import Edge, Graph
    from memory_audit import (
        PROVENANCE_EDGE_TYPES,
        _add_projection,
        _betweenness,
        _build_adjacency,
        _community_partition,
        _pagerank,
        _semantic_edges,
        _semantic_ids,
        _source_projection_edges,
    )

SCHEMA_VERSION = 1

# Edge types that express goal contribution, used for serves-gap detection.
GOAL_EDGE_TYPES = {"SERVES", "HAS_IDEA", "ABOUT", "INVOLVES"}


# ---------- shared scaffolding -------------------------------------------------

def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _node_sources(g: Graph) -> dict[str, set[str]]:
    """Distinct provenance sources per non-source node."""
    sources: dict[str, set[str]] = defaultdict(set)
    for edge in g.edges:
        if edge.type not in PROVENANCE_EDGE_TYPES:
            continue
        src = g.nodes.get(edge.src)
        dst = g.nodes.get(edge.dst)
        if src and dst and src.type != "source" and dst.type == "source":
            sources[edge.src].add(edge.dst)
        elif src and dst and src.type == "source" and dst.type != "source":
            sources[edge.dst].add(edge.src)
    return sources


def _excerpt_for(g: Graph, node_id: str, source_id: str) -> str:
    for edge in g.edges:
        if edge.type not in PROVENANCE_EDGE_TYPES or not edge.excerpt:
            continue
        if {edge.src, edge.dst} == {node_id, source_id}:
            return edge.excerpt
    return ""


def _label(g: Graph, node_id: str) -> str:
    node = g.nodes.get(node_id)
    return node.label if node else node_id


def _proposal(g: Graph, src: str, dst: str, type_: str, score: float,
              rationale: str, evidence: list[str]) -> dict:
    return {
        "src": src,
        "dst": dst,
        "type": type_,
        "score": round(score, 6),
        "rationale": rationale,
        "evidence_sources": sorted(evidence),
        "src_label": _label(g, src),
        "dst_label": _label(g, dst),
        "status": "proposed",
    }


class _Workspace:
    """Semantic projection shared by all analyses, computed once."""

    def __init__(self, g: Graph):
        self.g = g
        self.ids = _semantic_ids(g)
        id_set = set(self.ids)
        self.semantic_edges = _semantic_edges(g, id_set)
        self.directed, self.undirected = _build_adjacency(self.ids, self.semantic_edges)
        _add_projection(self.directed, self.undirected,
                        _source_projection_edges(g, id_set))
        self.pagerank = _pagerank(self.ids, self.directed)
        self.betweenness = _betweenness(self.ids, self.undirected)
        self.node_sources = _node_sources(g)
        # direct semantic adjacency (no source projection), for "no existing
        # edge" checks when proposing new links
        self.direct_links: set[frozenset[str]] = {
            frozenset((e.src, e.dst)) for e in self.semantic_edges
        }


# ---------- 1. staleness radar -------------------------------------------------

def staleness_radar(ws: _Workspace, stale_days: int, limit: int) -> dict:
    """Important nodes whose evidence trail has gone cold.

    Recency is the newest `last_seen`/`created_at` on any incident edge (or the
    node's own `created_at`). The clock reference is the newest timestamp in
    the whole graph, so results are deterministic for a committed graph file.
    """
    g = ws.g
    latest: datetime | None = None
    recency: dict[str, datetime] = {}
    for node_id in ws.ids:
        ts = _parse_ts(g.nodes[node_id].created_at)
        if ts:
            recency[node_id] = ts
            latest = max(latest, ts) if latest else ts
    for edge in g.edges:
        ts = _parse_ts(edge.last_seen) or _parse_ts(edge.created_at)
        if not ts:
            continue
        latest = max(latest, ts) if latest else ts
        for endpoint in (edge.src, edge.dst):
            if endpoint in recency:
                recency[endpoint] = max(recency[endpoint], ts)
            elif endpoint in g.nodes and g.nodes[endpoint].type != "source":
                recency[endpoint] = ts

    if not latest:
        return {"reference_time": None, "stale_days_threshold": stale_days, "stale": []}

    max_rank = max(ws.pagerank.values()) or 1.0
    records = []
    for node_id, seen in recency.items():
        days = (latest - seen).total_seconds() / 86400.0
        if days < stale_days:
            continue
        importance = ws.pagerank.get(node_id, 0.0) / max_rank
        node = g.nodes[node_id]
        records.append({
            "id": node_id,
            "type": node.type,
            "label": node.label,
            "days_stale": round(days, 1),
            "importance": round(importance, 4),
            "staleness_score": round(importance * days, 4),
            "flag": "STALE",
        })
    records.sort(key=lambda r: (-r["staleness_score"], r["id"]))
    return {
        "reference_time": latest.isoformat(),
        "stale_days_threshold": stale_days,
        "stale": records[:limit],
    }


# ---------- 2. co-mention inference --------------------------------------------

def co_mention_candidates(ws: _Workspace, min_sources: int, limit: int) -> list[dict]:
    """Pairs mentioned together in >= min_sources distinct sources but never
    directly linked. Multi-source co-occurrence is stronger evidence than
    adjacency inside a single conversation."""
    g = ws.g
    by_source: dict[str, set[str]] = defaultdict(set)
    for node_id, sources in ws.node_sources.items():
        for source_id in sources:
            by_source[source_id].add(node_id)

    pair_sources: dict[frozenset[str], set[str]] = defaultdict(set)
    for source_id, members in by_source.items():
        ordered = sorted(members)
        for i, left in enumerate(ordered):
            for right in ordered[i + 1:]:
                pair_sources[frozenset((left, right))].add(source_id)

    proposals = []
    for pair, sources in pair_sources.items():
        if len(sources) < min_sources or pair in ws.direct_links:
            continue
        left, right = sorted(pair)
        proposals.append(_proposal(
            ws.g, left, right, "CO_MENTIONED_WITH",
            score=float(len(sources)),
            rationale=(
                f"co-mentioned in {len(sources)} distinct sources "
                "with no direct edge"
            ),
            evidence=list(sources),
        ))
    proposals.sort(key=lambda p: (-p["score"], p["src"], p["dst"]))
    return proposals[:limit]


# ---------- 3+4. link prediction (serves gaps + related pairs) ------------------

def _adamic_adar(ws: _Workspace, a: str, b: str) -> tuple[float, list[str]]:
    shared = ws.undirected[a] & ws.undirected[b]
    score = 0.0
    witnesses = []
    for z in shared:
        degree = len(ws.undirected[z])
        if degree > 1:
            score += 1.0 / math.log(degree)
            witnesses.append(z)
    return score, sorted(witnesses)


def _has_directed_path(ws: _Workspace, start: str, target: str,
                       edge_types: set[str]) -> bool:
    allowed: dict[str, set[str]] = defaultdict(set)
    for edge in ws.semantic_edges:
        if edge.type in edge_types:
            allowed[edge.src].add(edge.dst)
    frontier, seen = [start], {start}
    while frontier:
        current = frontier.pop()
        if current == target:
            return True
        for nxt in allowed[current]:
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return False


def serves_candidates(ws: _Workspace, limit: int) -> list[dict]:
    """Ideas/decisions/projects structurally entangled with a goal they have
    no contribution path to. Surfaces the work the graph cannot yet explain."""
    g = ws.g
    goals = [nid for nid in ws.ids if g.nodes[nid].type == "goal"]
    contributors = [
        nid for nid in ws.ids
        if g.nodes[nid].type in {"idea", "decision", "project"}
    ]
    proposals = []
    for goal in goals:
        for node_id in contributors:
            if frozenset((node_id, goal)) in ws.direct_links:
                continue
            score, witnesses = _adamic_adar(ws, node_id, goal)
            if score <= 0 or _has_directed_path(ws, node_id, goal, GOAL_EDGE_TYPES):
                continue
            proposals.append(_proposal(
                g, node_id, goal, "SERVES_CANDIDATE",
                score=score,
                rationale=(
                    f"shares {len(witnesses)} neighbors with the goal "
                    "but has no contribution path to it"
                ),
                evidence=witnesses,
            ))
    proposals.sort(key=lambda p: (-p["score"], p["src"], p["dst"]))
    return proposals[:limit]


def related_candidates(ws: _Workspace, limit: int) -> list[dict]:
    """Classic Adamic-Adar link prediction over the semantic projection:
    non-adjacent pairs whose neighborhoods strongly overlap."""
    g = ws.g
    proposals = []
    for i, a in enumerate(ws.ids):
        for b in ws.ids[i + 1:]:
            pair = frozenset((a, b))
            if pair in ws.direct_links:
                continue
            score, witnesses = _adamic_adar(ws, a, b)
            if score < 1.0 or len(witnesses) < 2:
                continue
            proposals.append(_proposal(
                g, a, b, "RELATES_TO",
                score=score,
                rationale=f"Adamic-Adar {round(score, 3)} via {len(witnesses)} shared neighbors",
                evidence=witnesses,
            ))
    proposals.sort(key=lambda p: (-p["score"], p["src"], p["dst"]))
    return proposals[:limit]


# ---------- 5. question debt ----------------------------------------------------

def question_debt(ws: _Workspace, limit: int) -> dict:
    """Open questions ranked by how central, old, and evidence-free they are.

    A question counts as answered when a decision points at it via ABOUT; those
    detected pairs are reported as ANSWERS edges."""
    g = ws.g
    answered_by: dict[str, list[str]] = defaultdict(list)
    evidence_count: dict[str, int] = defaultdict(int)
    for edge in ws.semantic_edges:
        if edge.type == "ABOUT" and g.nodes[edge.src].type == "decision" \
                and g.nodes[edge.dst].type == "question":
            answered_by[edge.dst].append(edge.src)
        if edge.type == "SUPPORTED_BY" and g.nodes[edge.src].type == "question":
            evidence_count[edge.src] += 1

    latest = None
    for node_id in ws.ids:
        ts = _parse_ts(g.nodes[node_id].created_at)
        if ts:
            latest = max(latest, ts) if latest else ts

    max_rank = max(ws.pagerank.values()) or 1.0
    open_questions, answers = [], []
    for node_id in ws.ids:
        node = g.nodes[node_id]
        if node.type != "question":
            continue
        deciders = sorted(answered_by.get(node_id, []))
        for decision_id in deciders:
            answers.append({"src": decision_id, "dst": node_id, "type": "ANSWERS"})
        if deciders:
            continue
        created = _parse_ts(node.created_at)
        age_days = (latest - created).total_seconds() / 86400.0 if latest and created else 0.0
        weight = ws.pagerank.get(node_id, 0.0) / max_rank
        open_questions.append({
            "id": node_id,
            "label": node.label,
            "age_days": round(age_days, 1),
            "evidence_edges": evidence_count.get(node_id, 0),
            "centrality": round(weight, 4),
            "debt_score": round(weight * (1.0 + age_days), 4),
            "flag": "UNANSWERED",
        })
    open_questions.sort(key=lambda r: (-r["debt_score"], r["id"]))
    answers.sort(key=lambda r: (r["src"], r["dst"]))
    return {"open": open_questions[:limit], "answers_detected": answers}


# ---------- 6. corroboration ----------------------------------------------------

def corroboration(ws: _Workspace, limit: int) -> dict:
    """How many independent sources back each claim. Single-source memories are
    one bad transcript away from being wrong."""
    g = ws.g
    max_rank = max(ws.pagerank.values()) or 1.0
    single, distribution = [], defaultdict(int)
    for node_id in ws.ids:
        count = len(ws.node_sources.get(node_id, set()))
        distribution[count] += 1
        if count == 1:
            source_id = next(iter(ws.node_sources[node_id]))
            single.append({
                "id": node_id,
                "type": g.nodes[node_id].type,
                "label": g.nodes[node_id].label,
                "source": source_id,
                "excerpt": _excerpt_for(g, node_id, source_id),
                "centrality": round(ws.pagerank.get(node_id, 0.0) / max_rank, 4),
                "flag": "SINGLE_SOURCE",
            })
    single.sort(key=lambda r: (-r["centrality"], r["id"]))
    return {
        "source_count_distribution": dict(sorted(distribution.items())),
        "single_source": single[:limit],
    }


# ---------- 7. de-spined bridges ------------------------------------------------

def despined_bridges(ws: _Workspace, limit: int, max_communities: int = 12) -> dict:
    """Bridges that remain once dominant hubs are removed.

    Owner/project hub nodes absorb most betweenness and mask which concepts
    actually connect domains. Remove any node holding > 2x the median nonzero
    betweenness AND ranked in the top two, then recompute on the remainder."""
    ranked = sorted(ws.betweenness.items(), key=lambda kv: (-kv[1], kv[0]))
    nonzero = sorted(v for _, v in ranked if v > 0)
    spine: list[str] = []
    if len(nonzero) >= 3:
        median = nonzero[len(nonzero) // 2]
        for node_id, value in ranked[:2]:
            if value > 2 * median and value > 0:
                spine.append(node_id)

    remaining = [nid for nid in ws.ids if nid not in spine]
    adjacency = {
        nid: {n for n in ws.undirected[nid] if n not in spine}
        for nid in remaining
    }
    betweenness = _betweenness(remaining, adjacency)
    partition = _community_partition(remaining, adjacency, max_communities)

    bridges = []
    for edge in ws.semantic_edges:
        if edge.src in spine or edge.dst in spine:
            continue
        left, right = partition.get(edge.src), partition.get(edge.dst)
        if left is None or right is None or left == right:
            continue
        score = betweenness.get(edge.src, 0.0) + betweenness.get(edge.dst, 0.0)
        bridges.append({
            "src": edge.src,
            "dst": edge.dst,
            "type": "BRIDGES",
            "edge_type": edge.type,
            "communities": sorted((left, right)),
            "score": round(score, 6),
            "src_label": _label(ws.g, edge.src),
            "dst_label": _label(ws.g, edge.dst),
        })
    bridges.sort(key=lambda b: (-b["score"], b["src"], b["dst"]))

    top_nodes = sorted(
        ({"id": nid, "label": _label(ws.g, nid), "betweenness": round(val, 6)}
         for nid, val in betweenness.items() if val > 0),
        key=lambda r: (-r["betweenness"], r["id"]),
    )
    return {
        "spine_removed": spine,
        "communities": len(set(partition.values())),
        "bridge_edges": bridges[:limit],
        "bridge_nodes": top_nodes[:limit],
    }


# ---------- 8. tensions ---------------------------------------------------------

def tensions(ws: _Workspace, limit: int) -> list[dict]:
    """Contradiction structure: nodes both supported and challenged, and
    challenged contributors to goals that other nodes serve."""
    g = ws.g
    supported: dict[str, list[str]] = defaultdict(list)
    challenged: dict[str, list[str]] = defaultdict(list)
    serves: dict[str, list[str]] = defaultdict(list)
    for edge in ws.semantic_edges:
        if edge.type == "SUPPORTED_BY":
            supported[edge.src].append(edge.dst)
        elif edge.type == "CHALLENGES":
            challenged[edge.dst].append(edge.src)
        elif edge.type == "SERVES":
            serves[edge.dst].append(edge.src)

    proposals = []
    for node_id in ws.ids:
        if node_id in supported and node_id in challenged:
            for challenger in sorted(challenged[node_id]):
                proposals.append(_proposal(
                    g, challenger, node_id, "TENSION_WITH",
                    score=float(len(supported[node_id]) + len(challenged[node_id])),
                    rationale=(
                        f"target has {len(supported[node_id])} supporting and "
                        f"{len(challenged[node_id])} challenging edges — contested claim"
                    ),
                    evidence=sorted(supported[node_id]),
                ))
    for goal, contributors in serves.items():
        if goal not in challenged:
            continue
        for challenger in sorted(challenged[goal]):
            for contributor in sorted(contributors):
                if contributor == challenger:
                    continue
                proposals.append(_proposal(
                    g, challenger, contributor, "TENSION_WITH",
                    score=1.0,
                    rationale=(
                        f"challenges {goal}, which this node SERVES — "
                        "the contribution inherits the risk"
                    ),
                    evidence=[goal],
                ))
    proposals.sort(key=lambda p: (-p["score"], p["src"], p["dst"]))
    return proposals[:limit]


# ---------- assembly ------------------------------------------------------------

def build_discovery(g: Graph, *, limit: int = 10, stale_days: int = 30,
                    min_co_sources: int = 2) -> dict:
    ws = _Workspace(g)
    report = {
        "schema_version": SCHEMA_VERSION,
        "stats": {
            "semantic_nodes": len(ws.ids),
            "semantic_edges": len(ws.semantic_edges),
        },
        "staleness_radar": staleness_radar(ws, stale_days, limit),
        "co_mentions": co_mention_candidates(ws, min_co_sources, limit),
        "serves_candidates": serves_candidates(ws, limit),
        "related_candidates": related_candidates(ws, limit),
        "question_debt": question_debt(ws, limit),
        "corroboration": corroboration(ws, limit),
        "bridges": despined_bridges(ws, limit),
        "tensions": tensions(ws, limit),
    }
    return report


def extract_candidates(report: dict) -> dict:
    """Flatten every derived-edge proposal into one promotion-queue payload."""
    proposals = []
    for section in ("co_mentions", "serves_candidates", "related_candidates", "tensions"):
        proposals.extend(report.get(section, []))
    for bridge in report.get("bridges", {}).get("bridge_edges", []):
        proposals.append({
            "src": bridge["src"],
            "dst": bridge["dst"],
            "type": "BRIDGES",
            "score": bridge["score"],
            "rationale": f"connects communities {bridge['communities']}",
            "evidence_sources": [],
            "src_label": bridge["src_label"],
            "dst_label": bridge["dst_label"],
            "status": "proposed",
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "note": "Derived-edge proposals. Review before promoting; discover never mutates the graph.",
        "proposals": proposals,
    }


# ---------- console report ------------------------------------------------------

def _print_pairs(title: str, rows: list[dict], empty: str) -> None:
    print(f"\n{title}")
    if not rows:
        print(f"  {empty}")
        return
    for row in rows:
        print(f"  {row['src']} ↔ {row['dst']}  [{row['type']} {row['score']}]")
        print(f"    {row['rationale']}")


def print_report(report: dict) -> None:
    stats = report["stats"]
    print(f"discover: {stats['semantic_nodes']} semantic nodes, "
          f"{stats['semantic_edges']} semantic edges — proposals only, graph untouched")

    radar = report["staleness_radar"]
    print(f"\nStaleness radar (≥{radar['stale_days_threshold']} days behind latest activity)")
    if not radar["stale"]:
        print("  nothing stale — memory is warm")
    for row in radar["stale"]:
        print(f"  {row['id']}  {row['days_stale']}d cold, importance {row['importance']}")

    _print_pairs("Co-mention candidates (recur across sources, never linked)",
                 report["co_mentions"], "no multi-source co-mentions without edges")
    _print_pairs("Goal-alignment candidates (close to a goal, no contribution path)",
                 report["serves_candidates"], "every entangled node already has a path to its goals")
    _print_pairs("Link predictions (Adamic-Adar)",
                 report["related_candidates"], "no strong non-adjacent overlaps")

    debt = report["question_debt"]
    print(f"\nQuestion debt ({len(debt['open'])} open, "
          f"{len(debt['answers_detected'])} answered via decisions)")
    for row in debt["open"]:
        print(f"  {row['id']}  debt {row['debt_score']} "
              f"(age {row['age_days']}d, evidence edges {row['evidence_edges']})")

    corro = report["corroboration"]
    print(f"\nCorroboration (source-count distribution {corro['source_count_distribution']})")
    for row in corro["single_source"]:
        print(f"  {row['id']}  single source: {row['source']}")

    bridges = report["bridges"]
    spine = ", ".join(bridges["spine_removed"]) or "none"
    print(f"\nBridges after removing spine [{spine}] "
          f"({bridges['communities']} communities)")
    for row in bridges["bridge_edges"]:
        print(f"  {row['src']} —{row['edge_type']}— {row['dst']}  "
              f"communities {row['communities']}")

    _print_pairs("Tensions", report["tensions"], "no contested claims detected")


# ---------- CLI -----------------------------------------------------------------

def run_discover(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mykg discover")
    parser.add_argument("--graph", default=None,
                        help="Graph JSON path. Defaults to MYGRAPH_PATH or local graph.")
    parser.add_argument("--out", default=None,
                        help="Write full discovery report JSON here ('-' for stdout).")
    parser.add_argument("--candidates", default=None,
                        help="Write derived-edge proposals (promotion queue) here.")
    parser.add_argument("--limit", type=int, default=10, help="Rows per section.")
    parser.add_argument("--stale-days", type=int, default=30,
                        help="Days behind latest graph activity before a node is stale.")
    parser.add_argument("--min-co-sources", type=int, default=2,
                        help="Distinct sources required for a co-mention proposal.")
    parsed = parser.parse_args(args)

    g = Graph.load(parsed.graph)
    report = build_discovery(g, limit=parsed.limit, stale_days=parsed.stale_days,
                             min_co_sources=parsed.min_co_sources)

    if parsed.out == "-":
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        print()
    else:
        print_report(report)
        if parsed.out:
            path = Path(parsed.out).expanduser().resolve()
            path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            print(f"\ndiscover: wrote {path}")

    if parsed.candidates:
        payload = extract_candidates(report)
        path = Path(parsed.candidates).expanduser().resolve()
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"discover: wrote {len(payload['proposals'])} proposals → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(run_discover(sys.argv[1:]))
