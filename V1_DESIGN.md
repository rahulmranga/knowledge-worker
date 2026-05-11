# Rahul Brain — v1 Design

Read after `SPEC.md`. v1 turns the v0 schema into something that ingests real markdown and grows the graph honestly. Adds OWL as a sibling serialization. Adds discrete `check` mode.

---

## 1. Goal

> Point the script at a markdown file. It produces candidate nodes/edges with confidence and literal excerpts. Rahul reviews. Approved candidates merge. Every approve/reject becomes an eval signal.

Inputs we'll hit first, in order: `inspiration.md`, `cowin.md`, `~/Desktop/ideas/land_evaluation/*.md`, future Claude conversation exports.

The provenance-or-bust rule from v0 holds: **the LLM must produce a literal excerpt for every `high`-confidence candidate.** If it can't quote the source, the candidate is `low`-confidence at best.

---

## 2. Pipeline

```
markdown file
    │
    ▼
[1] Extract       LLM call, schema-constrained output → candidates.json
    │
    ▼
[2] Validate      jsonschema → reject malformed, demote ungrounded → validated.json
    │
    ▼
[3] Review        CLI presents each candidate; Rahul approves/rejects/edits
    │
    ▼
[4] Merge         idempotent, slug-based IDs, dedupe → graph updated
    │
    ▼
[5] Log           every approve/reject becomes an eval_record entry
```

Five stages, each replaceable. Stage 1 is the only place the LLM touches the graph. Everything downstream is deterministic.

---

## 3. The extractor

### 3a. Input contract

A single markdown file plus a `Source` declaration:

```
{
  "source_id": "source:land-evaluation-readme",
  "source_label": "land_evaluation/README.md",
  "source_path": "~/Desktop/ideas/land_evaluation/README.md",
  "ingested_at": "2026-05-09T..."
}
```

### 3b. Output contract (strict JSON)

```jsonc
{
  "source": { "id": "...", "label": "...", "body": "..." },
  "nodes": [
    {
      "id": "idea:slug-here",
      "type": "idea",
      "label": "short label",
      "body": "longer description, in plain prose",
      "confidence": "high|medium|low",
      "excerpt": "literal quote from the source (REQUIRED if confidence=high)"
    }
  ],
  "edges": [
    {
      "src": "idea:slug-here",
      "dst": "topic:knowledge-graphs",
      "type": "RELATES_TO",
      "confidence": "high|medium|low",
      "excerpt": "literal quote that justifies this edge"
    }
  ]
}
```

### 3c. The prompt (sketch, not final)

```
You are extracting nodes and edges for a personal knowledge graph centered on
Rahul. The graph stores durable concepts (Person, Idea, Project, Goal, Topic,
Reference, Question, Decision, Source) and relations between them.

Rules:
1. Every node and edge MUST cite a literal excerpt from the source. No paraphrase.
2. Use confidence "high" only when you have a direct quote.
3. Use confidence "medium" for clear paraphrase.
4. Use confidence "low" for inference. State the inference; quote what you inferred FROM.
5. Slug-style IDs: lowercase, hyphenated, type-prefixed. E.g. `idea:rahul-centered-graph`.
6. Reuse existing IDs when the candidate refers to a concept already in the graph
   (you will receive a list of existing IDs).
7. Do NOT invent biographical facts. If the source doesn't say it, it doesn't go in.
8. Output the JSON shape exactly. No prose, no commentary.

Existing node IDs (subset, for reuse):
{... list passed in at extract time ...}

Source markdown follows. Extract.
---
{... markdown ...}
```

### 3d. Choice of LLM

v1 uses Claude (or any frontier model with structured output). The prompt is the same; we don't fine-tune yet.

**v1.5 update (2026-05-09):** Local Gemma via Ollama is now a first-class extractor backend. Selection at ingest time:

```
python mygraph.py ingest <file.md> --backend claude   # default, frontier
python mygraph.py ingest <file.md> --backend ollama   # local Gemma (gemma4:e4b)
```

Implementation lives in `ollama_proxy/extractor_adapter.py` — drop-in replacement for `mygraph/extractor.py` that uses Ollama's structured-output mode (`format=<schema>`) instead of Anthropic tool-use. Same prompt, same output shape, same downstream pipeline. See §12.

---

## 4. Validation

`validated = validate(extracted)`:

- jsonschema check on the candidate JSON shape.
- Every node with `confidence == "high"` MUST have a non-empty `excerpt` that appears (substring match, normalized whitespace) in the source markdown. If the excerpt isn't actually in the source → demote to `low` and flag.
- Every edge MUST point to either an existing graph node ID or another candidate node from the same extraction. Orphan edges → reject.
- Every node ID MUST match `^[a-z]+:[a-z0-9-]+$`. Malformed → reject.

Validation outputs a manifest of: accepted, demoted-with-reason, rejected-with-reason. Rejections are logged but never silently dropped.

---

## 5. Review CLI

```
python rahul_brain.py ingest ~/Desktop/ideas/land_evaluation/README.md
```

For each candidate, terminal shows:

```
[idea] idea:land-eval-as-llm-test-case
  label: land_evaluation as v1 extractor test case
  body : Use the land_evaluation idea folder as the first non-trivial corpus...
  confidence: medium
  excerpt: "this is also an idea/inspiration"

[ a ] accept   [ r ] reject   [ e ] edit   [ s ] skip   [ q ] quit
>
```

Edit pops `$EDITOR` on the candidate JSON. Idempotent — re-running on the same source skips already-merged candidates (by ID).

---

## 6. Merge

- Stable IDs → `add_node` / `add_edge` are already idempotent per v0.
- If a candidate node has the same ID as an existing node but a different `body`, we **don't overwrite silently**. We surface the diff and ask: keep old, replace, or merge into a longer body. This becomes a `decision` node-level event we can log.
- New `Source` nodes always merge cleanly.

---

## 7. Eval logging

Every review action writes a line to `eval_record.jsonl`:

```jsonc
{ "ts": "2026-05-09T...", "kind": "review", "candidate_id": "idea:...",
  "verdict": "accept|reject|edit|skip", "source_id": "source:...",
  "extractor_confidence": "medium", "user_edit": null }
```

This file is the **training corpus**. v1 doesn't train anything; it builds the corpus. v2+ uses it.

---

## 8. OWL migration (v1, sibling serialization)

JSON stays canonical. OWL is generated from JSON at any time (and re-imported for round-tripping).

```
rahul_brain.json   ─┐
                    ├──>  rahul_brain.ttl   (Turtle)
                    └──>  rahul_brain.owl   (OWL/XML, optional)
```

Mapping:

| v0 concept | OWL form |
|---|---|
| Node type (`idea`, `project`, etc.) | OWL Class under `rb:Concept` |
| Edge type (`HAS_IDEA`, `RELATES_TO`, etc.) | OWL ObjectProperty |
| Node `id` | IRI under namespace `<http://rahul-brain.local/>` |
| `label`, `body` | rdfs:label, rdfs:comment |
| `confidence`, `excerpt`, `source_id` on edges | reified statements (one rb:Assertion per edge, with provenance properties) |
| `Source` node | rb:Source (subclass of dcterms:ProvenanceEntity) |

Tools:
- **rdflib** for read/write.
- **WebVOWL** or **Protégé** for visualization (open the `.ttl`).
- A reasoner is not on the critical path; we add one only when consistency-checking pays off (v2+).

The migration script is one file: `owl_io.py` with `to_turtle(graph)` and `from_turtle(path)`. Round-trip test required.

---

## 8a. Audit ingestion as canonical eval source

External tools that query the graph (GH Copilot, ChatGPT, another Claude session, future agents) can produce response audits — like `copilot_response_audit.md` from this session. Treat these as **first-class eval sources**:

- Each audit ingests as a `Source` node.
- Each Q&A pair produces an `eval_record` entry with `kind: external_query`, the question, the model's response, the model's self-evaluation, and *our independent verdict* (computed by comparing the response against the graph).
- Independent verdicts catch failures the model's own self-eval misses (e.g., uncited confidence levels, incomplete neighbor sets, missed `low`-confidence references).
- The verdicts feed the same training-signal stream as continuous + discrete modes.

This is how external tools become evaluators of our graph instead of just consumers — every external-query log is a free dataset. First test case: ingest `copilot_response_audit.md` and produce eval_records for its 8 Q&As, including the misses Claude flagged (no confidence labels surfaced, Q8 incomplete, Q5 paraphrase treated as quote).

---

## 9. Discrete `check` mode

```
python rahul_brain.py check          # run all checks, append to eval_record.jsonl
python rahul_brain.py check --pairs 10
python rahul_brain.py check --provenance
python rahul_brain.py check --stale-edges
```

Checks:

- **Provenance scan.** Hard invariant. Any node without a `MENTIONED_IN`, any edge without a `source_id` → log as `eval_record` with `kind: provenance_violation`. These should be zero. Non-zero = bug.
- **Stale-edge scan.** Edges older than N days with no recent reinforcement → flag with `kind: stale_candidate`. User reviews next session.
- **Random-pair relational probe.** Pick two random non-adjacent nodes; ask Claude (via API) "is X related to Y? if yes, by what predicate?" Log Claude's answer + confidence. User verdicts asynchronously.
- **Source candidacy scan.** Read recent Claude conversation exports; ask: "is this a Source we should ingest? What candidate Sources does it imply?" Log `kind: source_candidate`.

All output is **discrete records** in `eval_record.jsonl` — never written into the main graph until reviewed.

---

## 10. v1 success criterion

Two things, in order:

1. `python rahul_brain.py ingest ~/Desktop/ideas/land_evaluation/README.md` produces ≥5 candidate nodes. You accept ≥1. The graph grows. The accepted node has a literal excerpt back to the source. **Rahul says: "yeah, this caught what I'd want caught."**
2. `python rahul_brain.py check --provenance` returns zero violations on the post-merge graph.

If both pass, v1 is done. Move to v1.5 (OWL sibling) and v2 (embeddings) separately.

---

## 11. Scope discipline

What's in v1: extractor, validator, review CLI, merge, eval log, OWL serialization, `check` mode.

**v1.5 additions (in scope):** local Gemma backend via Ollama (`ollama_proxy/`), MCP wrap for Claude/Cowork consumption, logging passthrough proxy for AnythingLLM, Tailscale exposure runbook, Claude vs Gemma A/B comparison logger.

What's still out: vector embeddings, automated nightly ingest (v3), any UI beyond the existing viz, any RL training, any model fine-tuning, per-user auth on the proxy (tailnet ACL only), rate limiting. The `eval_record.jsonl` corpus *enables* those — it doesn't *do* them yet. Earn each one.

---

## 12. v1.5 — Local inference + remote access

### 12a. Goal

> Same five-stage pipeline. Swap the extractor LLM at the flag. Reach the model from any device on the tailnet without standing up a public surface.

### 12b. Components

| File | Purpose | Consumer |
|---|---|---|
| `ollama_proxy/server.py` | MCP server wrapping Ollama. Tools: `chat`, `generate`, `list_models`, `embed`. | Claude Code, Cowork, any MCP client |
| `ollama_proxy/proxy.py` | Logging HTTP passthrough in front of Ollama (default :11435 → :11434). | AnythingLLM, raw Ollama-API clients |
| `ollama_proxy/extractor_adapter.py` | Drop-in for `mygraph/extractor.py`. Uses Ollama `format=<schema>` for constrained JSON. | `mygraph/ingest.py --backend ollama` |
| `ollama_proxy/eval_compare.py` | Runs Claude + Gemma on the same source. Appends `kind:extractor_comparison` to `eval_record.jsonl`. | Manual A/B; cron later |
| `ollama_proxy/tailscale.md` | Tailscale `serve` runbook + ACL guidance. | Operator |

### 12c. Auth

Tailnet ACL only. No bearer tokens, no mTLS, no funnel. The threat model is "my devices on my tailnet" — Tailscale's identity is the auth boundary.

### 12d. Default model

`gemma4:e4b`. Override per-call (`--model`) or per-process (`OLLAMA_DEFAULT_MODEL`).

### 12e. Why MCP *and* a passthrough proxy

They serve different consumers. MCP is JSON-RPC tool-use for Claude/Cowork; AnythingLLM and most LLM clients speak Ollama's REST API directly. One surface for each. They share Ollama as the backend; they don't share each other.

### 12f. v1.5 success criterion

Three gates:

1. `python mygraph.py ingest ../inspiration.md --backend ollama --non-interactive` produces ≥5 candidates with no Python exceptions.
2. `python ollama_proxy/eval_compare.py ../inspiration.md` writes a single `kind:extractor_comparison` record showing both sides ran and a Jaccard score on shared node IDs.
3. From a different tailnet device: `curl https://<host>.<tailnet>.ts.net:11435/healthz` returns `{"ok": true, ...}`.

All three must pass. v1.5 is done when they do.
