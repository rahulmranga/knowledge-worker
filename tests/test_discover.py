from __future__ import annotations

import json
import unittest
from pathlib import Path

from mygraph.discover import build_discovery, extract_candidates
from mygraph.mygraph import Graph

ROOT = Path(__file__).resolve().parent.parent
DEMO_GRAPH = ROOT / "examples" / "demo_graph.jsonld"


class DiscoverDemoGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph_bytes = DEMO_GRAPH.read_bytes()
        cls.g = Graph.load(str(DEMO_GRAPH))
        cls.report = build_discovery(cls.g, limit=10, stale_days=30)

    def test_report_has_all_sections(self):
        for section in (
            "staleness_radar", "co_mentions", "serves_candidates",
            "related_candidates", "question_debt", "corroboration",
            "bridges", "tensions",
        ):
            self.assertIn(section, self.report)

    def test_demo_graph_meets_launch_fixture_spec(self):
        by_type = {}
        for node in self.g.nodes.values():
            by_type[node.type] = by_type.get(node.type, 0) + 1
        self.assertEqual(by_type["project"], 3)
        self.assertEqual(by_type["goal"], 4)
        self.assertEqual(by_type["decision"], 8)
        self.assertEqual(by_type["idea"], 12)
        self.assertEqual(by_type["source"], 6)
        self.assertEqual(by_type["reference"], 5)
        weak_edges = [e for e in self.g.edges if e.confidence != "high"]
        self.assertGreaterEqual(len(weak_edges), 3)
        self.assertGreaterEqual(len(self.report["bridges"]["bridge_edges"]), 2)

    def test_staleness_radar_flags_the_old_era(self):
        stale_ids = {row["id"] for row in self.report["staleness_radar"]["stale"]}
        self.assertIn("idea:low-power-mesh", stale_ids)
        # the bridge idea was re-mentioned recently, so it stays warm
        self.assertNotIn("idea:sensor-data-as-memory", stale_ids)

    def test_co_mentions_surface_unlinked_recurring_pairs(self):
        pairs = {
            frozenset((row["src"], row["dst"])) for row in self.report["co_mentions"]
        }
        self.assertIn(
            frozenset(("idea:sensor-data-as-memory", "topic:provenance")), pairs)
        self.assertIn(
            frozenset(("idea:write-what-you-build", "project:garden-sensors")), pairs)

    def test_question_debt_separates_open_from_answered(self):
        open_ids = {row["id"] for row in self.report["question_debt"]["open"]}
        self.assertIn("question:battery-life-winter", open_ids)
        answered = {
            (row["src"], row["dst"])
            for row in self.report["question_debt"]["answers_detected"]
        }
        self.assertIn(("decision:json-first", "question:storage-backend"), answered)
        self.assertNotIn("question:storage-backend", open_ids)

    def test_tensions_detect_contested_claims(self):
        pairs = {
            (row["src"], row["dst"]) for row in self.report["tensions"]
        }
        self.assertIn(
            ("question:battery-life-winter", "idea:low-power-mesh"), pairs)

    def test_corroboration_counts_distinct_sources(self):
        distribution = self.report["corroboration"]["source_count_distribution"]
        self.assertIn(3, distribution)  # project:garden-sensors has 3 sources
        single_ids = {row["id"] for row in self.report["corroboration"]["single_source"]}
        self.assertNotIn("project:garden-sensors", single_ids)

    def test_candidates_are_proposals_only(self):
        payload = extract_candidates(self.report)
        self.assertGreater(len(payload["proposals"]), 0)
        for proposal in payload["proposals"]:
            self.assertEqual(proposal["status"], "proposed")
            self.assertIn(proposal["type"], {
                "CO_MENTIONED_WITH", "SERVES_CANDIDATE", "RELATES_TO",
                "TENSION_WITH", "BRIDGES",
            })

    def test_discover_is_deterministic_and_read_only(self):
        second = build_discovery(Graph.load(str(DEMO_GRAPH)), limit=10, stale_days=30)
        self.assertEqual(
            json.dumps(self.report, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )
        self.assertEqual(DEMO_GRAPH.read_bytes(), self.graph_bytes)


if __name__ == "__main__":
    unittest.main()
