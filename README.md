# knowledge-worker

**A personal knowledge graph that survives between AI conversations.**  
User-centered (not conversation-centered). Provenance-or-bust. Built on boring infrastructure.

> *Your AI is only as smart as what it remembers about you.*

---

## Why This Exists

Every AI assistant forgets you the moment the conversation ends. You re-explain context. You re-teach preferences. You lose the thread.

`knowledge-worker` fixes this. It maintains a structured, provenance-backed knowledge graph about *you* — your projects, goals, decisions, and reasoning — and injects it as context into any LLM session. The result: an AI that picks up exactly where you left off.

---

## What It Does

- **Ingests your markdown files** (notes, journals, docs) → extracts structured nodes + edges via LLM
- **Builds a graph on Postgres** — no exotic graph DB, just boring reliable SQL
- **Validates every claim** against its source (no floating assertions)
- **Exports to OWL/RDF** for interoperability
- **Visualizes** as a force-directed interactive graph
- **Queries by concept** — find what you think about any topic, plus all connected reasoning

---

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

The graph pays off when LLM responses improve *because* of it. Concrete benchmarks:

### 1. Context-injected vs. baseline response quality
Run the same query through **Gemma** (local, no context) and **GitHub Copilot** (no personal context) — then re-run with the knowledge graph context prepended. Score on:
- Factual accuracy vs. your actual stated beliefs/decisions
- Relevance to your current projects and goals
- Reduction in re-explanation turns needed

### 2. Conversation continuity
Measure how many turns before the model "forgets" who you are, vs. with graph context injected. Target: zero re-introductions across sessions.

### 3. Graph density over time
```
v1 baseline:  91 nodes / 170 edges
target:      500 nodes / 1000+ edges
provenance:  100% (no floating claims — ever)
```

---

## Run

All commands from `mygraph/`:

```bash
cd mygraph/

python mygraph.py summary                          # stats overview
python mygraph.py query "postgres"                 # search nodes + neighbors + provenance
python mygraph.py path goal:green-card project:knowledge-worker
python mygraph.py dump                             # raw JSON

# Ingest a markdown file into the graph
python mygraph.py ingest <file.md> --auto-accept-high        # requires ANTHROPIC_API_KEY
python mygraph.py ingest <file.md> --candidates-file <hand-curated.json> --auto-accept-all

python mygraph.py export --ttl                     # emit mygraph.ttl (RDF/OWL)
python mygraph.py viz                              # open force-directed HTML graph
```

**Requires:** `ANTHROPIC_API_KEY` env var for ingest/check steps.

```bash
pip install -r mygraph/requirements.txt
```

---

## Files

| File | Purpose |
|---|---|
| `SPEC.md` | Schema, node/edge types, anti-slop rules. Read first. |
| `V1_DESIGN.md` | v1 build plan (LLM extractor → validation → review → merge → eval log → OWL) |
| `knowledge_worker_principles.md` | The three principles + why. The north star. |
| `V1_PLAN.md` | Implementation roadmap |
| `AGENTS.md` | Agent design |
| `inspiration.md` | GraphRAG + RL research grounding |
| `mygraph/` | All runnable code |

---

## Status

| Version | State | Notes |
|---|---|---|
| v0 | ✅ shipped | JSON-backed, stdlib only, seed data — 43 nodes / 71 edges |
| v1 | ✅ live | 91 nodes / 170 edges. Ingest pipeline, validator, OWL export, viz |
| v2 | 🔭 vision | Cold GPU nodes + Postgres. Federated, async, heterogeneous |

---

## Research Grounding

- [CogGRAG (arXiv:2503.06567)](https://arxiv.org/abs/2503.06567) — Human cognition-inspired RAG, 86 citations as of May 2026
- [HippoRAG](https://arxiv.org/abs/2405.14831) — Neurobiological associative memory for LLMs
- Kahneman's dual-process theory (System 1 / System 2)

---

## Core Rule

Every node points to a source. No floating claims. If it can't be quoted, it's not in the graph.
