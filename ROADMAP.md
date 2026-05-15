# Project Roadmap

This document describes the planned phases and milestones for the `knowledge-worker` project.

The long-term goal is not simply chat continuity.

It is:

> persistent personalized reasoning continuity

---

# Phase A — Make the memory loop real

## Goals
Create a reliable ingestion and persistence loop.

## Milestones

### Automated ingestion
- ingest ChatGPT exports
- ingest Claude exports
- ingest notes/journals/documents
- ingest candidate graph deltas

### Reliable persistence
- explicit graph backups before merge
- append-only provenance log
- review queue before mutation
- avoid silent graph mutation

### Sync infrastructure
- fix Mac mini ↔ OneDrive reliability
- support local-first persistence
- preserve offline operation

### Candidate extraction
- nightly extraction jobs
- candidate edge generation
- manual review before merge

---

# Phase B — Make it useful

## Goals
Improve retrieval quality and measurable usefulness.

## Milestones

### Context retrieval
- prompt-time graph retrieval
- select only relevant nodes/edges
- explain why context was selected

### Evaluation harness
Compare:
- no graph
- graph-assisted
- graph + retrieval scoring

Metrics:
- correctness
- continuity
- hallucination reduction
- personalization quality

### Query tooling
- graph inspection UI
- reasoning-path visualization
- provenance inspection

---

# Phase C — Make it defensible

## Goals
Handle ambiguity, contradictions, and time.

## Milestones

### Contradiction detection
- conflicting edge detection
- source disagreement tracking
- manual conflict resolution workflow

### Temporal reasoning
- timestamps on beliefs/facts
- stale edge detection
- historical snapshots

### Confidence systems
- confidence decay
- source weighting
- provenance ranking
- freshness scoring

---

# Future Directions

## Federated local compute
- local Gemma integration
- hybrid local/cloud reasoning
- model portability

## Multi-model orchestration
Different models for:
- extraction
- synthesis
- critique
- verification

## Long-term vision

A portable cognitive substrate that:
- survives across AI vendors
- preserves reasoning continuity
- maintains provenance
- evolves with the user over time