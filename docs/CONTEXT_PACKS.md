# Context Packs

Context packs are scoped, source-backed memory handoffs for AI work.

The normal `context` command prints a compact snapshot of the graph. A context
pack is narrower: it is generated for a specific task, query, collaborator, or
AI assistant, and it carries only the reviewed slice needed for that job.

## Why They Matter

Most AI workflows have two bad defaults:

- paste too little context and force the assistant to guess
- paste too much context and leak irrelevant private information

`knowledge-worker` should make the middle path explicit: export a cited slice,
review it, and then hand that bounded context to another tool.

## Pack Contract

A context pack should say:

- what task it supports
- what query, node, or path produced the slice
- which nodes and edges are included
- which source excerpts support the claims
- which confidence labels apply
- what was intentionally excluded

The important distinction is governance. A context pack is not just search
results. It is a reviewed memory boundary.

## Example Shape

```text
# Context Pack: Product Positioning

Purpose:
Help an AI assistant draft public-safe positioning copy.

Scope:
Query: "provenance memory"
Hops: 1
Minimum confidence: medium

Included Concepts:
- idea:provenance-first
  Confidence: high
  Source: source:demo-note
  Excerpt: "Every durable claim needs source evidence."

Excluded:
- raw chat transcripts
- private graph files
- unrelated person nodes
- low-confidence claims not needed for this task
```

## Public-Safe Direction

Initial support can build on the existing graph operations:

- query or start-node selection
- one-hop or two-hop expansion
- confidence filtering
- provenance excerpt inclusion
- Markdown and JSON output
- generated files under ignored export directories

Future support can add redaction rules, explicit review status, and task-specific
templates for PRDs, research briefs, decision memos, and AI assistant handoffs.
