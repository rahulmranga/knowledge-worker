# Public Roadmap

## v0.3: Directed Memory Audit And Benchmarks (shipped)

- Emit `analytics.json` with PageRank, betweenness, k-core, communities,
  low-confidence edges, and provenance coverage (`mykg audit`).
- Add a Memory Audit HTML view with ranked panels before the graph canvas:
  important concepts, bridge ideas, weak claims, and proof trail.
- Add directed idea-flow panels that separate idea attractors from idea
  generators.
- Turn weak claims into a user-reviewed queue: verify, downgrade, convert to a
  question, or ignore for now.
- Keep the audit read-only and prompt-driven so the user does the judgment work.
- Publish `docs/COMPETITIVE_ANALYSIS.md` with a source-checked category matrix.
- Publish `docs/BENCHMARKS.md` with offline demo-graph benchmarks.
- Add `tests/test_benchmarks.py` so benchmark checks run with no API key.
- Add README positioning that points readers to the analysis and benchmarks.

## v0.4: Discovery Layer (this release)

- Add `mykg discover`: derived-edge proposals and second-order analytics on top
  of the audit layer — staleness radar, co-mention inference, goal-alignment
  candidates, question debt, corroboration scoring, de-spined bridge detection,
  and tension detection.
- Keep every inference a *proposal*: discover never mutates the graph; output
  goes to a promotion queue for human review.
- Expand the fictional demo graph to launch scope (multiple communities, bridge
  ideas, low-confidence candidate edges) and commit generated demo analytics.

## v0.5: MCP Surface Hardening

- Complete and document the local MCP wrapper surface.
- Add MCP smoke tests that do not require private graph data.
- Revisit named competitor rows only after a fresh source-verification pass.

## v1: Public Demo And Local Graphs

- Keep the repo public-demo safe with fictional graph data only.
- Load private graphs through `MYGRAPH_PATH` or explicit CLI flags.
- Generate offline HTML viewers with embedded graph JSON.
- Keep provenance checks at zero violations.

## v1.5: Better Review Loops

- Improve candidate review ergonomics, including the discover promotion queue.
- Record clearer eval outcomes for accepted, rejected, and edited claims.
- Add repeatable privacy scans to the normal commit checklist.

## v2: Storage Evolution

- Move from JSON to SQL-backed persistence only when graph size or concurrency
  makes JSON awkward.
- Preserve the public node/edge schema and CLI behavior.

## v3: Productization

- Package the CLI for repeatable installation.
- Add import/export recipes for common note-taking and AI-export formats.
- Document deployment patterns that keep private graph data local by default.
