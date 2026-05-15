# knowledge-worker v1 Plan

## North Star

Make a local graph useful enough that AI sessions can recover project context
from structured, source-backed memory instead of from loose chat history.

## Milestones

1. Public-demo hygiene
   - Keep private graph data out of git.
   - Ship fictional examples only.
   - Add repeatable privacy checks before commit.

2. Provenance pipeline
   - Extract candidate graph facts from markdown.
   - Validate excerpts and IDs deterministically.
   - Require human review before merge.
   - Log review actions as eval records.

3. Offline graph viewing
   - Generate a single HTML file with embedded graph data.
   - Avoid network/CDN dependencies.
   - Show node details, confidence, neighbors, and provenance.

4. Export and interoperability
   - Keep JSON canonical.
   - Export Turtle/RDF from any graph path.
   - Maintain round-trip checks for generated TTL.

5. Future persistence
   - Add SQL-backed storage only after the JSON graph becomes painful.
   - Preserve the same node and edge schema at the API boundary.

## Success Criteria

- `check --provenance` returns zero violations on the demo graph.
- Private graph files can be queried through `MYGRAPH_PATH`.
- The generated demo viewer opens locally without external network access.
- A denylist scan of tracked files finds no private demo-owner data.
