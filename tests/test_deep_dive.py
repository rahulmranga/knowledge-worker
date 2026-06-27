import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mygraph.deep_dive import build_artifact_plan, generate_workspace
from mygraph.deep_dive import _read_lines
from mygraph.validator import validate


ROOT = Path(__file__).resolve().parents[1]


def run_mykg(*args, env=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "mygraph.mygraph", *args],
        cwd=ROOT,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


class DeepDiveCliTest(unittest.TestCase):
    def _source(self, tmp: Path) -> Path:
        source = tmp / "release-note.md"
        source.write_text(
            "\n".join([
                "# Release Interaction Model",
                "",
                "We need a decision about how generated candidates enter graph memory.",
                "The key risk is silent mutation without provenance review.",
                "Open question: which claims should stay artifact-local?",
            ]),
            encoding="utf-8",
        )
        return source

    def test_help_mentions_deep_dive(self):
        result = run_mykg("deep-dive", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mykg deep-dive <source.md>", result.stdout)
        self.assertIn("add-to-graph", result.stdout)

    def test_top_level_help_includes_deep_dive_commands(self):
        result = run_mykg("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mykg deep-dive <source.md>", result.stdout)
        self.assertIn("mykg deep-dive inspect <workspace>", result.stdout)
        self.assertIn("mykg deep-dive add-to-graph <workspace>", result.stdout)

    def test_missing_source_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            missing = tmp / "missing.md"
            workspace = tmp / "workspace"

            result = run_mykg("deep-dive", str(missing), "--out-dir", str(workspace))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source not found", result.stdout)

    def test_missing_out_dir_value_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            source = self._source(Path(tmp_raw))

            result = run_mykg("deep-dive", str(source), "--out-dir")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--out-dir needs a path", result.stdout)

    def test_unknown_flag_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            source = self._source(Path(tmp_raw))

            result = run_mykg("deep-dive", str(source), "--wat")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown flag", result.stdout)

    def test_iterations_must_be_positive(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            source = self._source(Path(tmp_raw))

            result = run_mykg("deep-dive", str(source), "--iterations", "0")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--iterations must be >= 1", result.stdout)

    def test_default_workspace_path_is_source_without_suffix(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = self._source(tmp)
            expected = source.with_suffix("")

            result = run_mykg("deep-dive", str(source))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((expected / "manifest.json").exists())
            self.assertIn(str(expected.resolve()), result.stdout)

    def test_generate_workspace_and_inspect(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = self._source(tmp)
            workspace = tmp / "workspace"

            result = run_mykg("deep-dive", str(source), "--out-dir", str(workspace))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("deep-dive: wrote workspace", result.stdout)
            manifest = json.loads((workspace / "manifest.json").read_text())
            self.assertEqual(manifest["schema_version"], "deep-dive/v1")
            self.assertFalse(manifest["graph_mutated"])
            self.assertTrue(Path(manifest["candidates_path"]).exists())
            self.assertTrue((workspace / "artifact-plan.json").exists())
            self.assertTrue((workspace / "validation-report.json").exists())
            self.assertTrue((workspace / "artifact-graph.json").exists())
            self.assertGreaterEqual(len(manifest["artifacts"]), 3)

            inspect = run_mykg("deep-dive", "inspect", str(workspace))
            self.assertEqual(inspect.returncode, 0, inspect.stderr)
            self.assertIn("Deep-dive workspace:", inspect.stdout)
            self.assertIn("Candidates:", inspect.stdout)
            self.assertIn("Validation:", inspect.stdout)

    def test_no_candidates_workspace_has_no_add_to_graph_next_step(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = self._source(tmp)
            workspace = tmp / "workspace"

            result = run_mykg(
                "deep-dive",
                str(source),
                "--out-dir",
                str(workspace),
                "--no-candidates",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((workspace / "manifest.json").read_text())
            self.assertIsNone(manifest["candidates_path"])
            self.assertIn("inspect", manifest["next_command"])
            inspect = run_mykg("deep-dive", "inspect", str(workspace))
            self.assertEqual(inspect.returncode, 0, inspect.stderr)
            self.assertIn("Candidates: none", inspect.stdout)

            added = run_mykg("deep-dive", "add-to-graph", str(workspace))
            self.assertNotEqual(added.returncode, 0)
            self.assertIn("no candidates to ingest", added.stdout)

    def test_inspect_missing_workspace_manifest_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            workspace = Path(tmp_raw) / "empty"
            workspace.mkdir()

            result = run_mykg("deep-dive", "inspect", str(workspace))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing manifest", result.stdout)

    def test_add_to_graph_missing_workspace_manifest_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            workspace = Path(tmp_raw) / "empty"
            workspace.mkdir()

            result = run_mykg("deep-dive", "add-to-graph", str(workspace))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing manifest", result.stdout)

    def test_generate_does_not_mutate_graph(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = self._source(tmp)
            workspace = tmp / "workspace"
            graph = tmp / "graph.json"
            graph.write_text(json.dumps({"nodes": {}, "edges": []}, sort_keys=True))
            before = graph.read_bytes()

            result = run_mykg(
                "deep-dive",
                str(source),
                "--out-dir",
                str(workspace),
                env={"MYGRAPH_PATH": str(graph)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(graph.read_bytes(), before)

    def test_add_to_graph_uses_existing_ingest_path(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = self._source(tmp)
            workspace = tmp / "workspace"
            graph = tmp / "graph.json"
            env = {"MYGRAPH_PATH": str(graph)}

            generated = run_mykg(
                "deep-dive",
                str(source),
                "--out-dir",
                str(workspace),
                env=env,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)

            added = run_mykg(
                "deep-dive",
                "add-to-graph",
                str(workspace),
                "--non-interactive",
                "--auto-accept-all",
                env=env,
            )

            self.assertEqual(added.returncode, 0, added.stderr)
            self.assertIn("[4/5] merge", added.stdout)
            data = json.loads(graph.read_text())
            self.assertIn("source:release-note", data["nodes"])
            self.assertTrue(
                any(node["type"] == "idea" for node in data["nodes"].values())
            )

    def test_generated_candidates_are_validator_compatible(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = self._source(tmp)
            workspace = tmp / "workspace"

            generate_workspace(source, workspace)
            manifest = json.loads((workspace / "manifest.json").read_text())
            payload = json.loads(Path(manifest["candidates_path"]).read_text())
            validated, manifest_obj = validate(payload, source.read_text())

            self.assertGreaterEqual(len(validated["nodes"]), 3)
            self.assertGreaterEqual(len(validated["edges"]), 3)
            self.assertEqual(len(manifest_obj.rejected_nodes), 0)
            self.assertEqual(len(manifest_obj.rejected_edges), 0)

    def test_validation_report_records_demotions_for_bad_high_confidence_excerpt(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = self._source(tmp)
            workspace = tmp / "workspace"
            generate_workspace(source, workspace)
            payload_path = workspace / "release-note.candidates.json"
            payload = json.loads(payload_path.read_text())
            payload["nodes"][0]["confidence"] = "high"
            payload["nodes"][0]["excerpt"] = "this excerpt is not in the source"

            _, manifest_obj = validate(payload, source.read_text())

            self.assertTrue(
                any(reason == "excerpt_not_in_source"
                    for _, reason in manifest_obj.demoted_nodes)
            )

    def test_artifact_plan_adapts_to_incident_source(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = tmp / "incident.md"
            source.write_text(
                "# Production Outage\n\n"
                "The deployment caused an error and a regression.\n"
                "Debug notes show the server failed after release.\n",
                encoding="utf-8",
            )

            plan = build_artifact_plan(source, _read_lines(source))
            artifact_paths = {artifact["path"] for artifact in plan["artifacts"]}

            self.assertEqual(plan["source"]["profile"], "incident_or_debug")
            self.assertIn("timeline.md", artifact_paths)
            self.assertIn("root-cause-and-actions.md", artifact_paths)

    def test_artifact_plan_adapts_to_planning_source(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = tmp / "plan.md"
            source.write_text(
                "# Release Plan\n\n"
                "Roadmap scope depends on milestone timing and next steps.\n",
                encoding="utf-8",
            )

            plan = build_artifact_plan(source, _read_lines(source))
            artifact_paths = {artifact["path"] for artifact in plan["artifacts"]}

            self.assertEqual(plan["source"]["profile"], "planning")
            self.assertIn("implementation-plan.md", artifact_paths)
            self.assertIn("risks-and-counterarguments.md", artifact_paths)

    def test_add_to_graph_can_auto_accept_high_only(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            source = self._source(tmp)
            workspace = tmp / "workspace"
            graph = tmp / "graph.json"
            env = {"MYGRAPH_PATH": str(graph)}

            generated = run_mykg(
                "deep-dive",
                str(source),
                "--out-dir",
                str(workspace),
                env=env,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)

            added = run_mykg(
                "deep-dive",
                "add-to-graph",
                str(workspace),
                "--non-interactive",
                "--auto-accept-high",
                env=env,
            )

            self.assertEqual(added.returncode, 0, added.stderr)
            data = json.loads(graph.read_text())
            self.assertIn("source:release-note", data["nodes"])
            # The topic and idea have high confidence; the generated question is
            # also high only when an explicit question line is present.
            self.assertGreaterEqual(len(data["nodes"]), 2)


if __name__ == "__main__":
    unittest.main()
