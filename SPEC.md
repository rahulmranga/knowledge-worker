# mygraph — v0 Spec

A personal knowledge graph that survives between Claude conversations.
Tonight's job: make a v0 that runs, holds a few real nodes about Rahul, and answers "what do I know about X?" with provenance.

---

## 1. The pivot that makes this not-AI-slop

Most "personal AI memory" projects index *conversations*. They store chat logs, embed them, and retrieve nearest-neighbor chunks. The problem: conversations are episodes, not concepts. You don't want "the chunk where I mentioned H1B." You want **what you currently think about H1B, what's still open, what you've decided, and which conversation got you there.**

So this graph is **Rahul-centered, not conversation-centered**.

- Nodes are *durable things*: ideas, projects, people, decisions, open questions, goals.
- Conversations and documents are **Sources** — they're the evidence trail, not the content.
- Every node points back to at least one Source. No floating claims.

This is the spine. If we hold this rule, the system is honest by construction. If we let it drift into "vibes from a chat log," it becomes the kind of memory product that hallucinates a personality at you and calls it *you*.

---

## 1.5 Architectural layers (high-level frame, before types)

Per Rahul's neuron / neural-net framing — nodes carry the load, edges thicken or thin with use, and there are layers above and beneath the concept layer that matter as much. Naming the layers up front, so §2 doesn't pretend to be the whole picture:

| Layer | What lives here | Where it shows up |
|---|---|---|
| **Substrate** | Sources — conversations, documents, journal entries. Append-only. | §2 (`Source` node type) |
| **Concept** | Person, Idea, Project, Goal, Topic, Reference, Question, Decision. The durable Rahul-stuff. | §2 |
| **Relation** | Edges between concepts; predicates that name *how*. Predicates may matter as much as nodes — they prune too. | §2, §5 pruning track |
| **Annotation** | Confidence, timestamps, `last_seen`, decay score. Per-node and per-edge metadata that drives pruning and eval. | §2, §5 pruning track |
| **Pruning / decay** | Rules + processes for ageing-out stale references and edges. The graph must shrink, not just grow. | §5 pruning track |
| **Eval / feedback** | In-conversation prompts: "is X related to Y?", "I surfaced this — does it make sense?" Failures become training signals. | §6 |
| **Sidecar** | Parallel graphs (Emotion / State), kept *separate* from the concept graph. Rahul supplies. Mined for cross-graph patterns later. | §5 sidecar track |
| **Visualization** | Ontology / RDF viewer — day-1 you should *see* the graph, not just CLI it. | §5 visualization track |

§2 fills in the Concept and Relation layers as a v0 minimum. The other layers get treatment in §5 (roadmap) and §6 (eval).

---

## 2. Schema (v0)

I believe an ontology viewer (RDF) would be useful here. 

### Node types

| Type | What it is | Example |
|---|---|---|
| `Person` | A human (you, family, colleagues, friends, public figures referenced) | Rahul, Saumya Shikhar, Dad |
| `Topic` | A domain or area of interest | H1B, Knowledge Graphs, Flow theory, Taxes |
| `Idea` | A specific claim, thesis, or thought *you* hold | "KG + RAG + small FT can mimic a knowledge worker" |
| `Project` | A thing you are building or have built | Rahul Brain, CoWIN email notifier |
| `Goal` | A longer-term aim | Green card, Entrepreneurship, Live in flow |
| `Question` | An open thread you haven't resolved | "Do I publish on Medium or in a venue?" |
| `Decision` | A stance you've taken (date-stamped) | "Build the v0 in plain JSON, not Kùzu, for tonight" |
| `Reference` | A paper, link, book, podcast | CogGRAG (arXiv:2503.06567), Csikszentmihalyi flow |
| `Source` | A conversation export, document, or note | `inspiration.md`, `cowin.md`, `2026-05-08-claude-chat` |

### Edge types

| Edge | From → To | Meaning |
|---|---|---|
| `HAS_IDEA` | Person → Idea | this person holds this idea |
| `RELATES_TO` | Idea/Project → Topic | this is about that |
| `SUPPORTED_BY` | Idea → Reference | citation / evidence |
| `CHALLENGES` | Idea → Idea | this contradicts that |
| `SERVES` | Project → Goal | this exists in service of that |
| `INVOLVES` | Project → Topic/Person | this project touches that |
| `ABOUT` | Question → Topic | this question concerns that |
| `MENTIONED_IN` | any node → Source | provenance — *this* came from *here* |
| `MADE_AT` | Decision → Source | when/where the decision was recorded |

Every node MUST have at least one `MENTIONED_IN` edge. That is the anti-slop guard.

### Node fields (minimum)

```
id          (string, stable, e.g. "idea:kg-rag-ft-knowledge-worker")
type        (one of the node types above)
label       (short human-readable name)
body        (optional longer description, in your own words)
created_at  (ISO timestamp)
confidence  (high | medium | low — high if direct quote, low if inferred)
```

### Edge fields (minimum)

```
src         (node id)
dst         (node id)
type        (one of the edge types)
source_id   (the Source node id this edge was extracted from)
confidence  (high | medium | low)
```

---

## 3. Anti-slop principles

These are the rules the system enforces so the graph stays honest.

1. **No node without a Source.** If we can't trace it to something you wrote or said, it doesn't go in.
2. **Confidence is required.** Every node and edge carries a confidence label. `high` = literal quote. `medium` = clear paraphrase. `low` = LLM inference. We surface confidence when we query.
3. **Quotes preserve original wording.** If a node says "Rahul thinks X," there is a stored excerpt from the source proving it. No remixing.
4. **Idempotent ingest.** Re-running ingest on the same source doesn't duplicate nodes. Stable IDs (slug-based) enforce this.
5. **The graph belongs to you.** Local file. No external service required. You can `cat mygraph/mygraph.json` and read it.
6. **Safety and privacy by default.** The graph holds real claims about you and people you know. It stays local, is never pushed remote without an explicit `--export` + redaction step, and is `.gitignore`'d in any repo by default.
7. **Recurring feedback over redesign.** When recall or connection-discovery misses, that's a *training signal*, not a redesign trigger. Failures are recorded as `eval_miss` records, used to refine extraction prompts, weight edges, or (later) feed RL. Schema redesign is reserved for failures that repeat at the schema level.

---

## 4. v0 scope (shipped)

What's in the box:

- `mygraph/mygraph.py` — single-file core (stdlib only). _Renamed from `rahul_brain.py`._
- A JSON-backed graph store (`mygraph/mygraph.json`).
- `seed()` populates Rahul's first nodes from: this conversation, `inspiration.md` (now also a formal Source `source:inspiration-md-file`), `cowin.md`.
- `query(topic_or_node_label)` → node + neighbors + provenance.
- `summary()` prints stats.
- CLI: `python mygraph/mygraph.py {seed|summary|query|path|dump|reset}`.

v1 extends the same CLI with `ingest`, `check`, `export --ttl`, and `viz`. See `V1_DESIGN.md` and `V1_PLAN.md`.

What's explicitly **out** of v0 (and that's fine):

- Auto-extraction from raw markdown — that's v1.
- Embeddings / vector search — v2.
- A web UI or graph visualization — later.
- RL or fine-tuning — possibly never. Earn it.
- Multi-user, sync, cloud — not on the roadmap.

---

## 5. Roadmap

**v0 — Tonight**: manual seed, JSON store, query with provenance. Proves the schema holds Rahul's real nodes without strain.

**v1 — Next session**: LLM-powered extraction. Point the script at a markdown file (`inspiration.md`, a Claude conversation export, a journal entry). It produces candidate nodes/edges with confidence scores. You approve before merge. Crucially: extraction must produce direct quotes, not summaries.

**v2**: Embedding layer over node `body` text. Enables semantic queries ("what's adjacent to flow theory in my thinking?"). Still local — sentence-transformers or similar.

**v3**: Auto-ingest pipeline. A folder you drop conversation exports into; a script that ingests new ones nightly. Diff view of what changed.

**v4**: Query interface — could be CLI with rich output, or a small web view (single HTML page reading the JSON). Whatever earns its keep.

**v5+**: *Only if* v0–v4 hit a clear ceiling — adapter fine-tuning on your own writing for "Rahul-voice" outputs, or RL over the graph for retrieval policies. Brain analogies are a hook, not a roadmap.

### Cross-cutting tracks (run alongside versions, not in sequence)

- **Pruning track.** From v1: every node and edge gets `last_seen` and a `decay` score. References that haven't been touched in N days get a low-confidence flag; old `CHALLENGES` edges that are no longer in tension can be pruned (manually first, then policy-driven). **Predicates (edge types) age out too** — a predicate that no edge instances use for X months is a candidate for retirement. Pruning is not a v4 concern; it's a v1 architectural concern, because a graph that only grows is a graph that lies.
- **Visualization track.** From v1 minimum: an ontology / RDF viewer or simple force-directed graph view. The whole point of a graph is being able to *see* it. CLI output is for debugging, not understanding.
- **Sidecar track (Emotion / State).** A separate, parallel store for state annotations (energy, context, time-of-day, mood). Kept off the main concept graph by design — Rahul supplies these manually. Mined later for cross-graph patterns ("which kinds of ideas land at midnight on coffee, vs at 9am after sleep").

---

## 6. Evaluation — how we know it works

Three concrete tests, plus a continuous mode.

1. **Self-recall (human + AI vibe check).** Query `"H1B"`, get back nodes you'd actually want surfaced. Both Rahul and Claude weigh in independently — *disagreement is itself a signal worth logging.*

2. **Provenance integrity (hard invariant).** Pick 5 random nodes. Each must trace to a literal excerpt in a Source. **If 2 fails, the system is broken** — this is a bug, not training data. Provenance is the spine; no amount of RL fixes a broken spine.

3. **Connection discovery.** Ask the graph "what connects Goal:GreenCard to Project:RahulBrain?" Does it find a path you'd nod at?

Eval runs in **two modes**, both feeding the same training-signal stream:

**Continuous mode (in-conversation, real-time).** During any working session, the system / Claude surfaces small prompts:
- "Is X related to Y?" — relational check.
- "I surfaced this node when you mentioned Z. Does it still make sense?" — drift / staleness check.
- "These two ideas are now in tension. Keep both, prune one, or merge?" — pruning prompt.

**Discrete mode (offline, scheduled or on-demand).** A `python mygraph/mygraph.py check` command runs — periodically or via cron — and produces a structured `eval_record.jsonl` log (one JSON line per check). It covers:
- Provenance integrity scan (every node has a Source; every edge has a `source_id`). Hard invariant.
- Stale-edge detector (edges older than N days without reinforcement → flagged for prune review).
- Random-pair relational probe ("is X related to Y?" — Claude answers, user verdicts later).
- "How did Claude respond — is any of this a Source we should ingest?" — Claude reviews recent transcripts and flags candidate Sources.

Output is **discrete records**, not noise in the main graph. The two modes feed the same `eval_record.jsonl` log, which becomes the corpus for v1 extraction-prompt refinement, edge-weight updates, and (eventually) any RL training.

Failures on (1), (3), and on continuous-mode prompts are **training signals**, not redesign triggers. Schema redesign is reserved for failures of the *same shape* that repeat — i.e., the schema itself can't represent what's needed.

---

## 7. Open questions for you to redline

- **Storage layer.** **Decided** (2026-05-08): JSON + schema validation for v0; **OWL is the v1 target** (Rahul: *"Yes v1"*). Kùzu is out (property graph DB, wrong tool for OWL anyway). Repos to evaluate against during v1: github.com/Lum1104/Understand-Anything, github.com/safishamsi/graphify. v1 design lives in `V1_DESIGN.md`.
- **Emotion / State as node types.** Decision: **separate sidecar graph**, not in the main concept graph. Rahul supplies state annotations. Cross-graph patterns mined later, without polluting the durable concept graph. (See sidecar track in §5.)
- **Reference auto-fetch metadata.** Defer. Pruning before fetching — a graph that auto-grows but never shrinks is the same problem the whole project exists to avoid.
- **Privacy.** Folded into Principle #6 in §3. `--redact-people` flag earned its place on the v3 export work.

---

## 8. Tonight's success criterion

You run `python mygraph/mygraph.py seed` and `python mygraph/mygraph.py query "knowledge graph"`. The output makes you say "yeah, that's roughly what I'm thinking, and I see the threads." That's it. Then you sleep.

_(Criterion met 2026-05-08. v0 is done.)_

---

## 9. Resolved decisions + remaining threads

**Resolved this session (2026-05-08):**

- **`land_evaluation` (idea/inspiration).** Lives at `~/Desktop/ideas/land_evaluation`. Rahul: *"this is also an idea/inspiration. I changed the folder structure for you but mostly for ME!"* Treated as both: (a) a Source folder we ingest from at v1, and (b) an Idea node in the graph — "apply Rahul-Brain methodology to land_evaluation." Folder access requested via `request_cowork_directory`; v1 ingester will read it.
- **OWL: v1, not v0.** Rahul: *"Yes v1."* v0 stays JSON + schema validation; v1 adds OWL serialization alongside automated extraction. See `V1_DESIGN.md`.
- **Continuous + discrete eval.** Rahul: *"Both."* In-conversation prompts during sessions, plus an offline `python mygraph/mygraph.py check` mode producing discrete `eval_record.jsonl` records. Both feed the same training-signal stream. See §6.
- **Predicates are first-class.** Captured in §1.5 (Relation layer) and §5 (pruning track). Predicate retirement is a real op, not a theoretical one.

**Resolved 2026-05-09:**

- **File rename.** `rahul_brain.py` → `mygraph/mygraph.py`, `rahul_brain.json` → `mygraph/mygraph.json`. Old files still present in the folder (mount prevents deletion) — delete manually.
- **Permanent home decided.** Project lives at `~/Desktop/ideas/Midnight idea - Knowledge worker/`. Docs at root; code + data in `mygraph/` subfolder.

**Remaining threads:**

- Visualization tool choice: WebVOWL, Protégé, custom force-directed view, or one of the repos in §7. Decide during v1 M4 work.
- `rahul_brain.py` and `rahul_brain.json` in `mygraph/` — delete manually when convenient.
