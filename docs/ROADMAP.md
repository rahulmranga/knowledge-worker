# Public Roadmap

## v0.3: Directed Memory Audit And Benchmarks (shipped)

- Emit `analytics.json` with PageRank, betweenness, k-core, communities,
  low-confidence edges, provenance coverage, and directed idea-flow queues
  through `mykg audit`.
- Add a Memory Audit HTML view with ranked panels before the graph canvas:
  important concepts, bridge ideas, weak claims, proof trail, and legwork
  queues.
- Publish `docs/COMPETITIVE_ANALYSIS.md` and `docs/BENCHMARKS.md`.
- Add offline benchmark tests over `examples/demo_graph.jsonld`.

## v0.4: Discovery Layer (shipped)

- Add `mykg discover`: derived-edge proposals and second-order analytics on top
  of the audit layer.
- Keep every inference a proposal: discover never mutates the graph; output goes
  to a promotion queue for human review.
- Expand the fictional demo graph so discovery has stale, weak, bridge, and
  tension examples to surface.

## v0.5-v0.6: Packaging And Context Surfaces (shipped)

- Package the CLI as `knowledge-worker` with `mykg` and `mygraph` entrypoints.
- Keep the core graph CLI stdlib-only, with optional extras for RDF and LLM
  extraction backends.
- Support context export, offline visualization, local Ollama adapter surfaces,
  and public-demo-safe graph fixtures.

## v0.7: Deep-Dive Interaction Model And Workspace

- Add `mykg deep-dive` as a pre-ingest workspace generator:
  artifacts, artifact plan, manifest, validation report, artifact-local graph
  summary, and canonical candidates.
- Add `mykg deep-dive inspect <workspace>` for reviewable workspace summaries.
- Add `mykg deep-dive add-to-graph <workspace>` as a wrapper over existing
  ingest validation/review/merge.
- Document the product interaction model: generate, inspect, challenge,
  add-to-graph, approve, and don't-ingest-yet.
- Keep `ingest` as the canonical graph mutation path.

## v0.8: Open-Web Storage Contract

- Keep JSON-LD as the canonical local graph store.
- Use JSONL for append-only review/eval/event history.
- Keep legacy JSON graph files readable for migration.
- Ship Turtle/RDF export as the semantic-web sibling to JSON-LD storage.
- Document Kuzu as a future optional read/query backend and graphify.net as a
  future publishing or interchange target, not as v0.8.0 storage dependencies.
- Keep the core graph CLI stdlib-only except for optional RDF export extras.
- Preserve provenance checks, public-demo safety, and private-by-default graph
  loading as release gates.

## v0.9: Memory Analyzer Layer

- Combine audit, context export, discovery, and deep-dive outputs into a single
  user-facing memory analyzer report.
- Summarize what the graph knows, what it can prove, what it should review, and
  which candidates are ready for promotion.
- Improve edge-review ergonomics so relationships can be accepted, rejected, or
  edited as first-class reasoning claims.
- Add evals for analyzer usefulness on the public demo graph.

## v1: Public Demo And Local Graphs

- Keep the repo public-demo safe with fictional graph data only.
- Load private graphs through `MYGRAPH_PATH` or explicit CLI flags.
- Generate offline HTML viewers with embedded graph JSON.
- Keep provenance checks at zero violations.

## v2: Storage Evolution

- Move from JSON-LD persistence to optional database-backed read models only
  when graph size, query ergonomics, or concurrency makes JSON awkward.
- Prefer adapters that preserve the public node/edge schema, CLI behavior,
  provenance invariants, and local-first/private-by-default workflow.
- Explore Kuzu for local graph analytics after JSON-LD, JSONL, and Turtle/RDF
  contracts are stable.
