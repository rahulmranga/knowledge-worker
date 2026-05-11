"""
check.py — v1 M2 offline health checks.

Subcommands (all write JSONL records to eval_record.jsonl):

  --provenance              hard invariant. Any node (except `source`) without a
                            MENTIONED_IN edge → kind: provenance_violation. Any
                            edge without source_id → same.
  --stale-edges [--days N]  edges with last_seen older than N days (default 90)
                            → kind: stale_candidate.
  --pairs N                 pick N random non-adjacent node pairs, ask the LLM
                            "is X related to Y? if yes, by what predicate?".
                            Logs kind: relational_probe.
  --source-candidates DIR   read recent .md/.txt files in DIR; ask the LLM if
                            any look like Sources we should ingest. Logs
                            kind: source_candidate. Never auto-ingests.

Default (no subcommand): runs --provenance and --stale-edges. LLM-bound checks
require ANTHROPIC_API_KEY; they're skipped (with a warning) if it's unset.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mygraph import Graph
from eval_log import append as eval_append, append_many


# ------------ provenance ------------------------------------------------------

def check_provenance(g: Graph) -> list[dict]:
    """Return list of violation records (also appended to eval_record.jsonl)."""
    violations = []
    mentioned_node_ids = {e.src for e in g.edges if e.type == "MENTIONED_IN"}
    mentioned_node_ids |= {e.dst for e in g.edges if e.type == "MENTIONED_IN"}
    for nid, n in g.nodes.items():
        if n.type == "source":
            continue
        if nid not in mentioned_node_ids:
            violations.append({
                "kind": "provenance_violation",
                "subkind": "node_without_source",
                "node_id": nid,
                "node_type": n.type,
                "label": n.label,
            })
    for i, e in enumerate(g.edges):
        if not e.source_id:
            violations.append({
                "kind": "provenance_violation",
                "subkind": "edge_without_source_id",
                "edge_index": i,
                "src": e.src, "dst": e.dst, "type": e.type,
            })
    append_many(violations)
    return violations


# ------------ stale edges -----------------------------------------------------

def check_stale_edges(g: Graph, days: int = 90) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stale = []
    for i, e in enumerate(g.edges):
        try:
            ls = datetime.fromisoformat(e.last_seen)
        except (ValueError, TypeError):
            continue
        if ls < cutoff:
            stale.append({
                "kind": "stale_candidate",
                "edge_index": i,
                "src": e.src, "dst": e.dst, "type": e.type,
                "last_seen": e.last_seen,
                "age_days": (datetime.now(timezone.utc) - ls).days,
            })
    append_many(stale)
    return stale


# ------------ relational probe (LLM) -----------------------------------------

PAIR_PROMPT = """\
You are evaluating a personal knowledge graph. Two nodes are below. Decide:
  (a) Are these conceptually related?
  (b) If yes, what predicate name from this set best fits?
       {edge_types}

Respond as a single JSON object with keys:
  related   : true | false
  predicate : one of the predicates above, or null if related=false
  rationale : one short sentence
  confidence: high | medium | low

NODE A: id={a_id}  type={a_type}  label={a_label}
        body: {a_body}
NODE B: id={b_id}  type={b_type}  label={b_label}
        body: {b_body}
"""


def _call_claude_json(prompt: str) -> dict | None:
    """Lightweight Claude call returning parsed JSON; None if no API key."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic  # type: ignore
    except ImportError:
        print("check: anthropic SDK not installed; skipping LLM-bound checks.")
        return None
    import json as _json
    client = anthropic.Anthropic()
    model = os.environ.get("MYGRAPH_MODEL", "claude-sonnet-4-6")
    resp = client.messages.create(
        model=model, max_tokens=400,
        messages=[{"role": "user", "content": prompt + "\n\nReturn ONLY JSON."}],
    )
    text = "".join(getattr(b, "text", "") for b in resp.content)
    text = text.strip()
    # be forgiving: strip ```json fences
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0] if text.endswith("```") else text
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        return {"_raw": text, "_parse_error": True}


def check_pairs(g: Graph, k: int = 10) -> list[dict]:
    from mygraph import EDGE_TYPES
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("check --pairs: ANTHROPIC_API_KEY unset; skipping.")
        return []
    adj = set()
    for e in g.edges:
        adj.add((e.src, e.dst))
        adj.add((e.dst, e.src))
    ids = [nid for nid, n in g.nodes.items() if n.type != "source"]
    pairs = []
    attempts = 0
    while len(pairs) < k and attempts < k * 20:
        attempts += 1
        a, b = random.sample(ids, 2)
        if (a, b) in adj:
            continue
        if (a, b) in pairs or (b, a) in pairs:
            continue
        pairs.append((a, b))
    records = []
    for a, b in pairs:
        na, nb = g.nodes[a], g.nodes[b]
        prompt = PAIR_PROMPT.format(
            edge_types=", ".join(sorted(EDGE_TYPES)),
            a_id=a, a_type=na.type, a_label=na.label, a_body=na.body[:200],
            b_id=b, b_type=nb.type, b_label=nb.label, b_body=nb.body[:200],
        )
        result = _call_claude_json(prompt)
        records.append({
            "kind": "relational_probe",
            "a_id": a, "b_id": b,
            "claude_result": result,
        })
    append_many(records)
    return records


# ------------ source candidacy (LLM) -----------------------------------------

SOURCE_CANDIDATE_PROMPT = """\
A markdown/text document is below. Decide whether it should be ingested as a
Source into Rahul's personal knowledge graph. Respond as JSON:

  ingest_recommendation : "yes" | "no" | "maybe"
  rationale             : one short sentence
  candidate_concepts    : list of 1-5 plain-English concept labels you'd extract
                          if ingested (empty list if no)

DOCUMENT (filename: {fname}):
---
{content}
---
"""


def check_source_candidates(g: Graph, dir_path: Path) -> list[dict]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("check --source-candidates: ANTHROPIC_API_KEY unset; skipping.")
        return []
    if not dir_path.is_dir():
        print(f"check --source-candidates: not a directory: {dir_path}")
        return []
    existing_source_paths = {n.body for n in g.nodes.values() if n.type == "source"}
    records = []
    for p in sorted(dir_path.glob("*.md")) + sorted(dir_path.glob("*.txt")):
        if str(p) in existing_source_paths:
            continue
        content = p.read_text()[:8000]
        prompt = SOURCE_CANDIDATE_PROMPT.format(fname=p.name, content=content)
        result = _call_claude_json(prompt)
        records.append({
            "kind": "source_candidate",
            "path": str(p),
            "claude_result": result,
        })
    append_many(records)
    return records


# ------------ CLI dispatch ----------------------------------------------------

def run_check(args: list[str]) -> int:
    g = Graph.load()
    flags = list(args)

    # parse value-bearing flags
    days = 90
    if "--days" in flags:
        i = flags.index("--days")
        days = int(flags[i + 1]); del flags[i:i + 2]
    pairs_n = 0
    if "--pairs" in flags:
        i = flags.index("--pairs")
        try:
            pairs_n = int(flags[i + 1]); del flags[i:i + 2]
        except (ValueError, IndexError):
            pairs_n = 10; del flags[i:i + 1]
    source_dir = None
    if "--source-candidates" in flags:
        i = flags.index("--source-candidates")
        if i + 1 < len(flags):
            source_dir = Path(flags[i + 1]).expanduser().resolve()
            del flags[i:i + 2]
        else:
            print("check: --source-candidates needs a directory")
            return 1

    only = set(f for f in flags if f.startswith("--"))
    run_all = not only and not pairs_n and not source_dir

    rc = 0
    if run_all or "--provenance" in only:
        v = check_provenance(g)
        print(f"provenance violations: {len(v)}")
        for r in v[:10]:
            print(f"  - {r['subkind']}: {r.get('node_id') or r.get('src')+'→'+r.get('dst')}")
        if v:
            rc = 2  # non-zero exit on hard-invariant break
    if run_all or "--stale-edges" in only:
        s = check_stale_edges(g, days=days)
        print(f"stale edges (>{days}d): {len(s)}")
        for r in s[:10]:
            print(f"  - {r['src']} --{r['type']}--> {r['dst']}  ({r['age_days']}d)")
    if pairs_n:
        p = check_pairs(g, k=pairs_n)
        print(f"relational probes: {len(p)} run")
    if source_dir:
        sc = check_source_candidates(g, source_dir)
        print(f"source candidates: {len(sc)} evaluated")
    return rc


if __name__ == "__main__":
    sys.exit(run_check(sys.argv[1:]))
