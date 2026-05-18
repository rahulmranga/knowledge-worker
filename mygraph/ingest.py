"""
ingest.py — orchestrates the 5-stage v1 pipeline.

  mykg ingest <path/to/file.md>
              [--non-interactive]
              [--auto-accept-high]
              [--auto-accept-all]
              [--candidates-file <path>]   # skip Stage 1 (extractor)
              [--keep-candidates]          # don't delete intermediate JSON
              [--backend claude|openai|ollama]  # extractor LLM (default claude)
              [--model <name>]             # v1.5: override model tag

Stage 1 (extractor) → candidates.json
Stage 2 (validator) → manifest + validated.json (in-memory)
Stage 3 (review CLI) → approved subset
Stage 4 (merge) → graph mutated, saved
Stage 5 (eval log) → review verdicts appended
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from .validator import validate
    from .review import review
    from .merge import merge
    from .eval_log import append as eval_append
except ImportError:  # direct script execution
    from validator import validate
    from review import review
    from merge import merge
    from eval_log import append as eval_append


def _load_extractor(backend: str):
    """Return the extract() callable for the chosen backend.
    backend ∈ {"claude", "openai", "ollama"}. Imported lazily so a missing dep
    on one side doesn't break the other."""
    if backend == "ollama":
        # ollama_proxy lives as a sibling to mygraph/
        import sys as _sys
        from pathlib import Path as _Path
        op = _Path(__file__).resolve().parent.parent / "ollama_proxy"
        if str(op) not in _sys.path:
            _sys.path.insert(0, str(op))
        from extractor_adapter import extract as _extract  # type: ignore
        return _extract
    if backend == "claude":
        try:
            from .extractor import extract as _extract
        except ImportError:
            from extractor import extract as _extract
        return _extract
    if backend == "openai":
        try:
            from .extractor_openai import extract as _extract
        except ImportError:
            from extractor_openai import extract as _extract
        return _extract
    raise ValueError(f"ingest: unknown --backend {backend!r} (valid: claude, openai, ollama)")


def run_ingest(args: list[str]) -> int:
    if not args:
        print("Usage: mykg ingest <file.md> [flags]")
        return 1
    md_path = Path(args[0]).expanduser().resolve()
    if not md_path.exists():
        print(f"ingest: file not found: {md_path}")
        return 1

    flags = set(args[1:])  # simple set membership; value-bearing flags handled below
    candidates_file = None
    if "--candidates-file" in args:
        i = args.index("--candidates-file")
        if i + 1 >= len(args):
            print("ingest: --candidates-file needs a path")
            return 1
        candidates_file = Path(args[i + 1]).expanduser().resolve()
    backend = "claude"
    if "--backend" in args:
        i = args.index("--backend")
        if i + 1 >= len(args):
            print("ingest: --backend needs a value (claude|openai|ollama)")
            return 1
        backend = args[i + 1]
    model = None
    if "--model" in args:
        i = args.index("--model")
        if i + 1 >= len(args):
            print("ingest: --model needs a value")
            return 1
        model = args[i + 1]
    non_interactive = "--non-interactive" in flags
    auto_high = "--auto-accept-high" in flags
    auto_all = "--auto-accept-all" in flags
    keep_candidates = "--keep-candidates" in flags

    if non_interactive and not (auto_high or auto_all):
        # Default headless behavior: be conservative — accept only `high`.
        auto_high = True

    # ---- Stage 1: Extract --------------------------------------------------
    if candidates_file:
        print(f"[1/5] using candidates from: {candidates_file}")
        payload = json.loads(candidates_file.read_text())
        candidates_path = candidates_file
    else:
        extract = _load_extractor(backend)
        print(f"[1/5] extract → backend={backend} on {md_path.name} ...")
        candidates_path = md_path.parent / f"{md_path.stem}.candidates.json"
        payload = extract(md_path, candidates_path, model=model) if model else extract(md_path, candidates_path)
        print(f"      wrote {candidates_path}")

    # ---- Stage 2: Validate -------------------------------------------------
    print("[2/5] validate ...")
    src_text = md_path.read_text()
    validated, manifest = validate(payload, src_text)
    print(manifest.summary())

    # log the manifest
    eval_append({"kind": "extract_manifest", "source_id": payload["source"]["id"],
                 "source_path": str(md_path),
                 "n_accepted_nodes": len(manifest.accepted_nodes),
                 "n_accepted_edges": len(manifest.accepted_edges),
                 "n_demoted_nodes": len(manifest.demoted_nodes),
                 "n_rejected_nodes": len(manifest.rejected_nodes),
                 "n_rejected_edges": len(manifest.rejected_edges),
                 "demotions": [{"id": n["id"], "reason": r} for n, r in manifest.demoted_nodes],
                 "rejections_n": [{"id": n.get("id", "?"), "reason": r} for n, r in manifest.rejected_nodes],
                 "rejections_e": [{"src": e.get("src", "?"), "dst": e.get("dst", "?"),
                                   "type": e.get("type", "?"), "reason": r}
                                  for e, r in manifest.rejected_edges]})

    # ---- Stage 3: Review --------------------------------------------------
    print("[3/5] review ...")
    approved = review(validated, src_text,
                      auto_accept_high=auto_high, auto_accept_all=auto_all)
    print(f"      approved: {len(approved['nodes'])} nodes, {len(approved['edges'])} edges")

    # ---- Stage 4: Merge ----------------------------------------------------
    print("[4/5] merge ...")
    n_added, e_added = merge(approved, interactive=not non_interactive)
    print(f"      +{n_added} nodes, +{e_added} edges")

    # ---- Stage 5: Eval log -------------------------------------------------
    eval_append({"kind": "ingest_complete", "source_id": approved["source"]["id"],
                 "source_path": str(md_path), "nodes_added": n_added,
                 "edges_added": e_added,
                 "candidates_file": str(candidates_path) if candidates_path else None,
                 "backend": backend, "model": model,
                 "non_interactive": non_interactive,
                 "auto_accept_high": auto_high, "auto_accept_all": auto_all})
    print("[5/5] eval log updated.")

    if not keep_candidates and candidates_path and candidates_file is None:
        # only auto-clean if WE wrote it
        try:
            candidates_path.unlink()
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(run_ingest(sys.argv[1:]))
