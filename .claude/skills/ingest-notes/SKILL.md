---
name: ingest-notes
description: Extract knowledge-graph candidates from a markdown notes file without an API key, then merge them into the local graph. Use when the user wants to ingest notes into knowledge-worker, build candidates.json, or add notes to their mygraph without calling an LLM backend.
---

# ingest-notes

Turn a markdown notes file into reviewable `knowledge-worker` graph candidates,
then hand off to the deterministic local pipeline for validation, review, and
merge. This replaces the paid API-backed `mykg ingest` extractor step: **you**
act as the extractor, so no `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` is needed.

## Inputs

- A path to a markdown notes file, e.g. `path/to/notes.md`. If the user did not
  name one, ask which file to ingest.

## Steps

1. **Read the source.** Read the target notes markdown file in full. Read the
   `EXTRACTION_TOOL` input schema and `PROMPT_TEMPLATE` in
   `mygraph/extractor.py` so the output matches the contract exactly.

2. **Write `<notes>.candidates.json`** (same directory and basename as the
   notes file, with a `.candidates.json` suffix). It MUST be a single JSON
   object with three top-level keys — `source`, `nodes`, `edges`:

   - `source` (object, all three fields **required** — the validator hard-rejects
     the file otherwise):
     - `id`: string that **must start with `source:`**, e.g.
       `source:my-notes` (lowercase, hyphenated slug of the filename).
     - `label`: human label, typically the filename.
     - `body`: a short description of the source.
   - `nodes` (array). Each node requires `id`, `type`, `label`, `confidence`;
     `excerpt` is required in practice for any durable claim (see rules below).
     - `id`: type-prefixed slug, e.g. `idea:context-memory`,
       `decision:use-json`.
     - `type`: one of `person`, `topic`, `idea`, `project`, `goal`,
       `question`, `decision`, `reference`, `source`.
     - `confidence`: `high`, `medium`, or `low`.
     - `excerpt`: a **literal substring** of the source markdown.
   - `edges` (array). Each edge requires `src`, `dst`, `type`, `confidence`;
     include `excerpt`.
     - `type`: one of `HAS_IDEA`, `RELATES_TO`, `SUPPORTED_BY`, `CHALLENGES`,
       `SERVES`, `INVOLVES`, `ABOUT`, `MENTIONED_IN`, `MADE_AT`.

3. **Follow the extraction rules** (from `PROMPT_TEMPLATE`):
   - Cite a **literal excerpt** from the source for every node and edge — no
     paraphrase in the `excerpt` field.
   - Use `confidence: "high"` only with a direct quote in `excerpt`. A
     `high`-confidence node whose excerpt is **not** a literal substring of the
     source gets demoted by the validator, so quote exactly.
   - Use `medium` for clear paraphrase, `low` for inference.
   - **Do not invent biographical or personal facts.** If the source doesn't
     say it, it does not go in.
   - Every **new concept node** must have a `MENTIONED_IN` edge to the
     `source` node.
   - Reuse existing graph IDs when a candidate refers to an existing concept
     (run `mykg dump` or `mykg list <type>` to see current IDs).

4. **Merge via the local pipeline.** Hand the file to the deterministic CLI,
   which validates provenance, runs review, and merges:

   ```bash
   mykg ingest path/to/notes.md --candidates-file path/to/notes.candidates.json
   ```

   If `mykg` is not installed, run from a clone with
   `python3 mygraph/mygraph.py ingest ...`. To target a specific graph, prefix
   with `MYGRAPH_PATH=/path/to/mygraph.json`.

## Notes

- Validation, review, and merge stay local — this skill only produces the
  candidates file; it never mutates the graph directly.
- Candidate files are gitignored by default; keep private notes out of the repo.
