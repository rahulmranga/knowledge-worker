# Changelog

## 0.7.0

- Added `mykg deep-dive`, a pre-ingest workspace flow for generating adaptive
  artifacts, validation reports, an artifact-local graph summary, and canonical
  ingest candidates without mutating `MYGRAPH_PATH`.
- Added `mykg deep-dive inspect <workspace>` for reviewing generated artifacts,
  candidate counts, validation status, and the next suggested command.
- Added `mykg deep-dive add-to-graph <workspace>` as a convenience wrapper over
  the existing `ingest --candidates-file` validation/review/merge path.
- Added the Deep-Dive Interaction Model documentation, defining generate,
  inspect, challenge, add-to-graph, approve, and don't-ingest-yet semantics.
- Expanded README workflow docs to explain how candidates become durable graph
  memory and where deep-dive fits before ingest.
- Updated the public roadmap to make v0.7.0 the interaction-model and
  deep-dive workspace release, with memory analyzer work tracked next.

## 0.6.x

- Added memory audit, context export, and discovery-layer workflows over the
  public demo graph.
- Kept audit and discover read-only: they rank, explain, and propose, but never
  mutate graph memory directly.
