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


class CliSmokeTest(unittest.TestCase):
    def test_help_runs_cleanly(self):
        result = run_mykg("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mykg query <string>", result.stdout)

    def test_demo_graph_query_runs_from_module(self):
        result = run_mykg(
            "query",
            "provenance",
            env={"MYGRAPH_PATH": str(ROOT / "examples" / "demo_graph.json")},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Matches for 'provenance'", result.stdout)
        self.assertIn("idea:provenance-first", result.stdout)

    def test_seed_summary_and_context_use_temp_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MYGRAPH_PATH": str(Path(tmp) / "demo.json")}

            seed = run_mykg("seed", env=env)
            self.assertEqual(seed.returncode, 0, seed.stderr)
            self.assertIn("Seeded.", seed.stdout)

            summary = run_mykg("summary", env=env)
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertIn("12 nodes, 19 edges", summary.stdout)

            context = run_mykg("context", "--max-ideas", "2", env=env)
            self.assertEqual(context.returncode, 0, context.stderr)
            self.assertIn("# mygraph", context.stdout)
            self.assertIn("## Ideas", context.stdout)

    def test_legacy_private_node_types_are_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "legacy.json"
            graph_path.write_text(json.dumps({
                "nodes": {
                    "source:test": {
                        "id": "source:test",
                        "type": "source",
                        "label": "test.md",
                    },
                    "observation:test": {
                        "id": "observation:test",
                        "type": "observation",
                        "label": "A saved observation",
                        "body": "Legacy/private graph type.",
                    },
                },
                "edges": [{
                    "src": "observation:test",
                    "dst": "source:test",
                    "type": "MENTIONED_IN",
                    "source_id": "source:test",
                    "excerpt": "Legacy/private graph type.",
                }],
            }))
            env = {"MYGRAPH_PATH": str(graph_path)}

            summary = run_mykg("summary", env=env)
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertIn("observation", summary.stdout)

            listed = run_mykg("list", "observations", env=env)
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertIn("observation:test", listed.stdout)


if __name__ == "__main__":
    unittest.main()
