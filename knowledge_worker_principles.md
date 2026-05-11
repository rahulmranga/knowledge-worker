# Midnight Knowledge Worker — Principles

*Why this exists, what it believes, and how it thinks.*

---

## Principle 1 — The Boring Persistence Layer

**Capability:** Postgres as the single source of truth. No graph databases, no Neptune, no exotic RAG stores.

**Why:** Graph databases promise intelligent relationships but deliver operational complexity. The moment you need to iterate fast — at 3am, at a deadline, mid-insight — a complex persistence layer becomes a wall. Postgres is boring. That's the feature. Intelligence lives *above* the database, not inside it. You bring the smarts; the DB just holds truth.

> *Rapid iteration is only possible when your persistence layer is boring.*

---

## Principle 2 — Cold GPUs / Federated Compute

**Capability:** Older, idle GPU nodes connect opportunistically to any available Postgres instance — heterogeneous hardware, any size, distributed across machines.

**Why:** Top-tier hardware creates bottlenecks and costs. The brain doesn't run on uniform silicon — it has regions that go quiet, regions that spike, old pathways that rewire. Computation should mirror this: async, background, federated. Like BitTorrent, but for intelligence. Nodes don't need to trust each other — they only need to trust their Postgres connection. Consistency lives in the data layer. Compute can be chaotic.

> *Chaos at compute. Boring at persistence.*

The "sleep" phase is not downtime — it's background cognition. The system thinks while it rests.

---

## Principle 3 — Emergent Knowledge Graph

**Capability:** A general knowledge graph / brain model — but implemented on Postgres, not prescribed by a graph DB schema.

**Why:** A graph imposed by infrastructure is brittle. A graph that emerges from data is alive. The relationships between ideas, documents, and computations should grow from usage — not be architected upfront. The KG is a byproduct of thinking, not a prerequisite for it.

> *The graph is emergent, not prescribed.*

---

## Meta-Principle — Capture First, Architect Later

Human creativity in 3-4am windows cannot be recovered. The rare clarity of those hours is non-renewable. The right move is always to capture the idea fully, then architect it when the sun is up.

Rapid iteration beats architectural purity. Every time.

---

*First captured: 2026-05-10, ~3:30am*
