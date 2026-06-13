# knowledge-worker Design

## Pipeline

```text
Markdown source
  -> extractor proposes nodes and edges
  -> validator checks shape, IDs, excerpts, and orphan edges
  -> reviewer accepts, rejects, or edits candidates
  -> merger writes canonical JSON
  -> eval log records review and health-check outcomes
```

## Provenance

The graph treats source material as evidence. A claim that cannot be tied to a
source should remain low-confidence or stay out of the graph.

High-confidence extraction requires a literal excerpt. The validator demotes
claims when the excerpt is missing or not present in the source text.

## Storage And Paths

`mygraph/mygraph.json` is the default local graph and is ignored by git. The
same CLI can target a private graph outside the repository:

```bash
MYGRAPH_PATH=/absolute/path/to/private/mygraph.json python3 mygraph/mygraph.py query "architecture"
```

Export and visualization also accept explicit output paths:

```bash
python3 mygraph/mygraph.py export --ttl --out examples/demo_graph.ttl
python3 mygraph/mygraph.py viz --graph examples/demo_graph.json --out examples/demo_graph.html --no-open
```

## Visualization

The v1 viewer is a single HTML file with embedded graph JSON and plain
JavaScript. It does not fetch D3, read a sibling JSON file, or upload graph data.

Expected interactions:

- Pan and zoom the graph.
- Click a node to inspect label, body, confidence, provenance, and neighbors.
- Open public demo HTML directly from disk.

## Eval Direction

The current eval loop is deterministic first: provenance checks, stale-edge
checks, and review records. LLM-backed probes are optional and require an API
key. Eval records are local-only and ignored by git.

## Non-Goals

- No cloud sync.
- No automatic publication of private graph data.
- No vector database in v1.
- No RL or fine-tuning in v1.
