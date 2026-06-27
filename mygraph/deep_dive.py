"""
deep_dive.py - pre-ingest reasoning workspace generator.

`mykg ingest` turns a source into reviewed graph memory. `mykg deep-dive`
adds a workbench before that step: generate reviewable artifacts, validate
canonical candidates, inspect the workspace, then optionally route the
candidates through the existing ingest review/merge path.

The v0.7.0 generator is intentionally conservative and stdlib-only. It creates
adaptive starter artifacts and ingest-compatible candidates without mutating the
graph. Richer LLM-backed artifact generation can replace the planner/generator
later without changing the workspace contract.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .extractor import build_source_decl, ensure_provenance_edges
    from .ingest import run_ingest
    from .mygraph import slug
    from .validator import validate
except ImportError:  # direct script execution
    from extractor import build_source_decl, ensure_provenance_edges
    from ingest import run_ingest
    from mygraph import slug
    from validator import validate


SCHEMA_VERSION = "deep-dive/v1"
DEFAULT_ITERATIONS = 2


@dataclass
class SourceLine:
    number: int
    text: str


def _usage() -> str:
    return """\
Usage:
  mykg deep-dive <source.md> --out-dir <workspace>
                   [--iterations N] [--no-candidates]
  mykg deep-dive inspect <workspace>
  mykg deep-dive add-to-graph <workspace>
                   [--non-interactive] [--auto-accept-high|--auto-accept-all]

Deep-dive creates a pre-ingest workspace. Generation never mutates MYGRAPH_PATH.
add-to-graph delegates to the existing ingest validation/review/merge pipeline.
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_lines(source: Path) -> list[SourceLine]:
    return [
        SourceLine(i + 1, line.rstrip("\n"))
        for i, line in enumerate(source.read_text(encoding="utf-8").splitlines())
    ]


def _nonempty(lines: list[SourceLine]) -> list[SourceLine]:
    return [line for line in lines if line.text.strip()]


def _heading(lines: list[SourceLine]) -> SourceLine | None:
    for line in lines:
        stripped = line.text.strip()
        if stripped.startswith("#"):
            label = stripped.lstrip("#").strip()
            if label:
                return SourceLine(line.number, label)
    return None


def _first_sentence(line: str) -> str:
    clean = re.sub(r"\s+", " ", line).strip()
    if not clean:
        return ""
    match = re.search(r"(?<=[.!?])\s+", clean)
    if match:
        clean = clean[:match.start()].strip()
    return clean[:280]


def _choose_excerpt(lines: list[SourceLine], patterns: list[str] | None = None) -> SourceLine:
    candidates = _nonempty(lines)
    if patterns:
        lowered = [(p, p.lower()) for p in patterns]
        for line in candidates:
            text = line.text.lower()
            if any(pattern in text for _, pattern in lowered):
                return SourceLine(line.number, _first_sentence(line.text))
    if candidates:
        return SourceLine(candidates[0].number, _first_sentence(candidates[0].text))
    return SourceLine(1, "")


def _classify_source(source: Path, lines: list[SourceLine]) -> dict[str, Any]:
    text = "\n".join(line.text for line in lines).lower()
    signals = {
        "technical_design": [
            "architecture", "implementation", "api", "schema", "deploy",
            "pipeline", "database", "latency", "server", "cli",
        ],
        "decision_analysis": [
            "decision", "tradeoff", "option", "alternative", "approve",
            "reject", "criteria", "priority",
        ],
        "incident_or_debug": [
            "bug", "error", "incident", "outage", "debug", "failure",
            "regression", "broken",
        ],
        "research_synthesis": [
            "paper", "research", "study", "evidence", "citation",
            "source", "literature",
        ],
        "planning": [
            "roadmap", "plan", "milestone", "next steps", "release",
            "scope", "timeline",
        ],
        "conversation_synthesis": [
            "human", "assistant", "claude", "chatgpt", "conversation",
            "user:", "assistant:",
        ],
    }
    scores = {
        kind: sum(text.count(token) for token in tokens)
        for kind, tokens in signals.items()
    }
    primary = max(scores, key=lambda kind: (scores[kind], kind))
    if scores[primary] == 0:
        primary = "general_synthesis"
    return {
        "source_path": str(source),
        "source_label": source.name,
        "line_count": len(lines),
        "profile": primary,
        "signals": scores,
    }


def _artifact_specs(profile: str) -> list[dict[str, str]]:
    base = [
        {
            "path": "overview.md",
            "purpose": "State the source's main topic, why it matters, and the evidence base.",
        },
        {
            "path": "claims-and-evidence.md",
            "purpose": "Separate direct claims, inferences, open questions, and source references.",
        },
        {
            "path": "open-questions.md",
            "purpose": "Capture unresolved questions before anything becomes durable graph memory.",
        },
    ]
    extras = {
        "technical_design": [
            ("technical-shape.md", "Extract interfaces, data flow, constraints, and implementation risks."),
            ("implementation-plan.md", "Turn the source into a smallest safe implementation slice."),
        ],
        "decision_analysis": [
            ("decision-analysis.md", "Compare options, tradeoffs, decision gates, and reversal criteria."),
            ("risks-and-counterarguments.md", "Challenge the strongest claims and record failure modes."),
        ],
        "incident_or_debug": [
            ("timeline.md", "Reconstruct event order and evidence."),
            ("root-cause-and-actions.md", "Separate symptoms, likely causes, fixes, and follow-up checks."),
        ],
        "research_synthesis": [
            ("research-synthesis.md", "Group evidence by claim and note confidence boundaries."),
            ("counterarguments.md", "Preserve conflicting evidence and weaker interpretations."),
        ],
        "planning": [
            ("implementation-plan.md", "Define phases, owner actions, tests, and release gates."),
            ("risks-and-counterarguments.md", "Name scope risks, kill criteria, and objections."),
        ],
        "conversation_synthesis": [
            ("conversation-map.md", "Track how the conversation moves between topics and decisions."),
            ("interaction-contract.md", "Extract workflow language and what the system should do next."),
        ],
        "general_synthesis": [
            ("synthesis.md", "Compile the source into a durable, evidence-backed summary."),
            ("risks-and-counterarguments.md", "Name weak spots and alternative interpretations."),
        ],
    }
    for path, purpose in extras.get(profile, extras["general_synthesis"]):
        base.append({"path": path, "purpose": purpose})
    return base


def build_artifact_plan(source: Path, lines: list[SourceLine]) -> dict[str, Any]:
    profile = _classify_source(source, lines)
    artifacts = _artifact_specs(profile["profile"])
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": _now(),
        "source": profile,
        "artifacts": artifacts,
        "acceptance_criteria": [
            "Claims cite source-local line references.",
            "Candidates remain proposals until ingest review.",
            "Generation does not mutate MYGRAPH_PATH.",
            "Weak or unsupported claims are surfaced for inspection.",
        ],
    }


def _line_ref(line: SourceLine) -> str:
    return f"{line.number}"


def _write_artifacts(out_dir: Path, plan: dict[str, Any],
                     lines: list[SourceLine], iterations: int) -> list[dict[str, Any]]:
    artifacts = []
    heading = _heading(lines)
    first = _choose_excerpt(lines)
    decision = _choose_excerpt(lines, ["decision", "decide", "agreed", "approve"])
    question = _choose_excerpt(lines, ["?", "unknown", "open question", "unclear"])
    risk = _choose_excerpt(lines, ["risk", "concern", "challenge", "counter", "failure"])

    source_name = Path(plan["source"]["source_path"]).name
    profile = plan["source"]["profile"]
    evidence_key = (
        f"- `{source_name}:{_line_ref(first)}`: {first.text}\n"
        + (f"- `{source_name}:{_line_ref(heading)}`: {heading.text}\n" if heading else "")
    )

    for spec in plan["artifacts"]:
        path = out_dir / spec["path"]
        title = spec["path"].removesuffix(".md").replace("-", " ").title()
        body = [
            f"# {title}",
            "",
            f"Source: `{source_name}`",
            f"Profile: `{profile}`",
            f"Purpose: {spec['purpose']}",
            "",
            "## Evidence Key",
            evidence_key.rstrip(),
            "",
        ]
        if spec["path"] == "claims-and-evidence.md":
            body.extend([
                "## Claims",
                "",
                "| Claim | Class | Evidence | Notes |",
                "|---|---|---|---|",
                f"| {heading.text if heading else source_name} | Fact | `{source_name}:{_line_ref(heading or first)}` | Source heading or filename-derived topic. |",
                f"| {first.text} | Fact | `{source_name}:{_line_ref(first)}` | Preserved as literal source text. |",
                f"| The source may contain unresolved work. | Inference | `{source_name}:{_line_ref(question)}` | Review before promotion. |",
            ])
        elif spec["path"] == "open-questions.md":
            body.extend([
                "## Open Questions",
                "",
                f"- What should be promoted into graph memory? Evidence: `{source_name}:{_line_ref(first)}`",
                f"- Which claims need stronger provenance before approval? Evidence: `{source_name}:{_line_ref(question)}`",
                f"- What should stay artifact-local for now? Evidence: `{source_name}:{_line_ref(risk)}`",
            ])
        elif "risk" in spec["path"] or "counter" in spec["path"]:
            body.extend([
                "## Risks And Counterarguments",
                "",
                f"- A generated candidate may overstate the source. Evidence: `{source_name}:{_line_ref(risk)}`",
                "- Edges are reasoning claims and should be inspected before durable promotion.",
                "- The workspace is a thinking surface; the graph is accepted memory.",
            ])
        elif "implementation" in spec["path"]:
            body.extend([
                "## Implementation Slice",
                "",
                "- Generate the workspace.",
                "- Inspect artifacts and candidates.",
                "- Challenge weak claims.",
                "- Add to graph only after validation and review.",
            ])
        elif "decision" in spec["path"]:
            body.extend([
                "## Decision Frame",
                "",
                f"- Candidate decision evidence: `{source_name}:{_line_ref(decision)}`",
                "- Promotion gate: only accepted candidates enter MYGRAPH_PATH.",
                "- Reversal gate: leave uncertain claims artifact-local.",
            ])
        else:
            body.extend([
                "## Summary",
                "",
                f"- Main source signal: {first.text}",
                f"- Evidence: `{source_name}:{_line_ref(first)}`",
                "",
                "## Next Action",
                "",
                "Inspect the generated candidates before adding anything to the graph.",
            ])
        body.extend([
            "",
            "## Generation Notes",
            "",
            f"- Iterations requested: `{iterations}`.",
            "- v0.7.0 uses a conservative local generator; richer LLM passes can refine this workspace.",
        ])
        path.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
        artifacts.append({"path": spec["path"], "purpose": spec["purpose"]})
    return artifacts


def _candidate_payload(source: Path, lines: list[SourceLine]) -> dict[str, Any]:
    decl = build_source_decl(source)
    source_text = source.read_text(encoding="utf-8")
    heading = _heading(lines)
    first = _choose_excerpt(lines)
    question = _choose_excerpt(lines, ["?", "unknown", "open question", "unclear"])
    decision = _choose_excerpt(lines, ["decision", "decide", "agreed", "approve"])

    topic_label = heading.text if heading else source.stem.replace("-", " ").replace("_", " ").title()
    topic_id = f"topic:{slug(topic_label) or slug(source.stem)}"
    idea_label = _first_sentence(first.text) or topic_label
    idea_id = f"idea:{slug(idea_label) or slug(source.stem + '-idea')}"
    question_label = _first_sentence(question.text.rstrip("?")) or f"What remains open in {topic_label}?"
    question_id = f"question:{slug(question_label) or slug(source.stem + '-question')}"

    nodes = [
        {
            "id": topic_id,
            "type": "topic",
            "label": topic_label,
            "body": f"Source-derived topic from {source.name}.",
            "confidence": "high" if (heading or first).text else "medium",
            "excerpt": (heading or first).text,
        },
        {
            "id": idea_id,
            "type": "idea",
            "label": idea_label,
            "body": "Candidate durable idea extracted during deep-dive generation.",
            "confidence": "high" if first.text else "medium",
            "excerpt": first.text,
        },
        {
            "id": question_id,
            "type": "question",
            "label": question_label,
            "body": "Candidate question preserved for review before graph promotion.",
            "confidence": "high" if question.text else "medium",
            "excerpt": question.text,
        },
    ]
    edges = [
        {
            "src": idea_id,
            "dst": topic_id,
            "type": "RELATES_TO",
            "confidence": "medium",
            "excerpt": first.text,
        },
        {
            "src": question_id,
            "dst": topic_id,
            "type": "ABOUT",
            "confidence": "medium",
            "excerpt": question.text,
        },
    ]
    if decision.text and decision.text != first.text:
        decision_label = _first_sentence(decision.text) or f"Decision in {topic_label}"
        decision_id = f"decision:{slug(decision_label) or slug(source.stem + '-decision')}"
        nodes.append({
            "id": decision_id,
            "type": "decision",
            "label": decision_label,
            "body": "Candidate decision surfaced by deep-dive generation.",
            "confidence": "high",
            "excerpt": decision.text,
        })
        edges.append({
            "src": decision_id,
            "dst": question_id,
            "type": "ABOUT",
            "confidence": "medium",
            "excerpt": decision.text,
        })

    payload = {
        "source": {
            "id": decl["source_id"],
            "label": decl["source_label"],
            "body": source_text[:1000],
        },
        "nodes": nodes,
        "edges": edges,
        "_meta": {
            "source_path": decl["source_path"],
            "ingested_at": decl["ingested_at"],
            "backend": "deep-dive-local",
            "schema_version": SCHEMA_VERSION,
        },
    }
    ensure_provenance_edges(payload)
    return payload


def _validation_report(payload: dict[str, Any], source_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    validated, manifest = validate(payload, source_text)
    return validated, {
        "schema_version": SCHEMA_VERSION,
        "validated_at": _now(),
        "accepted_nodes": len(manifest.accepted_nodes),
        "accepted_edges": len(manifest.accepted_edges),
        "demoted_nodes": [
            {"id": node.get("id"), "reason": reason}
            for node, reason in manifest.demoted_nodes
        ],
        "rejected_nodes": [
            {"id": node.get("id"), "reason": reason}
            for node, reason in manifest.rejected_nodes
        ],
        "rejected_edges": [
            {
                "src": edge.get("src"),
                "dst": edge.get("dst"),
                "type": edge.get("type"),
                "reason": reason,
            }
            for edge, reason in manifest.rejected_edges
        ],
    }


def _artifact_graph(plan: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "metadata": {
            "title": f"Deep Dive Workspace: {plan['source']['source_label']}",
            "source": plan["source"]["source_path"],
            "created_at": _now(),
            "canonical_graph_ingested": False,
        },
        "nodes": [
            {
                "id": f"artifact:{slug(artifact['path'])}",
                "type": "artifact",
                "label": artifact["path"],
                "description": artifact["purpose"],
            }
            for artifact in plan["artifacts"]
        ],
        "candidate_node_ids": [node["id"] for node in candidates.get("nodes", [])],
        "candidate_edge_count": len(candidates.get("edges", [])),
    }


def generate_workspace(source: Path, out_dir: Path, *,
                       iterations: int = DEFAULT_ITERATIONS,
                       write_candidates: bool = True) -> dict[str, Any]:
    source = source.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"deep-dive: source not found: {source}")
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = _read_lines(source)
    plan = build_artifact_plan(source, lines)
    artifacts = _write_artifacts(out_dir, plan, lines, iterations)
    (out_dir / "artifact-plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    candidates_path = None
    validation_path = None
    artifact_graph_path = out_dir / "artifact-graph.json"
    validation_report: dict[str, Any] | None = None
    if write_candidates:
        payload = _candidate_payload(source, lines)
        validated, validation_report = _validation_report(
            payload, source.read_text(encoding="utf-8")
        )
        candidates_path = out_dir / f"{source.stem}.candidates.json"
        candidates_path.write_text(
            json.dumps(validated, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        validation_path = out_dir / "validation-report.json"
        validation_path.write_text(
            json.dumps(validation_report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        artifact_graph_path.write_text(
            json.dumps(_artifact_graph(plan, validated), indent=2, sort_keys=True),
            encoding="utf-8",
        )
    else:
        artifact_graph_path.write_text(
            json.dumps(_artifact_graph(plan, {"nodes": [], "edges": []}), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _now(),
        "source_path": str(source),
        "workspace_path": str(out_dir),
        "artifacts": artifacts,
        "artifact_plan_path": str(out_dir / "artifact-plan.json"),
        "artifact_graph_path": str(artifact_graph_path),
        "candidates_path": str(candidates_path) if candidates_path else None,
        "validation_report_path": str(validation_path) if validation_path else None,
        "validation": validation_report,
        "graph_mutated": False,
        "next_command": (
            f"mykg deep-dive add-to-graph {out_dir}"
            if candidates_path else
            f"mykg deep-dive inspect {out_dir}"
        ),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def _load_manifest(workspace: Path) -> dict[str, Any]:
    manifest_path = workspace.expanduser().resolve() / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"deep-dive: missing manifest: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def inspect_workspace(workspace: Path) -> str:
    manifest = _load_manifest(workspace)
    lines = [
        f"Deep-dive workspace: {manifest['workspace_path']}",
        f"Source: {manifest['source_path']}",
        f"Artifacts: {len(manifest.get('artifacts', []))}",
    ]
    for artifact in manifest.get("artifacts", []):
        lines.append(f"  - {artifact['path']}: {artifact['purpose']}")
    candidates = manifest.get("candidates_path")
    if candidates:
        payload = json.loads(Path(candidates).read_text(encoding="utf-8"))
        lines.append(f"Candidates: {candidates}")
        lines.append(f"  nodes: {len(payload.get('nodes', []))}")
        lines.append(f"  edges: {len(payload.get('edges', []))}")
    else:
        lines.append("Candidates: none")
    validation = manifest.get("validation")
    if validation:
        lines.append(
            "Validation: "
            f"{validation['accepted_nodes']} nodes / "
            f"{validation['accepted_edges']} edges accepted; "
            f"{len(validation['demoted_nodes'])} demoted; "
            f"{len(validation['rejected_nodes']) + len(validation['rejected_edges'])} rejected"
        )
    lines.append(f"Next: {manifest.get('next_command')}")
    return "\n".join(lines)


def add_to_graph(workspace: Path, extra_args: list[str]) -> int:
    manifest = _load_manifest(workspace)
    source_path = manifest.get("source_path")
    candidates_path = manifest.get("candidates_path")
    if not source_path or not candidates_path:
        print("deep-dive add-to-graph: workspace has no candidates to ingest")
        return 1
    args = [source_path, "--candidates-file", candidates_path, *extra_args]
    return run_ingest(args)


def _parse_generate(args: list[str]) -> tuple[Path, Path, int, bool]:
    if not args or args[0] in {"-h", "--help", "help"}:
        raise ValueError(_usage())
    source = Path(args[0])
    out_dir: Path | None = None
    iterations = DEFAULT_ITERATIONS
    write_candidates = True
    i = 1
    while i < len(args):
        arg = args[i]
        if arg == "--out-dir":
            if i + 1 >= len(args):
                raise ValueError("deep-dive: --out-dir needs a path")
            out_dir = Path(args[i + 1])
            i += 2
        elif arg == "--iterations":
            if i + 1 >= len(args):
                raise ValueError("deep-dive: --iterations needs a number")
            iterations = int(args[i + 1])
            i += 2
        elif arg == "--no-candidates":
            write_candidates = False
            i += 1
        else:
            raise ValueError(f"deep-dive: unknown flag: {arg}")
    if out_dir is None:
        out_dir = source.with_suffix("")
    if iterations < 1:
        raise ValueError("deep-dive: --iterations must be >= 1")
    return source, out_dir, iterations, write_candidates


def run_deep_dive(args: list[str]) -> int:
    if not args or args[0] in {"-h", "--help", "help"}:
        print(_usage())
        return 0
    try:
        if args[0] == "inspect":
            if len(args) != 2:
                print("Usage: mykg deep-dive inspect <workspace>")
                return 1
            print(inspect_workspace(Path(args[1])))
            return 0
        if args[0] == "add-to-graph":
            if len(args) < 2:
                print("Usage: mykg deep-dive add-to-graph <workspace> [ingest flags]")
                return 1
            return add_to_graph(Path(args[1]), args[2:])

        source, out_dir, iterations, write_candidates = _parse_generate(args)
        manifest = generate_workspace(
            source,
            out_dir,
            iterations=iterations,
            write_candidates=write_candidates,
        )
        print(f"deep-dive: wrote workspace -> {manifest['workspace_path']}")
        print(f"deep-dive: artifacts -> {len(manifest['artifacts'])}")
        if manifest.get("candidates_path"):
            print(f"deep-dive: candidates -> {manifest['candidates_path']}")
        print(f"deep-dive: next -> {manifest['next_command']}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(run_deep_dive(sys.argv[1:]))
