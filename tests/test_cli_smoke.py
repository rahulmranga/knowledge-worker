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
        self.assertIn("--backend claude|openai|ollama", result.stdout)
        self.assertIn("mykg deep-dive <source.md>", result.stdout)

    def test_ingest_loads_openai_backend_without_sdk_import(self):
        from mygraph.ingest import _load_extractor

        extract = _load_extractor("openai")
        self.assertEqual(extract.__name__, "extract")

    def test_demo_graph_query_runs_from_module(self):
        result = run_mykg(
            "query",
            "provenance",
            env={"MYGRAPH_PATH": str(ROOT / "examples" / "demo_graph.json")},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Matches for 'provenance'", result.stdout)
        self.assertIn("idea:provenance-first", result.stdout)

    def test_audit_emits_analytics_and_memory_audit_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "analytics.json"
            html = Path(tmp) / "memory_audit.html"
            result = run_mykg(
                "audit",
                "--out",
                str(out),
                "--html",
                str(html),
                env={"MYGRAPH_PATH": str(ROOT / "examples" / "demo_graph.json")},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("audit: wrote", result.stdout)
            data = json.loads(out.read_text())
            self.assertEqual(data["schema_version"], "memory-audit/v1")
            self.assertIn("important_concepts", data["ranked"])
            self.assertIn("bridge_ideas", data["ranked"])
            self.assertIn("idea_attractors", data["ranked"])
            self.assertIn("idea_generators", data["ranked"])
            self.assertIn("weak_claims", data["ranked"])
            self.assertIn("weak_claim_queue", data["ranked"])
            self.assertIn("proof_trail", data["ranked"])
            self.assertIn("directed_flow", data)
            self.assertIn("legwork_queue", data)
            self.assertIn("pagerank", data["centrality"])
            self.assertIn("betweenness", data["centrality"])
            self.assertIn("core_number", data["centrality"])
            self.assertIn("semantic_in_degree", data["centrality"])
            self.assertIn("semantic_out_degree", data["centrality"])
            self.assertIn("provenance_coverage", data)
            self.assertTrue(html.exists())
            html_text = html.read_text()
            self.assertIn("Memory Audit", html_text)
            self.assertIn("Idea Attractors", html_text)
            self.assertIn("Weak Claim Queue", html_text)

    def test_seed_summary_and_context_use_temp_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MYGRAPH_PATH": str(Path(tmp) / "demo.json")}

            seed = run_mykg("seed", env=env)
            self.assertEqual(seed.returncode, 0, seed.stderr)
            self.assertIn("Seeded.", seed.stdout)

            summary = run_mykg("summary", env=env)
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertIn("49 nodes, 91 edges", summary.stdout)

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
