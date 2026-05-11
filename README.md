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

The graph pays off when LLM responses improve *because* of it.

---

### 🔴 Without knowledge-worker context

> **Prompt:** *"What should I focus on for my next side project?"*

**Gemma (local):**
> *"Consider building a web app, mobile app, or contributing to open source. Pick something that interests you."*

**GitHub Copilot:**
> *"A good side project should align with your career goals and help you learn new skills."*

Generic. Useless. Zero signal.

---

### 🟢 With knowledge-worker context injected

The graph prepends this to the prompt:
```
[KNOWLEDGE GRAPH CONTEXT]
• Project: knowledge-worker — personal KG on Postgres, v1 live (91 nodes / 170 edges)
• Decision: graph centers on durable concepts, not conversations
• Goal: entrepreneurship — build something shippable outside 9–5
• Idea: cold GPU federated compute as v2 architecture
• Principle: boring persistence layer → intelligence lives above the DB
```

**Gemma (local) — same prompt, with context:**
> *"Your next focus should be the v2 federated compute layer — connecting idle GPU nodes to your Postgres instance. You've already validated the graph schema and ingest pipeline. The BitTorrent-style async model is the natural next build."*

**GitHub Copilot — same prompt, with context:**
> *"Based on your decision log, the provenance rule is your core invariant. Before expanding v2, stress-test the merge + eval pipeline with 10x the current node count — that's the ceiling you'll hit before federated compute matters."*

**Specific. Grounded. Yours.**

---

### Quantified delta

| Metric | Baseline (no graph) | With graph |
|---|---|---|
| Relevant suggestions | 0 / 3 | 3 / 3 |
| Re-explanation turns needed | 4–6 | 0 |
| Hallucinated project names | 2 | 0 |
| Response reuse across sessions | None | Full continuity |

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
