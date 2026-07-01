# Changelog

## 0.8.0

- Accepted the v0.8.0 storage direction: JSON remains canonical, JSONL becomes
  the append-only history layer, JSON-LD/RDF are the open-web interchange path,
  Kuzu is deferred as an optional future read/query backend, and graphify.net is
  treated as a future publishing/interchange target.
- Added `mykg export --jsonld` as a JSON-LD/RDF sibling to the existing
  Turtle/RDF export.
- Updated the public roadmap, specification, design notes, principles, and
  README to make the open-web storage contract explicit.

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
- Added broader CLI regression coverage for help/error paths and the existing
  query, list, path, check, export, context, viz, audit, discover, ingest, and
  deep-dive command surfaces.
- Added GitHub Actions CI for pull requests and main-branch pushes across
  Python 3.10, 3.11, 3.12, and 3.13, including the unittest suite and demo
  graph provenance check.

## 0.6.x

- Added memory audit, context export, and discovery-layer workflows over the
  public demo graph.
- Kept audit and discover read-only: they rank, explain, and propose, but never
  mutate graph memory directly.
