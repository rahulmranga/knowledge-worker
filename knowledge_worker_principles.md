# knowledge-worker Principles

## 1. Provenance First

Durable memory needs evidence. The graph stores sources and excerpts so future
AI sessions can distinguish grounded claims from guesses.

## 2. Local First

Private graphs should live outside the public repo and be addressed by absolute
path. Generated local artifacts stay ignored unless they are explicitly
sanitized examples.

## 3. Boring Persistence

Use simple JSON until it becomes the limiting factor. Add SQL-backed storage only
when operational needs justify it, and keep the graph schema stable across
storage backends.

Use append-only JSONL for history and replay before introducing a database.
Export JSON-LD/RDF for open-web interoperability without making the local source
of truth depend on a hosted service.

## 4. Review Before Merge

LLMs can propose structure, but deterministic validation and human review decide
what becomes durable memory.

## 5. Evals As Gates

Health checks and review records should become merge gates for graph quality:
provenance violations are failures, not cosmetic warnings.
