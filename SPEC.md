# knowledge-worker Specification

## Goal

Build a local-first knowledge graph that stores durable context for AI-assisted
work without committing private data to git. The graph should answer “what do we
know about this concept?” with nearby nodes and source-backed provenance.

## Graph Model

Node types:

| Type | Meaning |
|---|---|
| `person` | A graph owner, collaborator, or public figure referenced by sources. |
| `topic` | A domain, theme, or technical area. |
| `idea` | A reusable thesis, principle, or design thought. |
| `project` | A thing being built or evaluated. |
| `goal` | A desired outcome. |
| `question` | An open decision or uncertainty. |
| `decision` | A resolved choice with source evidence. |
| `reference` | A paper, article, tool, or outside source. |
| `source` | A document, note, or conversation export used as evidence. |

Edge types:

`HAS_IDEA`, `RELATES_TO`, `SUPPORTED_BY`, `CHALLENGES`, `SERVES`, `INVOLVES`,
`ABOUT`, `MENTIONED_IN`, `MADE_AT`.

## Invariants

- Every non-source node has at least one `MENTIONED_IN` edge to a source.
- Every edge has a `source_id`.
- High-confidence claims must have literal excerpts where available.
- Private graph data is loaded by path, not committed.
- JSON is canonical; Turtle and HTML are generated artifacts.

## Storage

The default graph path is `mygraph/mygraph.json`, which is ignored by git.
Override it with:

```bash
MYGRAPH_PATH=/absolute/path/to/mygraph.json python3 mygraph/mygraph.py summary
```

This keeps public demo data and private graph data cleanly separated.

## CLI Surface

```bash
python3 mygraph/mygraph.py seed
python3 mygraph/mygraph.py summary
python3 mygraph/mygraph.py query <term>
python3 mygraph/mygraph.py list <type>
python3 mygraph/mygraph.py path <node_id> <node_id>
python3 mygraph/mygraph.py state "<entry>"
python3 mygraph/mygraph.py dump
python3 mygraph/mygraph.py reset
python3 mygraph/mygraph.py ingest <file.md>
python3 mygraph/mygraph.py check --provenance
python3 mygraph/mygraph.py export --ttl --out <file.ttl>
python3 mygraph/mygraph.py context --out <file.md>
python3 mygraph/mygraph.py viz --graph <file.json> --out <file.html> --no-open
python3 mygraph/mygraph.py audit --graph <file.json> --out <analytics.json>
python3 mygraph/mygraph.py discover --graph <file.json> --out <discovery.json> --candidates <candidates.json>
```

## Public Demo

The repository includes a fictional graph in `examples/demo_graph.json`. It
exercises provenance, decisions, goals, references, and questions without
exposing private source material.

## Safety Boundary

The repo should contain source code, docs, and sanitized examples only. Raw
exports, private graph files, eval records, state logs, local viewers, and
environment files are ignored by default.
