# knowledge-worker

A provenance-backed personal knowledge graph toolkit.

`knowledge-worker` keeps durable concepts, decisions, goals, questions, and
sources in a small graph that can be queried from local AI workflows. The public
repo ships only code, docs, and a fictional demo graph. Private graph data should
stay outside git and be loaded with `MYGRAPH_PATH`.

## What It Does

- **Ingests your markdown files** (notes, journals, docs) → extracts structured nodes + edges via LLM
- **Builds a graph on Postgres** — no exotic graph DB, just boring reliable SQL
- **Validates every claim** against its source (no floating assertions)
- **Exports to OWL/RDF** for interoperability
- **Visualizes** as a force-directed interactive graph
- **Queries by concept** — find what you think about any topic, plus all connected reasoning

---

## Roadmap

The long-term phases and milestones for this project are documented in [ROADMAP.md](./ROADMAP.md).

The roadmap focuses on evolving the graph from a static memory store into a living cognitive substrate:
- automated ingestion
- retrieval + evals
- contradiction detection
- temporal reasoning
- provenance-aware memory continuity

## Architecture

Three principles. See `knowledge_worker_principles.md` for full reasoning.

**1. Boring persistence layer** — Postgres, not Neptune or graph DBs. Intelligence lives above the DB, not in it.

**2. Cold GPU / federated compute** — Older/idle GPU nodes connect opportunistically to any Postgres instance. Heterogeneous hardware. Async. Distributed. Like BitTorrent, but for inference.

**3. Emergent KG** — The knowledge graph grows from usage on Postgres. Not prescribed by schema upfront.

> *Chaos at compute. Boring at persistence.*

---

## System 1 / System 2 Cognition Map

The architecture maps to dual-process cognition (Kahneman / AAAI 2020):

| Layer | What it is | Brain analogy |
|---|---|---|
| Cold GPU nodes | ML inference, pattern-matching | System 1 / Reptilian |
| Postgres | Symbolic knowledge store, explicit facts | System 2 / Neocortex |
| Emergent KG | Common-sense bridge between the two | Limbic / associative |

---

## Measures of Success

The graph pays off when LLM responses improve *because* of it.

---

### 🔴 Without knowledge-worker context

> **Prompt:** *"What should I focus on for my next side project?"*

**Gemma (local):**
> *"Consider building a web app, mobile app, or contributing to open source. Pick something that interests you."*

**GitHub Copilot:**
> *"A good side project should align with your career goals and help you learn new skills."*

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
