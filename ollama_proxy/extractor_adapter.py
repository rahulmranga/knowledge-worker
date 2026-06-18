"""
extractor_adapter.py — local-Gemma drop-in for mygraph's extractor (v1.5).

mygraph/extractor.py uses Claude with native tool-use to emit a structured
candidates payload. Ollama models don't speak Anthropic tool-use; they speak
Ollama's `format` (JSON mode + optional JSON schema). This adapter:

  - reuses the same prompt template + schema as mygraph/extractor.py
  - calls Ollama with `format=<schema>` for constrained JSON output
  - returns the same dict shape, so validator.py / review.py / merge.py work
    without modification

Usage (drop-in):
    from ollama_proxy.extractor_adapter import extract as gemma_extract
    payload = gemma_extract(Path("notes.md"), out_path=Path("out.json"))

Or via the helper CLI:
    python ollama_proxy/extractor_adapter.py path/to/file.md [out.json]

Env:
    OLLAMA_DEFAULT_MODEL  default model tag (gemma4:e4b)
    OLLAMA_BASE_URL       http://127.0.0.1:11434
    GEMMA_NUM_CTX         optional context window override (default 8192)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make mygraph/ importable regardless of cwd.
_HERE = Path(__file__).resolve().parent
_MYGRAPH = _HERE.parent / "mygraph"
if str(_MYGRAPH) not in sys.path:
    sys.path.insert(0, str(_MYGRAPH))

from mygraph import Graph, NODE_TYPES, EDGE_TYPES, slug  # noqa: E402
from extractor import (  # noqa: E402
    EXTRACTION_TOOL,
    PROMPT_TEMPLATE,
    build_source_decl,
    ensure_provenance_edges,
)

try:
    import httpx
except ImportError as e:
    raise SystemExit(
        "extractor_adapter: missing dep. Run: pip install httpx"
    ) from e


OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_DEFAULT_MODEL", "gemma4:e4b")
NUM_CTX = int(os.environ.get("GEMMA_NUM_CTX", "8192"))

# JSON schema mirrors mygraph/extractor.py's tool input_schema.
RESPONSE_SCHEMA = EXTRACTION_TOOL["input_schema"]


def _ollama_chat(prompt: str, model: str, schema: dict) -> dict:
    """Call /api/chat with format=schema, return parsed JSON content."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": schema,                 # Ollama structured-output mode
        "options": {"num_ctx": NUM_CTX, "temperature": 0.2},
    }
    with httpx.Client(timeout=600.0) as c:
        r = c.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
    if r.status_code != 200:
        raise RuntimeError(
            f"extractor_adapter: ollama returned {r.status_code}: {r.text[:500]}"
        )
    body = r.json()
    content = (body.get("message") or {}).get("content", "")
    if not content:
        raise RuntimeError(f"extractor_adapter: empty response from {model}")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        # Fallback: strip code fences if the model wrapped output despite format hint.
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped
            stripped = stripped.rsplit("```", 1)[0] if stripped.endswith("```") else stripped
            return json.loads(stripped)
        raise RuntimeError(
            f"extractor_adapter: model returned non-JSON: {content[:300]}"
        ) from e


def extract(md_path: Path, out_path: Path | None = None,
            model: str = DEFAULT_MODEL) -> dict:
    """End-to-end extract via local Ollama. Same return shape as
    mygraph.extractor.extract — drop-in compatible with validate()/review()/merge()."""
    g = Graph.load()
    decl = build_source_decl(md_path)
    source_text = md_path.read_text(encoding="utf-8")
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
    payload = _ollama_chat(prompt, model=model, schema=RESPONSE_SCHEMA)

    # Ensure required keys exist so validator never crashes on a missing top-level.
    payload.setdefault("source", {
        "id": decl["source_id"],
        "label": decl["source_label"],
        "body": "",
    })
    payload.setdefault("nodes", [])
    payload.setdefault("edges", [])
    injected = ensure_provenance_edges(payload)
    if injected:
        print(
            "extractor_adapter: gateway returned missing provenance edges; "
            f"synthesized {injected} MENTIONED_IN edges.",
            file=sys.stderr,
        )

    payload.setdefault("_meta", {})
    payload["_meta"]["source_path"] = decl["source_path"]
    payload["_meta"]["ingested_at"] = decl["ingested_at"]
    payload["_meta"]["model"] = model
    payload["_meta"]["backend"] = "ollama"

    if out_path:
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python extractor_adapter.py <path/to/file.md> [out.json] [--model NAME]")
        return 1
    md = Path(argv[1]).expanduser().resolve()
    out = None
    model = DEFAULT_MODEL
    rest = argv[2:]
    if "--model" in rest:
        i = rest.index("--model")
        model = rest[i + 1]
        del rest[i:i + 2]
    if rest:
        out = Path(rest[0]).expanduser().resolve()
    else:
        out = md.parent / f"{md.stem}.candidates.gemma.json"
    payload = extract(md, out, model=model)
    print(f"extractor_adapter: model={model}  "
          f"nodes={len(payload.get('nodes', []))}  "
          f"edges={len(payload.get('edges', []))}  ->  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
