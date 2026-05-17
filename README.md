# knowledge-worker

**Every AI conversation starts from zero. This one doesn't have to.**

`knowledge-worker` is a local-first personal knowledge graph that gives your AI assistant durable, source-backed memory across sessions — without sending your data to a cloud.

You ingest your notes. The graph extracts concepts, decisions, and goals with source citations. When you open a new Claude (or any LLM) session, you export a compact context snapshot and paste it in. Your assistant picks up where it left off.

Your private graph never leaves your machine.

---

## The Problem

You have a great conversation with an AI assistant. You reach clarity on an architecture decision, a goal, a constraint. Next session — it's gone. You re-explain. You re-decide. The AI is stateless; the cost is yours.

Obsidian doesn't connect to your LLM workflow. Embedding everything in the prompt is expensive and noisy. RAG requires infrastructure. You just want your thinking to persist.

## How It Works

```
Your notes (markdown)
  → ingest: LLM extracts candidate nodes + edges with source excerpts
  → review: you accept, reject, or edit each candidate
  → graph: provenance-backed JSON graph on your machine
  → export_context: compact LLM-ready snapshot
  → paste into Claude / GPT / Ollama → continuity
```

Every claim in the graph points back to the source it came from. If it can't be cited, it stays low-confidence or stays out.

## Quick Start

```bash
git clone https://github.com/rahulmranga/knowledge-worker
cd knowledge-worker

# Run the demo graph (no API key needed)
python3 mygraph/mygraph.py seed
python3 mygraph/mygraph.py summary
python3 mygraph/mygraph.py query "provenance"

# Generate an LLM-ready context snapshot
python3 mygraph/export_context.py

# Visualize the graph (opens a self-contained HTML file)
python3 mygraph/mygraph.py viz --graph examples/demo_graph.json --out /tmp/demo.html
```

For ingest with your own notes (requires an API key or local Ollama):

```bash
pip install -r mygraph/requirements.txt
export ANTHROPIC_API_KEY=...

python3 mygraph/mygraph.py ingest path/to/your/notes.md
```

## Private Graph Workflow

The public repo ships only code, docs, and a fictional demo graph. Your private graph lives outside the repo and is loaded by path:

```bash
# Point any command at your private graph
MYGRAPH_PATH=~/my-private-graph/mygraph.json python3 mygraph/mygraph.py summary
MYGRAPH_PATH=~/my-private-graph/mygraph.json python3 mygraph/mygraph.py query "architecture"
MYGRAPH_PATH=~/my-private-graph/mygraph.json python3 mygraph/mygraph.py export_context
```

Your private `mygraph.json` is gitignored by default. It never ends up in git unless you explicitly add it.

## Commands

| Command | What it does |
|---|---|
| `seed` | Populate a fictional demo graph |
| `summary` | Node + edge counts by type |
| `query <term>` | Search nodes, show neighbors and provenance |
| `list <type>` | All nodes of a given type (goal, decision, idea, ...) |
| `path <a> <b>` | Shortest path between two nodes |
| `ingest <file.md>` | 5-stage LLM pipeline: extract → validate → review → merge → eval |
| `check --provenance` | Flag nodes with missing source citations |
| `export --ttl` | Emit Turtle/RDF |
| `viz` | Generate offline single-file HTML viewer |
| `state "<entry>"` | Append a mood/state entry (sidecar, not in main graph) |

## Offline / Local LLM Support

The ingest and check pipelines support Ollama as a backend — no Anthropic API key required:

```bash
python3 mygraph/mygraph.py ingest notes.md --backend ollama --model llama3
```

The core graph model (seed, summary, query, viz, export) is pure stdlib Python with no external deps.

## Design Principles

**Provenance first.** Every durable claim points back to a source document and a literal excerpt. If it can't be cited, it doesn't go in as high-confidence.

**Local first.** Your graph is a file on your machine. No cloud sync, no accounts, no telemetry.

**Boring persistence.** Plain JSON until it becomes the limiting factor. The schema stays stable across storage backends.

**Review before merge.** The LLM proposes. You decide. Deterministic validation runs before anything enters the graph.

## Repository Layout

```
mygraph/          Core CLI and pipeline modules (mygraph.py, ingest.py, viz.py, ...)
examples/         Demo graph: demo_graph.json, demo_graph.ttl, demo_graph.html
docs/             ROADMAP.md
ollama_proxy/     Adapter for local Ollama LLM backend
SPEC.md           Graph model specification
V1_DESIGN.md      Pipeline design
STRATEGY.md       Open-source launch strategy
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The core graph model is intentionally minimal — contributions that keep it that way are preferred over ones that add complexity.

## License

MIT
