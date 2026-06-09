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

## How It Compares

`knowledge-worker` is personal AI memory with source-backed claims, not a team
chat-to-wiki system. It keeps reasoning local, reviewable, and tied to literal
provenance excerpts before claims become durable graph knowledge.

See [Competitive Analysis](docs/COMPETITIVE_ANALYSIS.md) for the category
matrix, [Mem0 Comparison](docs/MEM0_COMPARISON.md) for the closest agent-memory
contrast, and [Benchmarks](docs/BENCHMARKS.md) for the offline demo-graph
checks. See [Context Packs](docs/CONTEXT_PACKS.md) for the roadmap direction on
scoped, cited exports for AI handoffs.

## What It Does

- Ingests markdown notes into candidate graph nodes and edges.
- Requires provenance excerpts before claims become durable memory.
- Lets you review, accept, reject, or edit LLM proposals before merge.
- Searches by term, lists nodes by type, and finds paths between ideas.
- Exports an LLM-ready context snapshot for a fresh chat session.
- Audits memory shape with PageRank, betweenness, k-core, communities, weak
  claims, and provenance coverage.
- Generates an offline HTML graph viewer for exploration and demos.

## Quick Start

Requirements: Python 3.10+ on macOS or Linux. The core demo CLI has no runtime dependencies beyond the standard library and does not need a package install.

```bash
git clone https://github.com/rahulmranga/knowledge-worker
cd knowledge-worker

# Run the public demo graph, no API key needed
MYGRAPH_PATH=examples/demo_graph.json python3 mygraph/mygraph.py summary
MYGRAPH_PATH=examples/demo_graph.json python3 mygraph/mygraph.py query "provenance"

# Generate an LLM-ready context snapshot
MYGRAPH_PATH=examples/demo_graph.json python3 mygraph/mygraph.py context

# Audit memory structure and proof coverage
MYGRAPH_PATH=examples/demo_graph.json python3 mygraph/mygraph.py audit --out /tmp/analytics.json --html /tmp/memory_audit.html

# Visualize the graph as a self-contained HTML file
python3 mygraph/mygraph.py viz --graph examples/demo_graph.json --out /tmp/demo.html
```

One-command smoke test:

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 mygraph/mygraph.py query provenance
```

If you want the shorter `mykg` command, install it inside a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
MYGRAPH_PATH=examples/demo_graph.json mykg query provenance
```

Using a virtual environment avoids Homebrew/system Python's externally-managed install errors.

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .

$env:MYGRAPH_PATH = "examples\demo_graph.json"
mykg query provenance
mykg audit --out "$env:TEMP\analytics.json" --html "$env:TEMP\memory_audit.html"
```

If PowerShell blocks activation scripts, run this for the current terminal
session and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Run the test suite with:

```bash
python3 -m unittest
```

Run the public-demo benchmark suite with:

```bash
python3 -m unittest tests/test_benchmarks.py
```

## Use Your Own Notes

You can ingest your notes with or without an API key.

### Claude or Codex App, No API Key

If you are already working with Claude, Codex, or ChatGPT in an app session, you do **not** need an API key. Ask the assistant to produce a `*.candidates.json` file that follows the schema in `mygraph/extractor.py`, then let the local CLI validate, review, and merge it:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

mykg ingest path/to/your/notes.md --candidates-file path/to/your/notes.candidates.json
```

The app subscription helps you create the candidates file. The repo still keeps graph validation and merge local.

### Automated API-Backed Ingest

If you want the CLI to call an LLM directly, use a provider API key or local Ollama.

For Anthropic API:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[anthropic]"
export ANTHROPIC_API_KEY=...

mykg ingest path/to/your/notes.md
```

The Claude backend also auto-detects Anthropic-compatible provider env:

- Anthropic API: `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`
- Foundry: `ANTHROPIC_FOUNDRY_API_KEY` plus `ANTHROPIC_FOUNDRY_RESOURCE` or `ANTHROPIC_FOUNDRY_BASE_URL`
- Bedrock: `AWS_BEARER_TOKEN_BEDROCK`, or AWS credentials plus `AWS_REGION`/`AWS_DEFAULT_REGION`

For OpenAI API:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[openai]"
export OPENAI_API_KEY=...

mykg ingest path/to/your/notes.md --backend openai --model gpt-5.2
```

For local Ollama:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[ollama]"
mykg ingest notes.md --backend ollama --model llama3
```

If you prefer a traditional requirements file, activate a virtual environment first, then run `python -m pip install -r requirements.txt`. That installs the CLI plus optional dependencies for Anthropic API ingest, OpenAI API ingest, Ollama ingest, and Turtle/RDF export.

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
| `audit` | Emit graph analytics, directed idea-flow queues, and optional Memory Audit HTML |
| `state "<entry>"` | Append a mood/state sidecar entry |

## Memory Audit

`mykg audit` is a read-only layer over the graph. It ranks important concepts
with PageRank, bridge ideas with betweenness, structural strength with k-core,
communities with deterministic graph splitting, and weak claims from confidence
and provenance gaps. It also includes directed idea-flow queues:
`idea_attractors` for concepts that many edges point into, `idea_generators`
for ideas that branch outward, and a `weak_claim_queue` that asks for human
review actions instead of auto-promoting conclusions.

```bash
MYGRAPH_PATH=examples/demo_graph.json mykg audit \
  --out /tmp/analytics.json \
  --html /tmp/memory_audit.html
```

The generated HTML puts ranked panels and legwork queues first, with the graph
canvas second. This keeps the feature focused on memory governance instead of
making the raw graph view the product.

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
