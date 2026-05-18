# knowledge-worker

**Source-backed memory for AI work. Local files in, durable context out.**

<p align="center">
  <img src="docs/assets/knowledge-worker-demo.gif" alt="knowledge-worker graph visualizer demo" width="900">
</p>

`knowledge-worker` is a local-first personal knowledge graph for carrying context across AI sessions. It turns notes into reviewable concepts, decisions, goals, and relationships, keeps source excerpts attached, and exports compact context you can paste into Claude, GPT, Ollama, or any other LLM workflow.

Your private graph stays on your machine.

## Why

AI conversations usually start from zero. You clarify a decision, name a constraint, sketch a goal, and then the next session forgets it. RAG can be heavy, full-note prompts are noisy, and most note apps do not plug cleanly into chat workflows.

`knowledge-worker` keeps the useful parts: cited claims, explicit relationships, human review, and a small context snapshot when you need continuity.

## What It Does

- Ingests markdown notes into candidate graph nodes and edges.
- Requires provenance excerpts before claims become durable memory.
- Lets you review, accept, reject, or edit LLM proposals before merge.
- Searches by term, lists nodes by type, and finds paths between ideas.
- Exports an LLM-ready context snapshot for a fresh chat session.
- Generates an offline HTML graph viewer for exploration and demos.

## Quick Start

Requirements: Python 3.10+ on macOS or Linux. The core demo CLI has no runtime dependencies beyond the standard library.

```bash
git clone https://github.com/rahulmranga/knowledge-worker
cd knowledge-worker

# Install the CLI command
python3 -m pip install -e .

# Run the public demo graph, no API key needed
MYGRAPH_PATH=examples/demo_graph.json mykg summary
MYGRAPH_PATH=examples/demo_graph.json mykg query "provenance"

# Generate an LLM-ready context snapshot
MYGRAPH_PATH=examples/demo_graph.json mykg context

# Visualize the graph as a self-contained HTML file
mykg viz --graph examples/demo_graph.json --out /tmp/demo.html
```

One-command smoke test:

```bash
python3 -m pip install -e . && MYGRAPH_PATH=examples/demo_graph.json mykg query provenance
```

Run the test suite with:

```bash
python3 -m unittest
```

## Use Your Own Notes

LLM-backed ingest needs either an Anthropic API key or a local Ollama model:

```bash
python3 -m pip install -e ".[llm]"
export ANTHROPIC_API_KEY=...

mykg ingest path/to/your/notes.md
```

For local Ollama:

```bash
python3 -m pip install -e ".[ollama]"
mykg ingest notes.md --backend ollama --model llama3
```

If you prefer a traditional requirements file, `python3 -m pip install -r requirements.txt` installs the CLI plus optional dependencies for Claude ingest, Ollama ingest, and Turtle/RDF export.

## Private Graph Workflow

The public repo ships code, docs, and a fictional demo graph. Your real graph should live outside the repo or in the ignored default path, then be loaded explicitly:

```bash
MYGRAPH_PATH=~/my-private-graph/mygraph.json mykg summary
MYGRAPH_PATH=~/my-private-graph/mygraph.json mykg query "architecture"
MYGRAPH_PATH=~/my-private-graph/mygraph.json mykg context
```

Your private `mygraph.json`, generated private viewers, TTL exports, eval logs, state logs, and local env files are ignored by default.

## Commands

| Command | What it does |
|---|---|
| `seed` | Populate a fictional demo graph |
| `summary` | Show node and edge counts by type |
| `query <term>` | Search nodes, neighbors, and provenance |
| `list <type>` | List nodes of a given type |
| `path <a> <b>` | Find the shortest path between two nodes |
| `ingest <file.md>` | Extract, validate, review, merge, and eval candidates |
| `check --provenance` | Flag nodes with missing source citations |
| `export --ttl` | Emit Turtle/RDF |
| `context` | Print a compact LLM-ready context snapshot |
| `viz` | Generate an offline single-file HTML viewer |
| `state "<entry>"` | Append a mood/state sidecar entry |

## Local LLM Support

The `ollama_proxy/` package adds three local-model surfaces:

- `server.py`: MCP wrapper for Claude/Cowork-style tool use.
- `proxy.py`: Ollama-compatible logging passthrough for HTTP clients.
- `extractor_adapter.py`: drop-in extraction backend for `mykg ingest --backend ollama`.

See [ollama_proxy/README.md](ollama_proxy/README.md) for setup.

## Design Principles

**Provenance first.** Every durable claim points back to a source document and literal excerpt.

**Local first.** The graph is a file on your machine. No cloud sync, accounts, or telemetry.

**Review before merge.** The LLM proposes. You decide. Deterministic validation runs before anything enters the graph.

**Boring persistence.** Plain JSON until it becomes the limiting factor. The schema stays stable across storage backends.

## Repository Layout

```text
mygraph/          Core CLI and pipeline modules
examples/         Fictional demo graph, TTL, and HTML viewer
docs/             Roadmap and public assets
ollama_proxy/     Adapter, MCP server, and proxy for local Ollama workflows
tests/            CLI smoke tests
SPEC.md           Graph model specification
V1_DESIGN.md      Pipeline design notes
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The core graph model is intentionally minimal; contributions that preserve that shape are preferred.

## License

MIT
