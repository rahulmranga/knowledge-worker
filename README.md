# knowledge-worker

Personal knowledge graph that survives between Claude conversations.
User-centered (not conversation-centered). Provenance-or-bust.

---

## Architecture (as of 2026-05-10)

Three principles captured: See `knowledge_worker_principles.md` for full reasoning.

**1. Boring persistence layer** — Postgres, not Neptune or graph DBs. Intelligence lives above the DB, not in it.

**2. Cold GPU / federated compute** — Older/idle GPU nodes connect opportunistically to any Postgres instance. Heterogeneous hardware. Async. Distributed. Like BitTorrent, but for inference.

**3. Emergent KG** — The knowledge graph grows from usage on Postgres. Not prescribed by schema upfront.

> Chaos at compute. Boring at persistence.

---

## Framing (from AAAI 2020 + Kahneman)

The architecture maps to System 1 / System 2 cognition:

| Layer | What it is | Brain analogy |
|---|---|---|
| Cold GPU nodes | ML inference, pattern-matching | System 1 / Reptilian |
| Postgres | Symbolic knowledge store, explicit facts | System 2 / Neocortex |
| Emergent KG | Common-sense bridge between the two | Limbic / Sonnet territory |

---

## Files

- `SPEC.md` — schema, node/edge types, anti-slop rules. Read first.
- `V1_DESIGN.md` — v1 build plan (LLM extractor → validation → review → merge → eval log → OWL).
- `knowledge_worker_principles.md` — the three principles + why. The north star.
- `V1_PLAN.md` — implementation roadmap.
- `AGENTS.md` — agent design.
- `midnight_journal.md` — raw 3am captures. Source of truth for ideation.
- `rahul_brain.py` — v0 implementation (stdlib only, JSON-backed).
- `rahul_brain.json` — the graph (created on `seed`).

---

## Run

All commands run from `mygraph/`:

```bash
cd mygraph/

python mygraph.py summary                        # stats overview
python mygraph.py query "postgres"               # search nodes + neighbors + provenance
python mygraph.py path goal:green-card project:rahul-brain
python mygraph.py dump                           # raw JSON

# Ingest a new markdown file into the graph
python mygraph.py ingest <file.md> --auto-accept-high   # requires ANTHROPIC_API_KEY
python mygraph.py ingest <file.md> --candidates-file <hand-curated.json> --auto-accept-all

python mygraph.py export --ttl                   # emit mygraph.ttl (RDF)
python mygraph.py viz                            # open force-directed HTML graph
```

---

## Status

- **v0:** shipped — started at 43 nodes / 71 edges (rahul_brain.py, JSON-backed, stdlib only).
- **v1:** live in `mygraph/` — 91 nodes / 170 edges as of 2026-05-10. Ingest pipeline, validator, OWL export, viz.
- **v2 (vision):** cold GPU nodes connecting to Postgres. Federated, async, heterogeneous.

---

## Core Rule

Every node points to a Source. No floating claims. If it can't be quoted, it's not in the graph.
