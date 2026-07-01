# Storage Decision: JSON-LD, JSONL, Kuzu, And graphify.net

Status: accepted for v0.8.0.

## Decision

`knowledge-worker` uses JSON-LD as the canonical local graph store for v0.8.0.
The project uses append-only JSONL records for events, review history, evals,
and replayable provenance logs, while treating Turtle/RDF as the generated
semantic-web interchange layer.

Kuzu is a future optional read/query backend, not the source of truth. graphify.net
is a future publishing or interchange experiment, not the local storage layer.

## Why

The project is local-first, provenance-first, and open-web-oriented. The storage
layer should make private graphs easy to inspect, diff, back up, and keep out of
the public repo while also carrying web-native meaning. Compact JSON-LD serves
that contract: it is still a readable JSON document, but it includes context and
schema metadata so the graph can participate in RDF, linked data, provenance,
and W3C-style interoperability without making every local user run a database or
hosted service.

## Storage Roles

| Layer | Role | v0.8.0 stance |
|---|---|---|
| JSON-LD | Canonical local graph: nodes, edges, context, schema version, source-backed claims | Keep as source of truth |
| JSONL | Append-only event stream: reviews, evals, analyzer runs, replay logs | Keep as history/log layer |
| Turtle/RDF | Generated semantic-web export for linked data and interoperable agents | Keep as interchange artifact |
| JSON | Legacy graph files | Keep readable for migration |
| Kuzu | Fast graph queries and larger local analytical workloads | Defer to optional v2 read model |
| graphify.net | Publishing, visualization, interchange, or federation surface | Explore after JSON-LD export is stable |

## Release Implications

v0.8.0 ships the open-web storage contract:

- JSON-LD remains the canonical graph format.
- JSONL records capture reviewable history and eval traces.
- RDF/Turtle export remains supported.
- Legacy JSON graph files remain readable.
- Kuzu and graphify.net are documented as future adapters, not required
  dependencies.

## Release Gates

Before a v0.8.0 release, run:

```bash
MYGRAPH_PATH=examples/demo_graph.jsonld python3 -m mygraph.mygraph check --provenance
python3 -m unittest
MYGRAPH_PATH=examples/demo_graph.jsonld python3 -m mygraph.mygraph export --out /tmp/demo_graph.jsonld
python3 -m json.tool /tmp/demo_graph.jsonld >/dev/null
python3 -m pip wheel . -w /tmp/knowledge-worker-wheel-test
git status --short
```

The release should not include private graph JSON-LD, legacy private graph JSON,
private TTL/JSON-LD exports, generated private viewers, eval logs, state logs,
or `.env` files.
