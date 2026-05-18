"""
extractor_openai.py — Stage 1 extractor backed by OpenAI Responses API.

Reads a markdown file, calls OpenAI with a JSON-schema constrained response,
and writes a candidates.json. No graph mutation here.

Env:
    OPENAI_API_KEY        — required.
    MYGRAPH_OPENAI_MODEL  — optional model override; default `gpt-5.2`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mygraph import Graph, NODE_TYPES, EDGE_TYPES

try:
    from .extractor import EXTRACTION_TOOL, PROMPT_TEMPLATE, build_source_decl
except ImportError:  # direct script execution
    from extractor import EXTRACTION_TOOL, PROMPT_TEMPLATE, build_source_decl


DEFAULT_MODEL = os.environ.get("MYGRAPH_OPENAI_MODEL", "gpt-5.2")


def _response_text(resp: Any) -> str:
    """Extract text from OpenAI Responses SDK objects across SDK versions."""
    output_text = getattr(resp, "output_text", None)
    if output_text:
        return output_text

    chunks: list[str] = []
    for item in getattr(resp, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
    return "".join(chunks)


def _loads_json(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped
        stripped = stripped.rsplit("```", 1)[0] if stripped.endswith("```") else stripped
    return json.loads(stripped)


def call_openai(prompt: str, model: str = DEFAULT_MODEL) -> dict:
    """Invoke OpenAI with Structured Outputs. Returns the parsed JSON dict."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "extractor_openai: `openai` package not installed. Run:\n"
            "    python -m pip install -e '.[openai]'"
        ) from e
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "extractor_openai: OPENAI_API_KEY env var is not set.\n"
            "Either export it, or run `mykg ingest <file> --candidates-file <path>` "
            "to skip extraction with a hand-curated candidates JSON."
        )

    client = OpenAI()
    resp = client.responses.create(
        model=model,
        input=[{"role": "user", "content": prompt}],
        max_output_tokens=8000,
        text={
            "format": {
                "type": "json_schema",
                "name": EXTRACTION_TOOL["name"],
                "description": EXTRACTION_TOOL["description"],
                "schema": EXTRACTION_TOOL["input_schema"],
                "strict": False,
            }
        },
    )
    text = _response_text(resp)
    if not text:
        raise RuntimeError("extractor_openai: model returned no text output.")
    try:
        return _loads_json(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"extractor_openai: model returned non-JSON: {text[:300]}"
        ) from e


def extract(md_path: Path, out_path: Path | None = None,
            model: str = DEFAULT_MODEL) -> dict:
    """End-to-end extract via OpenAI. Same return shape as extractor.extract."""
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
    payload = call_openai(prompt, model=model)
    payload.setdefault("_meta", {})
    payload["_meta"]["source_path"] = decl["source_path"]
    payload["_meta"]["ingested_at"] = decl["ingested_at"]
    payload["_meta"]["model"] = model
    payload["_meta"]["backend"] = "openai"
    if out_path:
        out_path.write_text(json.dumps(payload, indent=2))
    return payload


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python extractor_openai.py <path/to/file.md> [out.json] [--model NAME]")
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
        out = md.parent / f"{md.stem}.candidates.openai.json"
    payload = extract(md, out, model=model)
    print(f"extractor_openai: model={model}  "
          f"nodes={len(payload.get('nodes', []))}  "
          f"edges={len(payload.get('edges', []))}  ->  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
