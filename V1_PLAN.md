# mygraph — v0 Audit + v1 Plan

_Generated: 2026-05-09. Read after SPEC.md and V1_DESIGN.md._

---

## Part 1 — v0 Audit

### Graph state
| Metric | Value |
|---|---|
| Nodes | 52 |
| Edges | 91 (87 original + 4 bug fixes this session) |
| Node confidence | 48 high / 3 medium / 1 low |
| Provenance violations | **0** (was 4 — fixed) |
| Edges missing source_id | 0 |

### v0 verdict
The spine will now hold. Provenance is now clean (0 violations). The schema carried real nodes without strain. The structural verifier proved the self-eval problem (D grade for Copilot's self-assessment) — external verifier is essential. **v0 is done. Proceed to v1.**

---

## Part 2 — v1 Plan

### North star (from `inspiration.md`)
The goal is a **CogGRAG-style knowledge worker**: not a search engine, but a system that decomposes queries, navigates associative paths in the graph, and self-verifies. The three CogGRAG stages map directly onto what v1 builds:

| CogGRAG stage | v1 equivalent |
|---|---|
| Decompose | Extractor breaks a markdown source into candidate nodes/edges |
| Retrieve | Existing graph + slug-based ID reuse = associative lookup |
| Self-verify | Validator + review CLI + check mode = dual-process verification |

RL rewards (outcome / process / efficiency) are v5+ — only after the retrieval and verification loops exist and have a training corpus. The eval_record.jsonl we're building now is that corpus.

---

### Milestones

---

#### M0 — Housekeeping _(do now)_

**Goal:** Clean state before building.

**Tasks:**
- [ ] **M0.1** Delete `rahul_brain.py` and `rahul_brain.json` manually (mounted fs blocks deletion from sandbox). Keep `mygraph.py` + `mygraph.json`. (and move it to ~/Desktop/ideas/Midnight idea - Knowledge worker)
- [ ] **M0.2** Permanent home for the project. Options: (a) `~/Desktop/ideas/Midnight idea - Knowledge worker/mygraph/` (current)
- [ ] **M0.3** Add `inspiration.md` as a formal `Source` node in the graph. It's referenced as the origin of CogGRAG/HippoRAG/Graph-R1 nodes but never formally ingested. One `add_node` call, one `MENTIONED_IN` edge from `reference:coggrag`.
- [ ] **M0.4** Update `SPEC.md` §4 to reflect the file rename (rahul_brain → mygraph).

**Success:** `python mygraph.py summary` shows 0 provenance violations; no stale filenames.

---

#### M1 — LLM Extractor Pipeline _(the big one)_

**Goal:** Point the script at markdown files → get candidate nodes/edges → review → merge → log. The 5-stage pipeline from V1_DESIGN.md §2.

**Tasks:**

- [ ] **M1.1 — Stage 1: Extractor**
  - Write `extractor.py` (or add `extract()` to `mygraph.py`).
  - Input: path to a markdown file + Source declaration.
  - LLM call (Claude API, structured output) using the prompt from V1_DESIGN.md §3c.
  - Output: `candidates.json` with `source`, `nodes[]`, `edges[]`.
  - Pass existing node IDs to the prompt so the LLM can reuse slugs instead of inventing new ones.
  - _Provenance rule_: every `high`-confidence candidate MUST include a literal `excerpt` field.

- [ ] **M1.2 — Stage 2: Validator**
  - jsonschema check on `candidates.json` shape.
  - Excerpt verification: for every `confidence == "high"` node, substring-match `excerpt` against the source markdown (normalized whitespace). Fail → demote to `low` and flag.
  - Orphan edge check: every edge `src`/`dst` must resolve to an existing graph node OR another candidate in the same extraction. Fail → reject.
  - ID format check: `^[a-z]+:[a-z0-9-]+$`. Fail → reject.
  - Output: manifest of accepted / demoted-with-reason / rejected-with-reason.

- [ ] **M1.3 — Stage 3: Review CLI**
  - Interactive terminal loop: for each candidate, print type / id / label / body / confidence / excerpt.
  - Keys: `[a]ccept`, `[r]eject`, `[e]dit` (opens `$EDITOR` on candidate JSON), `[s]kip`, `[q]uit`.
  - Idempotent: re-running on the same source skips already-merged node IDs.

- [ ] **M1.4 — Stage 4: Merge**
  - Idempotent `add_node` / `add_edge` (slug-based IDs, already v0).
  - Body-diff: if candidate ID matches existing node but body differs → surface diff, prompt: keep old / replace / append.
  - New Source nodes always merge cleanly.

- [ ] **M1.5 — Stage 5: Eval log**
  - Every review action (accept / reject / edit / skip) writes one line to `eval_record.jsonl`.
  - Fields: `ts`, `kind: "review"`, `candidate_id`, `verdict`, `source_id`, `extractor_confidence`, `user_edit`.

- [ ] **M1.6 — Wire CLI**
  - `python mygraph.py ingest <path/to/file.md>` runs all 5 stages end-to-end.

**First test targets (in order):**
1. `inspiration.md` — already in the workspace, CogGRAG/RL content, known ground truth.
2. `copilot_response_audit.md` — structured Q&A, will produce `eval_record` entries.
3. `~/Desktop/ideas/land_evaluation/resources/*.md` — first non-trivial corpus.

**Success (from V1_DESIGN.md §10):**
- `python mygraph.py ingest ~/Desktop/ideas/inspiration.md` produces ≥5 candidates. Rahul accepts ≥1. Accepted node has a literal excerpt back to the source.
- Rahul says: "yeah, this caught what I'd want caught."

---

#### M2 — Check Mode

**Goal:** Offline health-check that runs without LLM and catches graph rot before it accumulates.

**Tasks:**

- [ ] **M2.1 — Provenance scan** _(hard invariant)_
  - Every node (except `source`) must have a `MENTIONED_IN` edge. Non-zero = bug, not warning.
  - Every edge must have a `source_id`. Non-zero = bug.
  - Output: `eval_record` entries with `kind: "provenance_violation"`.

- [ ] **M2.2 — Stale-edge scanner**
  - Edges older than N days (configurable, default 90) with no `last_seen` reinforcement → flag as `kind: "stale_candidate"`.
  - Adds `last_seen` tracking to the edge schema (new field, non-breaking).

- [ ] **M2.3 — Random-pair relational probe**
  - Pick K random non-adjacent node pairs.
  - Ask Claude (API): "Is X related to Y? If yes, by what predicate?"
  - Log Claude's answer + confidence as `kind: "relational_probe"`. User verdicts asynchronously.
  - This is the semantic verifier — the part the structural verifier can't do.

- [ ] **M2.4 — Source candidacy scan**
  - Read recent Claude conversation exports in a configurable folder.
  - Ask: "Is this a Source we should ingest? What candidates does it imply?"
  - Log as `kind: "source_candidate"`. Never auto-ingest.

- [ ] **M2.5 — Wire CLI**
  - `python mygraph.py check` — run all checks, append to `eval_record.jsonl`.
  - `python mygraph.py check --provenance` — provenance only.
  - `python mygraph.py check --stale-edges` — stale-edge only.
  - `python mygraph.py check --pairs 10` — relational probe only.

**Success:** `python mygraph.py check --provenance` returns 0 violations on a freshly merged graph.

---

#### M3 — OWL Sibling Serialization

**Goal:** JSON stays canonical. Add a `mygraph.ttl` (Turtle) that any OWL viewer can open. Round-trip must be lossless.

**Tasks:**

- [ ] **M3.1** Install `rdflib` (only new non-stdlib dependency in v1).
- [ ] **M3.2** Write `owl_io.py` — two functions:
  - `to_turtle(graph) → str`: serializes all nodes and edges. Mapping per V1_DESIGN.md §8.
  - `from_turtle(path) → Graph`: round-trip import. Must produce the same node/edge count.
- [ ] **M3.3** Round-trip test: `mygraph.json → mygraph.ttl → reimport → compare`. Zero loss tolerance on nodes and edges.
- [ ] **M3.4** Wire CLI: `python mygraph.py export --ttl` → writes `mygraph.ttl`.
- [ ] **M3.5** Open `mygraph.ttl` in WebVOWL (web-based, no install) or Protégé. Confirm the ontology renders correctly. Screenshot → add to this doc.

**Key mapping (from V1_DESIGN.md §8):**

| JSON concept | OWL form |
|---|---|
| Node type | OWL Class under `rb:Concept` |
| Edge type | OWL ObjectProperty |
| Node `id` | IRI `<http://mygraph.local/node_id>` |
| `label`, `body` | `rdfs:label`, `rdfs:comment` |
| `confidence`, `excerpt`, `source_id` on edges | Reified statements (`rb:Assertion`) |
| Source node | `rb:Source` (subclass of `dcterms:ProvenanceEntity`) |

**Success:** `mygraph.ttl` opens in WebVOWL and shows the class hierarchy and property graph without errors.

---

#### M4 — Visualization

**Goal:** You can *see* the graph, not just CLI it. The whole point of a graph is being able to navigate it visually.

**Tasks:**

- [ ] **M4.1** Evaluate options (pick one):
  - **WebVOWL** (web, reads TTL from M3) — zero install, good for ontology view.
  - **Gephi** (desktop, reads JSON/GraphML) — better for force-directed layout.
  - **Custom force-directed HTML** — single `mygraph_viz.html` file using D3.js, reads `mygraph.json` directly. Most portable.
- [ ] **M4.2** Implement the chosen option. If custom HTML: nodes colored by type, edges labeled by predicate, click-to-inspect shows label + body + provenance.
- [ ] **M4.3** Wire CLI (if applicable): `python mygraph.py viz` opens the view.

**Success:** Rahul opens the graph and says "I can see my ideas."

---

### Sequencing

```
M0 (housekeeping)
    │
    ▼
M1 (extractor)  ←── biggest, most value, do this first
    │
    ├──▶  M2 (check mode)   ← run in parallel after M1 pipeline exists
    │
    └──▶  M3 (OWL)         ← run in parallel after M1 merge works
              │
              ▼
             M4 (viz)       ← depends on M3 for TTL, or standalone if custom HTML
```

M1 is the critical path. M2, M3, M4 can be picked up in any order after M1 ships.

---

### Cross-cutting rules for v1 (carry forward from SPEC)

1. **Provenance-or-bust holds.** Every candidate from the extractor that lacks a literal excerpt gets demoted to `low`, never silently accepted as `high`.
2. **The eval corpus grows every session.** Every approve/reject/edit in the review CLI writes to `eval_record.jsonl`. This is the training dataset for v2+.
3. **Pruning is a first-class concern from M1.** The stale-edge scanner in M2 is not an afterthought — build `last_seen` into the edge schema at M1.4 so decay tracking exists from the first merge.
4. **No auto-merge.** The review CLI is mandatory. The LLM proposes; Rahul disposes.
5. **File renames don't break the graph.** Slug-based node IDs are stable identifiers. The file can move; the IDs don't change.

---

### v1 success criterion (from V1_DESIGN.md §10)

Two gates, in order:

1. `python mygraph.py ingest ~/Desktop/ideas/inspiration.md` produces ≥5 candidate nodes. Rahul accepts ≥1. Accepted node has a literal excerpt traceable to the source. **Rahul says: "yeah, this caught what I'd want caught."**
2. `python mygraph.py check --provenance` returns **zero violations** on the post-merge graph.

Both must pass. Either alone is not enough.

---

### What v1 does NOT do (scope discipline)

- No vector embeddings (v2)
- No automated nightly ingest (v3)
- No RL training of any kind (v5+)
- No fine-tuning (v5+)
- No multi-user or cloud sync (not on roadmap)
- The `eval_record.jsonl` corpus _enables_ future training — it doesn't do it yet

---

### Open questions carried into v1

| Question | Status |
|---|---|
| Permanent home for the project (`ideas/` vs `projects/`) | Decide at M0 |
| Visualization tool choice (WebVOWL / Gephi / custom HTML) | Decide at M4.1 |
| RL reward shaping (outcome / process / efficiency per `inspiration.md`) | Deferred to v5+ — logged here for continuity |
| `reference:graph-r1` existence | Verify during M1 ingest of `inspiration.md` — if the paper doesn't exist, demote + flag |
| State sidecar implementation (manual log command) | v1.5 — after M1–M4 ship |
| Medium article timing | After v1 success criterion passes — the article is about what we built, not what we plan |
