"""
eval_compare.py — Claude vs Gemma extraction A/B (v1.5).

Runs the same source markdown through both extractors (mygraph/extractor.py
for Claude, ollama_proxy/extractor_adapter.py for Gemma), then writes a single
record to eval_record.jsonl with kind="extractor_comparison".

Use this to feed the v1 eval corpus with comparative data — the hard signal
for "should we replace Claude with local Gemma?" lives here.

Usage:
    python ollama_proxy/eval_compare.py path/to/file.md
    python ollama_proxy/eval_compare.py path/to/file.md --gemma-model gemma4:latest
    python ollama_proxy/eval_compare.py path/to/file.md --claude-only
    python ollama_proxy/eval_compare.py path/to/file.md --gemma-only

Compares (per-side):
  - n_nodes, n_edges (raw)
  - n_high / n_medium / n_low confidence
  - validator outcome: accepted / demoted / rejected
  - latency (wall-clock, seconds)
  - which node IDs each side proposed (set diff)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# wire up sibling imports
_HERE = Path(__file__).resolve().parent
_MYGRAPH = _HERE.parent / "mygraph"
for _p in (_MYGRAPH, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from validator import validate  # noqa: E402


def _by_confidence(items: list[dict]) -> dict:
    out = {"high": 0, "medium": 0, "low": 0, "other": 0}
    for it in items:
        c = it.get("confidence", "other")
        out[c if c in out else "other"] += 1
    return out


def _summarize(payload: dict, src_text: str, latency_s: float) -> dict:
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    try:
        validated, manifest = validate(payload, src_text)
        v_accepted_n = len(manifest.accepted_nodes)
        v_accepted_e = len(manifest.accepted_edges)
        v_demoted = len(manifest.demoted_nodes)
        v_rejected_n = len(manifest.rejected_nodes)
        v_rejected_e = len(manifest.rejected_edges)
        validator_error = None
    except Exception as e:
        v_accepted_n = v_accepted_e = v_demoted = v_rejected_n = v_rejected_e = None
        validator_error = str(e)

    return {
        "n_nodes_raw": len(nodes),
        "n_edges_raw": len(edges),
        "node_confidence": _by_confidence(nodes),
        "edge_confidence": _by_confidence(edges),
        "validator": {
            "accepted_nodes": v_accepted_n,
            "accepted_edges": v_accepted_e,
            "demoted_nodes": v_demoted,
            "rejected_nodes": v_rejected_n,
            "rejected_edges": v_rejected_e,
            "error": validator_error,
        },
        "node_ids": sorted({n.get("id", "") for n in nodes}),
        "latency_s": round(latency_s, 2),
        "model": (payload.get("_meta") or {}).get("model"),
        "backend": (payload.get("_meta") or {}).get("backend"),
    }


def _id_diff(a_summary: dict, b_summary: dict) -> dict:
    a_ids = set(a_summary.get("node_ids", []))
    b_ids = set(b_summary.get("node_ids", []))
    return {
        "shared": sorted(a_ids & b_ids),
        "claude_only": sorted(a_ids - b_ids),
        "gemma_only": sorted(b_ids - a_ids),
        "jaccard": (len(a_ids & b_ids) / len(a_ids | b_ids)) if (a_ids | b_ids) else None,
    }


def run(md_path: Path, claude_only: bool = False, gemma_only: bool = False,
        gemma_model: str | None = None, claude_model: str | None = None) -> dict:
    src_text = md_path.read_text(encoding="utf-8")

    claude_summary: dict | None = None
    gemma_summary: dict | None = None
    claude_payload: dict | None = None
    gemma_payload: dict | None = None

    # Claude side
    if not gemma_only:
        from extractor import extract as claude_extract  # noqa: E402
        t0 = time.perf_counter()
        kwargs = {"model": claude_model} if claude_model else {}
        claude_payload = claude_extract(md_path, **kwargs)
        claude_summary = _summarize(claude_payload, src_text, time.perf_counter() - t0)

    # Gemma side
    if not claude_only:
        from extractor_adapter import extract as gemma_extract  # noqa: E402
        t0 = time.perf_counter()
        kwargs = {"model": gemma_model} if gemma_model else {}
        gemma_payload = gemma_extract(md_path, **kwargs)
        gemma_summary = _summarize(gemma_payload, src_text, time.perf_counter() - t0)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "extractor_comparison",
        "source_path": str(md_path),
        "claude": claude_summary,
        "gemma": gemma_summary,
    }
    if claude_summary and gemma_summary:
        record["diff"] = _id_diff(claude_summary, gemma_summary)

    # write to mygraph/eval_record.jsonl (canonical eval log location)
    log_path = _MYGRAPH / "eval_record.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="A/B Claude vs Gemma extraction")
    p.add_argument("source", help="path to source markdown")
    p.add_argument("--claude-only", action="store_true")
    p.add_argument("--gemma-only", action="store_true")
    p.add_argument("--gemma-model", default=None,
                   help=f"override (default {os.environ.get('OLLAMA_DEFAULT_MODEL', 'gemma4:e4b')})")
    p.add_argument("--claude-model", default=None,
                   help="override Claude model")
    p.add_argument("--print", action="store_true", help="pretty-print the record to stdout")
    args = p.parse_args(argv)

    md = Path(args.source).expanduser().resolve()
    if not md.exists():
        print(f"eval_compare: not found: {md}", file=sys.stderr)
        return 1
    record = run(md, claude_only=args.claude_only, gemma_only=args.gemma_only,
                 gemma_model=args.gemma_model, claude_model=args.claude_model)
    if args.print:
        print(json.dumps(record, indent=2))
    else:
        # Compact summary for the terminal
        c, g = record.get("claude"), record.get("gemma")
        print(f"source: {md.name}")
        if c:
            print(f"  claude  ({c.get('model')}): {c['n_nodes_raw']} nodes / {c['n_edges_raw']} edges  "
                  f"high={c['node_confidence']['high']} med={c['node_confidence']['medium']} low={c['node_confidence']['low']}  "
                  f"{c['latency_s']}s")
            v = c.get("validator", {})
            print(f"            validator: accepted {v.get('accepted_nodes')} / demoted {v.get('demoted_nodes')} / rejected {v.get('rejected_nodes')}")
        if g:
            print(f"  gemma   ({g.get('model')}): {g['n_nodes_raw']} nodes / {g['n_edges_raw']} edges  "
                  f"high={g['node_confidence']['high']} med={g['node_confidence']['medium']} low={g['node_confidence']['low']}  "
                  f"{g['latency_s']}s")
            v = g.get("validator", {})
            print(f"            validator: accepted {v.get('accepted_nodes')} / demoted {v.get('demoted_nodes')} / rejected {v.get('rejected_nodes')}")
        d = record.get("diff")
        if d:
            print(f"  jaccard(node_ids) = {d['jaccard']:.2f}  "
                  f"shared={len(d['shared'])} claude_only={len(d['claude_only'])} gemma_only={len(d['gemma_only'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
