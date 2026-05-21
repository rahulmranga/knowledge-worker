# Public Roadmap

## v0.3: Directed Memory Audit And Benchmarks

- Add directed idea-flow panels that separate idea attractors from idea
  generators.
- Turn weak claims into a user-reviewed queue: verify, downgrade, convert to a
  question, or ignore for now.
- Keep the audit read-only and prompt-driven so the user does the judgment work.
- Publish `docs/COMPETITIVE_ANALYSIS.md` with a source-checked category matrix.
- Publish `docs/BENCHMARKS.md` with offline demo-graph benchmarks.
- Add `tests/test_benchmarks.py` so benchmark checks run with no API key.
- Add README positioning that points readers to the analysis and benchmarks.
- Keep the MCP comparison honest while `ollama_proxy/server.py` remains
  experimental.

## v0.4: MCP Surface Hardening

- Complete and document the local MCP wrapper surface.
- Add MCP smoke tests that do not require private graph data.
- Revisit named competitor rows only after a fresh source-verification pass.

## v1: Public Demo And Local Graphs

- Keep the repo public-demo safe with fictional graph data only.
- Load private graphs through `MYGRAPH_PATH` or explicit CLI flags.
- Generate offline HTML viewers with embedded graph JSON.
- Keep provenance checks at zero violations.

## v1.5: Better Review Loops

- Improve candidate review ergonomics.
- Record clearer eval outcomes for accepted, rejected, and edited claims.
- Add repeatable privacy scans to the normal commit checklist.

## v1.5: Memory Audit

- Emit `analytics.json` with PageRank, betweenness, k-core, communities,
  low-confidence edges, and provenance coverage.
- Add a Memory Audit HTML view with ranked panels before the graph canvas:
  important concepts, bridge ideas, weak claims, and proof trail.
- Keep audit output read-only and generated from explicit graph paths so private
  graph data stays outside the public repo.

## v2: Storage Evolution

- Move from JSON to SQL-backed persistence only when graph size or concurrency
  makes JSON awkward.
- Preserve the public node/edge schema and CLI behavior.

## v3: Productization

- Package the CLI for repeatable installation.
- Add import/export recipes for common note-taking and AI-export formats.
- Document deployment patterns that keep private graph data local by default.
