# Deep-Dive Interaction Model

`knowledge-worker` has one durable memory rule:

> The model proposes. Artifacts expose reasoning. Provenance verifies. Human
> review promotes.

This document defines the product language around the current ingest flow and
the `deep-dive` workflow added in v0.7.0.

## Current Memory Lifecycle

Today, durable memory enters the graph through ingest:

```text
source note
  -> candidates.json
  -> validate
  -> review
  -> merge accepted items into MYGRAPH_PATH
```

Candidates are proposals. Validation checks shape, IDs, allowed node/edge
types, endpoint references, and high-confidence excerpts. Review decides what
gets promoted. Merge writes only approved material to the active graph.

## Deep-Dive Lifecycle

`deep-dive` adds a reasoning workspace before ingest:

```text
source
  -> deep-dive workspace
  -> artifacts
  -> evidence validation
  -> refinement
  -> candidates.json
  -> validate
  -> review
  -> merge accepted items into MYGRAPH_PATH
```

In v0.7.0 the local generator creates conservative starter artifacts and
validated canonical candidates. Future LLM-backed generators can deepen the
workspace without changing the state model.

## User Intent Semantics

`generate`
: Create a workspace with artifacts, manifest, validation report, artifact
graph summary, and optional canonical candidates. This never mutates
`MYGRAPH_PATH`.

`inspect`
: Summarize the workspace: artifacts, source path, candidate counts, validation
status, weak spots, and next command.

`challenge this`
: Critique or refine the workspace. This is not rejection and not graph merge.
It means the reasoning surface needs another pass.

`add to graph`
: Start the validation/review/merge path. In v0.7.0 this is implemented as
`mykg deep-dive add-to-graph <workspace>`, which delegates to existing ingest.

`approve X`
: Promote only selected material where the review path supports selection.
Approval is a graph-memory action, not an artifact-generation action.

`don't ingest yet`
: Keep outputs artifact-local. The workspace can still be useful without
becoming durable graph memory.

## Workspace Contract

Every generated workspace includes:

- `manifest.json`: source path, artifact list, candidate path, validation
status, mutation flag, and next suggested command.
- `artifact-plan.json`: the source profile, chosen artifacts, and acceptance
criteria.
- Markdown artifacts: reviewable reasoning surfaces with source-local evidence
references.
- `validation-report.json`: canonical candidate validation summary when
candidates are generated.
- `artifact-graph.json`: artifact-local summary, not canonical graph memory.
- `*.candidates.json`: ingest-compatible proposals when candidates are enabled.

## Known Review Limitation

Current interactive ingest reviews candidate nodes directly. Eligible edges are
included after node approval when their endpoints are approved or already exist.
That keeps ingest short, but edges are reasoning claims and deserve better
review ergonomics. Improved edge review remains a roadmap item.

## Safe Mental Model

```text
Artifacts are thinking.
Candidates are proposals.
Validation is evidence discipline.
Review is promotion.
The graph is accepted memory.
```
