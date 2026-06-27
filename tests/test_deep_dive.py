import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
