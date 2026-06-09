# Benchmarks

`knowledge-worker` benchmarks are public-demo-safe checks that run entirely
against `examples/demo_graph.json`. They do not need an API key, private graph,
network access, or generated artifact committed to the repo.

Run the benchmark suite:

```bash
python3 -m unittest tests/test_benchmarks.py
```

Run the smoke and benchmark suites together:

```bash
python3 -m unittest tests/test_cli_smoke.py tests/test_benchmarks.py
```

## Benchmark Summary

| ID | Name | What it protects | Threshold |
|---|---|---|---|
| B1 | Provenance check | Required provenance remains a hard invariant | `check --provenance` exits 0 with 0 violations |
| B2 | Audit coverage | Audit reports complete source and excerpt coverage | `node_coverage`, `edge_source_coverage`, and `excerpt_coverage` are all `1.0` |
| B3 | Query recall with excerpts | Query output includes a relevant node and cited source excerpt | `query provenance` returns `idea:provenance-first` and the provenance excerpt |
| B4 | Path finding | The demo graph supports relationship traversal | Owner-to-goal path includes at least one intermediate node |
| B5 | Weak-claim queue | Audit surfaces review burden instead of hiding uncertainty | `weak_claims` and `weak_claim_queue` are populated lists |
| B6 | Directed audit shape | Directed idea-flow output stays present and useful | `idea_generators` is populated; `idea_attractors` is present as a list |
| B7 | Context compactness | LLM context export stays paste-sized | `context --max-ideas 5` emits fewer than 3000 characters |
| B8 | Privacy boundary | Public fixture stays sanitized and private graph path remains ignored | Demo nodes/edges use public schema; no email or absolute home paths; default private graph is not tracked |
| B9 | Negative query | Missing topics are reported plainly | Absent query prints `No nodes match ...` and does not return false positives |
| B10 | Launch fixture | Public demo keeps its promised composition and useful audit topology | Exact type counts, two measurable bridge ideas, and at least three low-confidence candidate edges |

## Manual Commands

### B1: Provenance Check

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 -m mygraph.mygraph check --provenance
```

Pass criteria:

- exit code `0`
- stdout contains `provenance violations: 0`

### B2: Audit Coverage

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 -m mygraph.mygraph audit --out /tmp/knowledge-worker-audit.json
```

Pass criteria:

- `provenance_coverage.node_coverage == 1.0`
- `provenance_coverage.edge_source_coverage == 1.0`
- `provenance_coverage.excerpt_coverage == 1.0`

### B3: Query Recall With Excerpts

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 -m mygraph.mygraph query provenance
```

Pass criteria:

- stdout contains `idea:provenance-first`
- stdout contains the source excerpt `Every durable claim needs source evidence.`

### B4: Path Finding

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 -m mygraph.mygraph path person:demo-owner goal:trusted-ai-assistance
```

Pass criteria:

- stdout starts with a path, not `No path`
- output includes `person:demo-owner` and `goal:trusted-ai-assistance`
- output includes at least one intermediate node

### B5: Weak-Claim Queue

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 -m mygraph.mygraph audit --out /tmp/knowledge-worker-audit.json
```

Pass criteria:

- `ranked.weak_claims` is a non-empty list
- `ranked.weak_claim_queue` is a non-empty list
- at least one weak claim references the medium-confidence demo reference node

### B6: Directed Audit Shape

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 -m mygraph.mygraph audit --out /tmp/knowledge-worker-audit.json
```

Pass criteria:

- `ranked.idea_generators` is a non-empty list
- `ranked.idea_attractors` exists and is a list
- `directed_flow` includes both `idea_generators` and `idea_attractors`

The current demo graph has a real generator and no qualifying attractor. That is
acceptable: the benchmark protects the output shape and the populated side of
the minimal fixture rather than forcing synthetic graph data.

### B7: Context Compactness

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 -m mygraph.mygraph context --max-ideas 5
```

Pass criteria:

- stdout is fewer than `3000` characters
- stdout contains the expected context headings

### B8: Privacy Boundary

This is a static fixture check in `tests/test_benchmarks.py`.

Pass criteria:

- every demo node type is listed in `SPEC.md`
- every demo edge type is listed in `SPEC.md`
- demo graph strings do not contain emails or absolute home-directory paths
- `mygraph/mygraph.json` remains ignored and untracked; developers may still
  have a local ignored private graph at that path

### B9: Negative Query

```bash
MYGRAPH_PATH=examples/demo_graph.json python3 -m mygraph.mygraph query unlikely-absent-benchmark-token
```

Pass criteria:

- stdout contains `No nodes match 'unlikely-absent-benchmark-token'.`
- stdout does not contain a normal match section

### B10: Launch Fixture

This is a static fixture and analytics check in `tests/test_benchmarks.py`.

Pass criteria:

- exactly 3 projects, 4 goals, 8 decisions, 12 ideas, 6 sources, and 5 references
- `idea:audited-context-bridge` and `idea:evidence-governance-bridge` have positive betweenness
- at least three low-confidence candidate edges feed the weak-claim queue

## Interpreting Failures

- A provenance failure means the public demo graph no longer satisfies the core
  invariant and should be fixed before release.
- A compactness failure means the default context export may be drifting toward
  a full dump instead of an LLM-ready snapshot.
- A privacy failure means the public fixture may contain local or personal data,
  or the ignored default private graph path may have become tracked.
- A benchmark should not depend on local private graphs, API keys, model output,
  or generated audit files checked into git.
