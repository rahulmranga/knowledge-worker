"""
eval_log.py — JSONL appender for eval_record.jsonl.

Every review action, provenance violation, stale-edge flag, relational probe,
and source-candidate suggestion writes one line here. This is the v1 corpus that
v2+ will use for prompt refinement / edge weighting / RL.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
EVAL_LOG = HERE / "eval_record.jsonl"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append(record: dict, path: Path = EVAL_LOG) -> None:
    record.setdefault("ts", now())
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_many(records: list[dict], path: Path = EVAL_LOG) -> None:
    if not records:
        return
    ts = now()
    with path.open("a") as f:
        for r in records:
            r.setdefault("ts", ts)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
