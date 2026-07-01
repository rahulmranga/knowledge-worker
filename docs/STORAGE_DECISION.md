# Storage Decision: JSON, JSONL, JSON-LD, Kuzu, And graphify.net

Status: accepted for v0.8.0.

## Decision

`knowledge-worker` keeps plain JSON as the canonical local graph store for
v0.8.0. The project uses append-only JSONL records for events, review history,
evals, and replayable provenance logs, while treating JSON-LD/RDF as the
open-web interchange layer.

Kuzu is a future optional read/query backend, not the source of truth. graphify.net
is a future publishing or interchange experiment, not the local storage layer.

## Why

The project is local-first and provenance-first. The storage layer should make
private graphs easy to inspect, diff, back up, and keep out of the public repo.
Plain JSON already serves that contract. Replacing it before scale or
concurrency requires it would add operational weight without improving the core
promise: durable claims with source excerpts and human review before merge.

The open-web direction is still important. JSON-LD lets the same graph model
participate in RDF, linked data, provenance, and W3C-style interoperability
without making every local user run a database or hosted service.

## Storage Roles

| Layer | Role | v0.8.0 stance |
|---|---|---|
| JSON | Canonical local graph: nodes, edges, source-backed claims | Keep as source of truth |
| JSONL | Append-only event stream: reviews, evals, analyzer runs, replay logs | Add and document as history/log layer |
| JSON-LD/RDF | Open-web export for linked data and interoperable agents | Promote as the semantic web bridge |
| Kuzu | Fast graph queries and larger local analytical workloads | Defer to optional v2 read model |
| graphify.net | Publishing, visualization, interchange, or federation surface | Explore after JSON-LD export is stable |

## Release Implications

v0.8.0 ships the open-web storage contract:

- JSON remains the canonical graph format.
- JSONL records capture reviewable history and eval traces.
- RDF/Turtle export remains supported.
- JSON-LD export is supported as the preferred open-web JSON export target.
- Kuzu and graphify.net are documented as future adapters, not required
  dependencies.

## Release Gates

Before a v0.8.0 release, run:

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 -m mygraph.mygraph check --provenance
python3 -m unittest
MYGRAPH_PATH=examples/demo_graph.json python3 -m mygraph.mygraph export --jsonld --out /tmp/demo_graph.jsonld
python3 -m json.tool /tmp/demo_graph.jsonld >/dev/null
python3 -m pip wheel . -w /tmp/knowledge-worker-wheel-test
git status --short
```

The release should not include private graph JSON, private TTL/JSON-LD exports,
generated private viewers, eval logs, state logs, or `.env` files.
