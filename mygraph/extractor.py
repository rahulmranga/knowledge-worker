"""
extractor.py — Stage 1 of the v1 ingest pipeline.

Reads a markdown file, calls the Anthropic API with a schema-constrained prompt,
and writes a candidates.json. No graph mutation here.

Provenance-or-bust: the prompt requires literal excerpts for `high`-confidence
candidates. Validator (Stage 2) enforces it; this stage just asks for it.

Env:
    ANTHROPIC_API_KEY — required (else the script raises a clear error).
    MYGRAPH_MODEL    — optional model override; default `claude-sonnet-4-6`.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mygraph import Graph, NODE_TYPES, EDGE_TYPES, slug

DEFAULT_MODEL = os.environ.get("MYGRAPH_MODEL", "claude-sonnet-4-6")

EXTRACTION_TOOL = {
    "name": "emit_candidates",
    "description": "Emit candidate nodes and edges extracted from the source markdown.",
    "input_schema": {
        "type": "object",
        "properties": {
            "source": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["id", "label", "body"],
            },
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string", "enum": sorted(NODE_TYPES)},
                        "label": {"type": "string"},
                        "body": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "excerpt": {"type": "string"},
                    },
                    "required": ["id", "type", "label", "confidence"],
                },
            },
            "edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "src": {"type": "string"},
                        "dst": {"type": "string"},
                        "type": {"type": "string", "enum": sorted(EDGE_TYPES)},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "excerpt": {"type": "string"},
                    },
                    "required": ["src", "dst", "type", "confidence"],
                },
            },
        },
        "required": ["source", "nodes", "edges"],
    },
}


PROMPT_TEMPLATE = """\
You are extracting nodes and edges for a personal knowledge graph centered on Rahul.
The graph stores durable concepts (Person, Idea, Project, Goal, Topic, Reference,
Question, Decision, Source) and relations between them.

Rules:
1. Every node and edge MUST cite a literal excerpt from the source. No paraphrase.
2. Use confidence "high" only when you have a direct quote in the `excerpt` field.
3. Use confidence "medium" for clear paraphrase (still quote what you paraphrased FROM).
4. Use confidence "low" for inference. Quote what you inferred FROM.
5. Slug-style IDs: lowercase, hyphenated, type-prefixed. E.g. `idea:rahul-centered-graph`.
6. Reuse existing IDs (below) when a candidate refers to an existing concept.
7. Do NOT invent biographical facts. If the source doesn't say it, it doesn't go in.
8. The Source node `id` MUST equal: {source_id}
9. Every NEW concept node MUST have a `MENTIONED_IN` edge to the Source.
10. Output the tool call exactly per schema. No prose.

Allowed node types: {node_types}
Allowed edge types: {edge_types}

Existing node IDs (reuse when applicable):
{existing_ids}

SOURCE METADATA:
  id    : {source_id}
  label : {source_label}
  path  : {source_path}

SOURCE MARKDOWN follows between <<<SOURCE>>> markers. Extract.

<<<SOURCE>>>
{source_text}
<<<SOURCE>>>
"""


def build_source_decl(md_path: Path) -> dict:
    sid_slug = slug(md_path.stem)
    return {
        "source_id": f"source:{sid_slug}",
        "source_label": md_path.name,
        "source_path": str(md_path.resolve()),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def call_anthropic(prompt: str, model: str = DEFAULT_MODEL) -> dict:
    """Invoke Claude with the extraction tool. Returns the tool input dict."""
    try:
        import anthropic  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "extractor: `anthropic` package not installed. Run:\n"
            "    pip install anthropic"
        ) from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "extractor: ANTHROPIC_API_KEY env var is not set.\n"
            "Either export it, or run `python mygraph.py ingest <file> --candidates-file <path>` "
            "to skip extraction with a hand-curated candidates JSON."
        )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=8000,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "emit_candidates"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_candidates":
            return block.input  # type: ignore[return-value]
    raise RuntimeError("extractor: model did not emit the emit_candidates tool call.")


def extract(md_path: Path, out_path: Path | None = None,
            model: str = DEFAULT_MODEL) -> dict:
    """End-to-end extract: read markdown, call LLM, write candidates.json."""
    g = Graph.load()
    decl = build_source_decl(md_path)
    source_text = md_path.read_text()
    existing_ids = sorted(g.nodes.keys())
    prompt = PROMPT_TEMPLATE.format(
        source_id=decl["source_id"],
        source_label=decl["source_label"],
        source_path=decl["source_path"],
        node_types=", ".join(sorted(NODE_TYPES)),
        edge_types=", ".join(sorted(EDGE_TYPES)),
        existing_ids="\n".join(f"  - {i}" for i in existing_ids),
        source_text=source_text,
    )
    payload = call_anthropic(prompt, model=model)
    # ensure source_path/ingested_at hitch a ride for downstream stages
    payload.setdefault("_meta", {})
    payload["_meta"]["source_path"] = decl["source_path"]
    payload["_meta"]["ingested_at"] = decl["ingested_at"]
    payload["_meta"]["model"] = model
    if out_path:
        out_path.write_text(json.dumps(payload, indent=2))
    return payload


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python extractor.py <path/to/file.md> [out.json]")
        return 1
    md = Path(argv[1]).expanduser().resolve()
    out = Path(argv[2]).resolve() if len(argv) > 2 else md.parent / f"{md.stem}.candidates.json"
    payload = extract(md, out)
    print(f"extractor: wrote {len(payload.get('nodes', []))} nodes, "
          f"{len(payload.get('edges', []))} edges → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
