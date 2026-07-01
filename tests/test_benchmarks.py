import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_GRAPH = ROOT / "examples" / "demo_graph.jsonld"

PUBLIC_NODE_TYPES = {
    "person",
    "topic",
    "idea",
    "project",
    "goal",
    "question",
    "decision",
    "reference",
    "source",
}

PUBLIC_EDGE_TYPES = {
    "HAS_IDEA",
    "RELATES_TO",
    "SUPPORTED_BY",
    "CHALLENGES",
    "SERVES",
    "INVOLVES",
    "ABOUT",
    "MENTIONED_IN",
    "MADE_AT",
}


def mentions_coggrag(item):
    return "reference:coggrag" in {
        item.get("id"),
        item.get("src"),
        item.get("dst"),
    }


def run_mykg(*args):
    env = os.environ.copy()
    env["MYGRAPH_PATH"] = str(DEMO_GRAPH)
    return subprocess.run(
        [sys.executable, "-m", "mygraph.mygraph", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def load_demo_graph():
    return json.loads(DEMO_GRAPH.read_text())


def iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


class BenchmarkTest(unittest.TestCase):
    def load_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "audit.json"
            result = run_mykg("audit", "--out", str(out))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(out.exists())
            return json.loads(out.read_text())

    def test_b1_provenance_check_is_clean(self):
        result = run_mykg("check", "--provenance")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("provenance violations: 0", result.stdout)

    def test_b2_audit_reports_complete_provenance_coverage(self):
        data = self.load_audit()
        coverage = data["provenance_coverage"]

        self.assertEqual(coverage["node_coverage"], 1.0)
        self.assertEqual(coverage["edge_source_coverage"], 1.0)
        self.assertEqual(coverage["excerpt_coverage"], 1.0)
        self.assertEqual(coverage["missing_nodes"], [])
        self.assertEqual(coverage["edges_missing_source_id"], [])

    def test_b3_query_returns_relevant_node_and_source_excerpt(self):
        result = run_mykg("query", "provenance")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("idea:provenance-first", result.stdout)
        self.assertIn("Every durable claim needs source evidence.", result.stdout)
        self.assertIn("provenance:", result.stdout)

    def test_b4_path_finding_connects_owner_to_goal(self):
        result = run_mykg(
            "path",
            "person:demo-owner",
            "goal:trusted-ai-assistance",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Path from person:demo-owner to goal:trusted-ai-assistance", result.stdout)
        self.assertIn("person:demo-owner", result.stdout)
        self.assertIn("goal:trusted-ai-assistance", result.stdout)
        path_lines = [line for line in result.stdout.splitlines() if line.startswith("  [")]
        self.assertGreaterEqual(len(path_lines), 3, result.stdout)
        self.assertNotIn("No path", result.stdout)

    def test_b5_weak_claim_detection_feeds_review_queue(self):
        data = self.load_audit()
        weak_claims = data["ranked"]["weak_claims"]
        weak_claim_queue = data["ranked"]["weak_claim_queue"]

        self.assertGreater(len(weak_claims), 0)
        self.assertGreater(len(weak_claim_queue), 0)
        self.assertTrue(
            any(mentions_coggrag(item) for item in weak_claims),
            weak_claims,
        )
        self.assertTrue(
            any(mentions_coggrag(item) for item in weak_claim_queue),
            weak_claim_queue,
        )

    def test_b6_directed_audit_has_generators_and_stable_attractor_shape(self):
        data = self.load_audit()
        ranked = data["ranked"]
        directed_flow = data["directed_flow"]

        self.assertIsInstance(ranked["idea_attractors"], list)
        self.assertIsInstance(ranked["idea_generators"], list)
        self.assertGreater(len(ranked["idea_generators"]), 0)
        self.assertIn("idea_attractors", directed_flow)
        self.assertIn("idea_generators", directed_flow)
        self.assertIsInstance(directed_flow["idea_attractors"], list)
        self.assertIsInstance(directed_flow["idea_generators"], list)

    def test_b7_context_export_stays_compact(self):
        result = run_mykg("context", "--max-ideas", "5")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(len(result.stdout), 3000)
        self.assertIn("# mygraph", result.stdout)
        self.assertIn("## Goals", result.stdout)
        self.assertIn("## Ideas", result.stdout)
        self.assertIn("## Recent Sources", result.stdout)

    def test_b8_demo_fixture_respects_public_privacy_boundary(self):
        graph = load_demo_graph()

        for node in graph["nodes"].values():
            self.assertIn(node["type"], PUBLIC_NODE_TYPES, node)

        for edge in graph["edges"]:
            self.assertIn(edge["type"], PUBLIC_EDGE_TYPES, edge)

        person_nodes = [
            node for node in graph["nodes"].values() if node["type"] == "person"
        ]
        self.assertEqual([node["id"] for node in person_nodes], ["person:demo-owner"])

        for text in iter_strings(graph):
            self.assertIsNone(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text), text)
            self.assertIsNone(re.search(r"(^|[\"' ])(/Users/|/home/|C:\\\\Users\\\\)", text), text)

        gitignore = (ROOT / ".gitignore").read_text()
        self.assertIn("mygraph/mygraph.json", gitignore)
        self.assertIn("mygraph/mygraph.jsonld", gitignore)

        if (ROOT / ".git").exists():
            tracked = subprocess.run(
                ["git", "ls-files", "mygraph/mygraph.jsonld", "mygraph/mygraph.json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(tracked.returncode, 0, tracked.stderr)
            self.assertEqual(tracked.stdout.strip(), "")

    def test_b9_absent_query_says_no_nodes_match_plainly(self):
        missing_term = "unlikely-absent-benchmark-token"
        result = run_mykg("query", missing_term)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"No nodes match '{missing_term}'.", result.stdout)
        self.assertNotIn("Matches for", result.stdout)


if __name__ == "__main__":
    unittest.main()
