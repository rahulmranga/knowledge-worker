# Changelog

## 0.8.4

- Removed the author name and email from the package metadata.
- Fixed script injection in the `mykg audit` and `mykg viz` HTML pages: graph
  text could close the script block with a differently cased `</SCRIPT`. Every
  `<` in the embedded JSON is now written as `\u003c`.
- Fixed a blank `mykg audit` page when graph text contained a template
  placeholder such as `__GRAPH_JSON__`.
- Enforced edge provenance in automatic ingestion (#7).

## 0.8.3

- Rewrote the PyPI description and expanded the keyword list so the project is
  discoverable as knowledge-graph memory for LLMs and AI agents.
- Moved the development status to Beta and added Information Technology,
  End Users, English, Python Modules, and Utilities classifiers.
- Added Documentation and Changelog project URLs and corrected the author email.

## 0.8.2

- Removed the ecosystem cross-link header so the README opens on the project
  heading.
- Added a chat-context comparison image and a process-flow diagram, and moved
  the graph visualizer demo down to "What It Does".
- Pointed README images at absolute raw URLs so they render on the PyPI project
  page as well as on GitHub.

## 0.8.1

- Reworked the README: moved "What It Does" and "How Memory Enters The Graph"
  after Quick Start, documented the app-session (no API key) candidates flow,
  and simplified the install commands.
- Added `llm.txt`, an llms.txt-style summary of the project principles and
  entry points for AI assistants.

## 0.8.0

- Accepted the v0.8.0 storage direction: JSON-LD becomes canonical, JSONL
  remains the append-only history layer, Turtle/RDF is the interchange path,
  Kuzu is deferred as an optional future read/query backend, and graphify.net is
  treated as a future publishing/interchange target.
- Made `mykg export` default to canonical JSON-LD and kept `mykg export
  --jsonld` as the explicit form.
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
