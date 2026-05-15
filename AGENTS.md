# Agent Instructions — knowledge-worker

This repo is a public-demo-safe graph toolkit. Treat private graph data as
external input, not as repo content.

## Querying Graphs

Use the CLI instead of grepping graph JSON:

```bash
MYGRAPH_PATH=/absolute/path/to/private/mygraph.json python3 mygraph/mygraph.py query "<term>"
MYGRAPH_PATH=/absolute/path/to/private/mygraph.json python3 mygraph/mygraph.py summary
MYGRAPH_PATH=/absolute/path/to/private/mygraph.json python3 mygraph/mygraph.py path "<node_id>" "<node_id>"
```

For the public demo:

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 mygraph/mygraph.py query "provenance"
```

## Safety Rules

1. Do not commit raw exports, private graph JSON, private TTL, generated private
   viewers, eval logs, state logs, or `.env` files.
2. Prefer `MYGRAPH_PATH` or `--graph` for private graph work.
3. When answering from a private graph, cite node IDs and provenance excerpts
   returned by the CLI.
4. If the graph has no match for a topic, say so plainly.
5. Run privacy and provenance checks before committing public-demo changes.
