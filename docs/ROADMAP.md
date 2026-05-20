# Public Roadmap

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
