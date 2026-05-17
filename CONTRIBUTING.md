# Contributing to knowledge-worker

Thanks for looking. This is an early-stage personal tool that has been made public — contributions are welcome but the scope is intentionally narrow.

## What This Project Is

A local-first personal knowledge graph CLI. The core value is provenance-backed memory for AI workflows. Every node must cite a source. The graph stays simple and local.

## What Fits

- Bug fixes and edge-case handling in the core pipeline
- Improvements to the `ingest` / `check` / `viz` / `export_context` UX
- Additional export formats (JSON-LD, etc.) that don't add new required deps
- Better Ollama backend compatibility
- Documentation that explains a real workflow

## What Doesn't Fit (Right Now)

- Cloud sync or remote graph storage
- Multi-user or shared graph features
- A web UI or hosted service
- Vector database integration
- New node or edge types without a strong provenance argument

If you're not sure, open an issue first and describe the use case.

## How to Contribute

1. Fork the repo and create a branch: `git checkout -b your-feature`
2. Keep the core graph (`mygraph.py`) stdlib-only. New deps belong in `pyproject.toml` as optional extras.
3. Install locally: `python3 -m pip install -e .` (`python -m pip ...` is fine if `python` is Python 3.10+)
4. Run the smoke tests: `python3 -m unittest` (`python -m unittest` is fine if `python` is Python 3.10+)
5. Test with the demo graph: `MYGRAPH_PATH=examples/demo_graph.json mykg check --provenance`
6. Open a pull request with a clear description of what changed and why.

## Code Style

- Python 3.10+, type hints where they add clarity
- No external formatter required; keep diffs readable
- Comments on non-obvious decisions; silence on the obvious

## Issues

Bug reports and feature requests are welcome. Use a short title and enough context to reproduce or understand the request. "This broke" with no detail will be closed.

## License

By contributing, you agree your contributions are licensed under the project's MIT license.
