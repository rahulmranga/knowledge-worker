# Agent instructions — mygraph

This user maintains a personal knowledge graph called **mygraph**.
Before answering any question about Rahul, his ideas, projects, goals, decisions,
or open questions, **query the graph first**. Do not grep JSON files directly.

## Canonical query interface

Always use absolute paths. The `mq` shell alias only exists in interactive
shells — agentic tools spawning non-interactive subshells will NOT see it.

```bash
MYGRAPH="$HOME/Desktop/ideas/Midnight idea - Knowledge worker/mygraph"
python3 "$MYGRAPH/mygraph.py" query "<term>"
python3 "$MYGRAPH/mygraph.py" summary
python3 "$MYGRAPH/mygraph.py" path "<node_id>" "<node_id>"
```

Examples:
```bash
python3 "$HOME/Desktop/ideas/Midnight idea - Knowledge worker/mygraph/mygraph.py" query "land"
python3 "$HOME/Desktop/ideas/Midnight idea - Knowledge worker/mygraph/mygraph.py" query "h1b"
```

The CLI returns matching nodes with: type, id, label, body, confidence, edges,
and provenance (literal source excerpts). Use those as your grounded answer.

## Other commands

```bash
python "$MYGRAPH/mygraph.py" check --provenance      # integrity (must be 0)
python "$MYGRAPH/mygraph.py" ingest <file.md>        # add a new source
```

## Hard rules

1. Every claim about Rahul MUST cite a node id from `mq` output and the
   provenance excerpt it returned. No paraphrase, no inference beyond that.
2. If `mq <term>` returns nothing, say so plainly. Do NOT fabricate; do NOT
   fall back to the design docs (SPEC.md, V1_PLAN.md, V1_DESIGN.md) — those
   describe the system, not Rahul's beliefs.
3. Surface confidence labels (`high|medium|low`) when answering. `low` =
   inference; treat as such.
4. Multiple synonyms welcome — try a few queries (e.g. `query "land"`,
   `query "evaluation"`, `query "real estate"`) before concluding "not in graph".
5. If a topic isn't in the graph, the answer is "not yet ingested — run
   `python3 $MYGRAPH/mygraph.py ingest <path/to/file.md>` to add it." Don't
   hunt for the data elsewhere on disk; the graph is the single source of truth.

## Schema (for context, not for grep)

- **Node types:** person, topic, idea, project, goal, question, decision, reference, source
- **Edge types:** HAS_IDEA, RELATES_TO, SUPPORTED_BY, CHALLENGES, SERVES, INVOLVES, ABOUT, MENTIONED_IN, MADE_AT
- Every node has at least one `MENTIONED_IN` edge to a Source. That's the provenance spine.
