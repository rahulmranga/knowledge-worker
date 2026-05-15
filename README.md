# knowledge-worker

A provenance-backed personal knowledge graph toolkit.

`knowledge-worker` keeps durable concepts, decisions, goals, questions, and
sources in a small graph that can be queried from local AI workflows. The public
repo ships only code, docs, and a fictional demo graph. Private graph data should
stay outside git and be loaded with `MYGRAPH_PATH`.

## What It Does

- Ingests markdown into candidate nodes and edges.
- Requires source-backed provenance for high-confidence claims.
- Reviews candidates before merge.
- Exports JSON graphs to Turtle/RDF.
- Runs deterministic health checks.
- Generates an offline, single-file HTML graph viewer.

## Quick Start

```bash
cd mygraph
python3 mygraph.py summary
python3 mygraph.py query provenance
python3 mygraph.py check --provenance
python3 mygraph.py export --ttl --out ../examples/demo_graph.ttl
python3 mygraph.py viz --graph ../examples/demo_graph.json --out ../examples/demo_graph.html --no-open
```

Use a private graph without copying it into the repo:

```bash
MYGRAPH_PATH=/absolute/path/to/private/mygraph.json python3 mygraph/mygraph.py summary
MYGRAPH_PATH=/absolute/path/to/private/mygraph.json python3 mygraph/mygraph.py query "roadmap"
MYGRAPH_PATH=/absolute/path/to/private/mygraph.json python3 mygraph/mygraph.py check --provenance
```

## Public Demo Files

| File | Purpose |
|---|---|
| `examples/demo_graph.json` | Fictional graph used by docs and tests. |
| `examples/demo_graph.ttl` | Turtle/RDF export generated from the demo graph. |
| `examples/demo_graph.html` | Offline viewer with the demo graph embedded. |
| `mygraph/` | Runnable graph CLI and modules. |
| `docs/ROADMAP.md` | Public implementation roadmap. |

## Private Data Policy

This repo is meant to be safe as a public demo:

- Do not commit raw chat exports, private graph JSON, private TTL, eval logs, or
  generated private viewers.
- Load private graph files through `MYGRAPH_PATH` or `--graph`.
- Keep `mygraph/mygraph.json` local-only.
- Run `git status --short` and the privacy scan before committing.

## Commands

```bash
python3 mygraph/mygraph.py seed
python3 mygraph/mygraph.py summary
python3 mygraph/mygraph.py query "provenance"
python3 mygraph/mygraph.py path idea:context-memory goal:trusted-ai-assistance
python3 mygraph/mygraph.py check --provenance
python3 mygraph/mygraph.py export --ttl --out examples/demo_graph.ttl
python3 mygraph/mygraph.py viz --graph examples/demo_graph.json --out examples/demo_graph.html --no-open
```

LLM-backed ingest and semantic checks require:

```bash
pip install -r mygraph/requirements.txt
export ANTHROPIC_API_KEY=...
```

The core graph model remains plain JSON and standard-library Python.

## Core Rule

Every non-source node must be tied to a source. If it cannot be traced to
provenance, it should not be treated as a durable claim.
