"""
export_context.py — generate a compact LLM-ready context snapshot of mygraph.
Usage: python export_context.py [--out context.md] [--max-ideas 20]
"""
import json, argparse, datetime
from collections import defaultdict

def load(path="mygraph.json"):
    with open(path) as f:
        return json.load(f)

def export_context(g, max_ideas=20):
    nodes = g["nodes"]
    edges = g["edges"]

    # Build incoming edge count per node
    in_edges = defaultdict(list)
    for e in edges:
        in_edges[e["dst"]].append(e)

    def by_type(t):
        return [n for n in nodes.values() if n.get("type") == t]

    def conf_marker(c):
        if c == "low": return " ⚠"
        if c == "medium": return " ~"
        return ""

    lines = []
    lines.append("# mygraph — Context Snapshot")
    lines.append(f"*Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | "
                 f"{len(nodes)} nodes, {len(edges)} edges*\n")

    # Goals
    goals = by_type("goal")
    if goals:
        lines.append("## Goals")
        for n in goals:
            lines.append(f"- **{n['label']}**{conf_marker(n.get('confidence',''))}")
            if n.get("body"):
                lines.append(f"  {n['body'][:120]}")
        lines.append("")

    # Decisions (high confidence only to keep it tight)
    decisions = [n for n in by_type("decision") if n.get("confidence") != "low"]
    if decisions:
        lines.append("## Key Decisions")
        for n in decisions[:20]:
            lines.append(f"- **{n['label']}**")
            if n.get("body"):
                lines.append(f"  {n['body'][:100]}")
        lines.append("")

    # Ideas — sort by incoming edge count (most connected first)
    ideas = by_type("idea")
    ideas_sorted = sorted(ideas, key=lambda n: -len(in_edges.get(n["id"], [])))
    lines.append("## Ideas")
    for n in ideas_sorted[:max_ideas]:
        edge_count = len(in_edges.get(n["id"], []))
        marker = conf_marker(n.get("confidence",""))
        lines.append(f"- **{n['label']}**{marker} *(connections: {edge_count})*")
        if n.get("body"):
            lines.append(f"  {n['body'][:120]}")
    lines.append("")

    # Topics (core only — k-core proxy: more than 1 incoming edge)
    topics = [n for n in by_type("topic") if len(in_edges.get(n["id"],[])) > 1]
    topics_sorted = sorted(topics, key=lambda n: -len(in_edges.get(n["id"],[])))
    if topics_sorted:
        lines.append("## Core Topics")
        for n in topics_sorted[:20]:
            lines.append(f"- {n['label']} *(×{len(in_edges[n['id']])})*")
        lines.append("")

    # Recent sources (last 5)
    sources = sorted(by_type("source"), key=lambda n: n.get("created_at",""), reverse=True)[:5]
    if sources:
        lines.append("## Recent Sources")
        for n in sources:
            lines.append(f"- {n['label']}")
        lines.append("")

    # Questions
    questions = by_type("question")
    if questions:
        lines.append("## Open Questions")
        for n in questions[:10]:
            lines.append(f"- {n['label']}{conf_marker(n.get('confidence',''))}")
        lines.append("")

    return "\n".join(lines)

if __name__ == "__main__":
    import os, sys
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--max-ideas", type=int, default=20)
    args = parser.parse_args()

    g = load()
    text = export_context(g, max_ideas=args.max_ideas)

    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
        print(f"Written to {args.out}")
    else:
        print(text)
