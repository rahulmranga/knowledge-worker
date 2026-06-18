"""
audit.py — structural verifier for external-query audits (e.g. copilot_response_audit.md).

No LLM. Just structural checks against the graph:
  - confidence labels surfaced for non-high nodes?
  - provenance (source:*) cited?
  - completeness: did the response list all expected nodes for a typed question?

Outputs JSONL eval_record entries appended to eval_record.jsonl.

Usage:
    python audit.py copilot_response_audit.md
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from mygraph import Graph

HERE = Path(__file__).parent
EVAL_LOG = HERE / "eval_record.jsonl"


def parse_audit(md_text: str) -> list[dict]:
    blocks = re.split(r'\n## \d+\.', md_text)[1:]
    out = []
    for b in blocks:
        q = re.search(r'\*\*User:\*\*\s*(.+?)(?=\*\*Copilot:\*\*)', b, re.DOTALL)
        r = re.search(r'\*\*Copilot:\*\*\s*(.+?)(?=\*\*Evaluation:\*\*|\Z)', b, re.DOTALL)
        e = re.search(r'\*\*Evaluation:\*\*\s*(.+?)\Z', b, re.DOTALL)
        out.append({
            "question": q.group(1).strip() if q else "",
            "response": r.group(1).strip() if r else "",
            "self_eval": e.group(1).strip() if e else "",
        })
    return out


def referenced_nodes(text: str, g: Graph) -> list[str]:
    ids = set(re.findall(r'\b([a-z]+:[a-z0-9-]+)\b', text))
    low = text.lower()
    for nid, n in g.nodes.items():
        if len(n.label) > 4 and n.label.lower() in low:
            ids.add(nid)
    return sorted(i for i in ids if i in g.nodes)


def check_confidence(refs, g, resp):
    issues = []
    low = resp.lower()
    for r in refs:
        n = g.nodes[r]
        if n.confidence != "high" and n.confidence not in low and "confidence" not in low:
            issues.append(f"unflagged_{n.confidence}_confidence:{r}")
    return issues


def check_provenance(refs, resp):
    if not refs:
        return []
    return [] if "source:" in resp.lower() else ["no_source_cited"]


def check_completeness(question, refs, g, resp):
    q = question.lower()
    issues = []
    typed_checks = [
        ("goal", "goal"),
        ("decid", "decision"),
        ("idea", "idea"),
        ("question", "question"),
    ]
    for keyword, node_type in typed_checks:
        if keyword in q and "?" in q:
            all_of = [nid for nid, n in g.nodes.items() if n.type == node_type]
            if not all_of:
                continue
            listed = [r for r in refs if r in all_of]
            if len(listed) < len(all_of):
                issues.append(f"incomplete_{node_type}_listing:{len(listed)}/{len(all_of)}")
    return issues


def audit(audit_path: Path) -> list[dict]:
    g = Graph.load()
    md = audit_path.read_text(encoding="utf-8")
    blocks = parse_audit(md)
    records = []
    ts = datetime.now(timezone.utc).isoformat()
    for i, b in enumerate(blocks, 1):
        refs = referenced_nodes(b["response"], g)
        misses = (
            check_confidence(refs, g, b["response"])
            + check_provenance(refs, b["response"])
            + check_completeness(b["question"], refs, g, b["response"])
        )
        records.append({
            "ts": ts,
            "kind": "external_query",
            "audit_source": audit_path.name,
            "q_index": i,
            "question": b["question"][:200],
            "response_excerpt": b["response"][:300],
            "self_eval": b["self_eval"][:200],
            "referenced_nodes": refs,
            "claude_verdict": "ok" if not misses else "miss",
            "misses": misses,
        })
    with EVAL_LOG.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return records


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else HERE / "copilot_response_audit.md"
    if not path.exists():
        print(f"Not found: {path}")
        return 1
    records = audit(path)
    misses = [r for r in records if r["misses"]]
    print(f"Wrote {len(records)} eval_records -> {EVAL_LOG}")
    print(f"  {len(misses)}/{len(records)} responses flagged with misses\n")
    for r in misses:
        print(f"  Q{r['q_index']}: {r['question'][:60]}")
        for m in r["misses"]:
            print(f"      - {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
