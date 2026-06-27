import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_GRAPH = ROOT / "examples" / "demo_graph.json"


def run_mykg(*args, env=None):
    merged_env = os.environ.copy()
    merged_env["MYGRAPH_PATH"] = str(DEMO_GRAPH)
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


class CliRegressionTest(unittest.TestCase):
    def test_no_args_prints_usage_and_nonzero(self):
        result = run_mykg()

        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage:", result.stdout)

    def test_unknown_command_prints_usage_and_nonzero(self):
        result = run_mykg("nope")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage:", result.stdout)

    def test_query_requires_search_string(self):
        result = run_mykg("query")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Need a query string.", result.stdout)

    def test_path_requires_two_node_ids(self):
        result = run_mykg("path", "person:demo-owner")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Need two node ids.", result.stdout)

    def test_list_requires_type_and_accepts_plural(self):
        missing = run_mykg("list")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("Need a node type.", missing.stdout)

        listed = run_mykg("list", "ideas")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("idea:", listed.stdout)

    def test_state_requires_entry(self):
        result = run_mykg("state")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Need a state entry.", result.stdout)

    def test_ingest_requires_file(self):
        result = run_mykg("ingest")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage: mykg ingest", result.stdout)

    def test_check_default_runs_provenance_and_stale_edges(self):
        result = run_mykg("check")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("provenance violations: 0", result.stdout)
        self.assertIn("stale edges", result.stdout)

    def test_check_source_candidates_without_llm_config_skips_cleanly(self):
        result = run_mykg("check", "--source-candidates", "/definitely/not/a/dir")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("source candidates: 0 evaluated", result.stdout)

    def test_export_ttl_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            out = Path(tmp_raw) / "demo.ttl"

            result = run_mykg("export", "--ttl", "--out", str(out))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(out.exists())
            self.assertIn("@prefix", out.read_text(encoding="utf-8"))

    def test_context_out_writes_file_without_stdout_dump(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            out = Path(tmp_raw) / "context.md"

            result = run_mykg("context", "--out", str(out), "--max-ideas", "2")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(out.exists())
            self.assertIn("# mygraph", out.read_text(encoding="utf-8"))
            self.assertLess(len(result.stdout), 120)

    def test_viz_no_open_writes_html(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            out = Path(tmp_raw) / "demo.html"

            result = run_mykg(
                "viz",
                "--graph",
                str(DEMO_GRAPH),
                "--out",
                str(out),
                "--no-open",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(out.exists())
            html = out.read_text(encoding="utf-8")
            self.assertIn("knowledge-worker", html.lower())
            self.assertIn("graph", html.lower())

    def test_audit_out_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            out = Path(tmp_raw) / "audit.json"

            result = run_mykg("audit", "--out", str(out))

            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], "memory-audit/v1")
            self.assertIn("ranked", data)
            self.assertIn("centrality", data)

    def test_discover_writes_report_and_candidates(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            out = Path(tmp_raw) / "discovery.json"
            candidates = Path(tmp_raw) / "discovery.candidates.json"

            result = run_mykg(
                "discover",
                "--out",
                str(out),
                "--candidates",
                str(candidates),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(out.read_text(encoding="utf-8"))
            proposals = json.loads(candidates.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], 1)
            self.assertIn("proposals", proposals)
            self.assertTrue(
                all(item["status"] == "proposed" for item in proposals["proposals"])
            )

    def test_deep_dive_subcommands_validate_arguments(self):
        inspect = run_mykg("deep-dive", "inspect")
        self.assertEqual(inspect.returncode, 1)
        self.assertIn("inspect <workspace>", inspect.stdout)

        add = run_mykg("deep-dive", "add-to-graph")
        self.assertEqual(add.returncode, 1)
        self.assertIn("add-to-graph <workspace>", add.stdout)


if __name__ == "__main__":
    unittest.main()
