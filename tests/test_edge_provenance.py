import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mygraph import Graph, Node
from mygraph.ingest import run_ingest
from mygraph.review import review
from mygraph.validator import validate


SOURCE = "Solar lamps support the garden project."


def candidates():
    return {
        "source": {"id": "source:garden-note", "label": "garden.md", "body": SOURCE},
        "nodes": [
            {"id": "idea:solar-lamps", "type": "idea", "label": "Solar lamps",
             "confidence": "high", "excerpt": "Solar lamps"},
            {"id": "project:garden", "type": "project", "label": "Garden project",
             "confidence": "high", "excerpt": "garden project"},
        ],
        "edges": [{"src": "idea:solar-lamps", "dst": "project:garden",
                   "type": "SERVES", "confidence": "high", "excerpt": SOURCE}],
    }


class EdgeProvenanceTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.graph_path = self.root / "graph.jsonld"
        env = patch.dict(os.environ, {"MYGRAPH_PATH": str(self.graph_path)})
        env.start()
        self.addCleanup(env.stop)
        self.records = []
        # Eval logs are package-local by default: keep these fictional tests in memory.
        for module in ("ingest", "review", "merge"):
            logger = patch(f"mygraph.{module}.eval_append", side_effect=self.records.append)
            logger.start()
            self.addCleanup(logger.stop)

    def seed_endpoints(self):
        g = Graph()
        for node in candidates()["nodes"]:
            g.add_node(Node(id=node["id"], type=node["type"], label=node["label"]))
        g.save()

    def ingest(self, payload, *flags):
        source = self.root / "garden.md"
        source.write_text(SOURCE, encoding="utf-8")
        candidate_path = self.root / "candidates.json"
        candidate_path.write_text(json.dumps(payload), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            return run_ingest([str(source), "--candidates-file", str(candidate_path),
                               "--non-interactive", *flags])

    def test_high_edges_without_matching_excerpts_are_demoted(self):
        for excerpt, reason in [(None, "no_excerpt"), (" \n\t", "no_excerpt"),
                                ("Windmills power the harbor.", "excerpt_not_in_source")]:
            with self.subTest(excerpt=excerpt):
                payload = candidates()
                if excerpt is None:
                    payload["edges"][0].pop("excerpt")
                else:
                    payload["edges"][0]["excerpt"] = excerpt
                validated, manifest = validate(payload, SOURCE)
                self.assertEqual(validated["edges"][0]["confidence"], "low")
                self.assertEqual([r for _, r in manifest.demoted_edges], [reason])
                self.assertIn("0 nodes / 1 edges", manifest.summary())

    def test_matching_excerpt_normalizes_whitespace_and_case(self):
        payload = candidates()
        payload["edges"][0]["excerpt"] = "  SOLAR\nlamps support\tthe garden project. "
        validated, manifest = validate(payload, SOURCE)
        self.assertEqual(validated["edges"][0]["confidence"], "high")
        self.assertEqual(manifest.demoted_edges, [])

    def test_invalid_or_orphan_edges_still_get_rejected(self):
        for change in [{"type": "INVALID"}, {"confidence": "certain"},
                       {"src": "not-an-id"}, {"dst": "project:unknown"}]:
            with self.subTest(change=change):
                payload = candidates()
                payload["edges"][0].update(change)
                validated, manifest = validate(payload, SOURCE)
                self.assertEqual(validated["edges"], [])
                self.assertEqual(len(manifest.rejected_edges), 1)

    def test_auto_high_filters_edges_even_between_existing_nodes(self):
        self.seed_endpoints()
        for confidence in ["high", "medium", "low"]:
            with self.subTest(confidence=confidence):
                payload = candidates()
                payload["nodes"] = []
                payload["edges"][0]["confidence"] = confidence
                validated, _ = validate(payload, SOURCE)
                approved = review(validated, SOURCE, auto_accept_high=True)
                self.assertEqual(len(approved["edges"]), int(confidence == "high"))

    def test_auto_all_remains_an_explicit_override_for_demoted_edges(self):
        payload = candidates()
        payload["edges"][0].pop("excerpt")
        validated, _ = validate(payload, SOURCE)
        approved = review(validated, SOURCE, auto_accept_high=True, auto_accept_all=True)
        self.assertEqual(len(approved["edges"]), 1)
        self.assertEqual(approved["edges"][0]["confidence"], "low")

    def test_default_headless_ingest_does_not_promote_unsupported_edges(self):
        for existing in [False, True]:
            for excerpt in [None, "Windmills power the harbor."]:
                with self.subTest(existing=existing, excerpt=excerpt):
                    self.graph_path.unlink(missing_ok=True)
                    if existing:
                        self.seed_endpoints()
                    payload = candidates()
                    payload["edges"][0]["excerpt"] = excerpt
                    self.assertEqual(self.ingest(payload), 0)
                    g = Graph.load()
                    self.assertIn("idea:solar-lamps", g.nodes)
                    self.assertFalse(any(e.type == "SERVES" for e in g.edges))
                    manifest = next(r for r in reversed(self.records)
                                    if r["kind"] == "extract_manifest")
                    self.assertEqual(manifest["n_demoted_edges"], 1)
                    self.assertEqual(manifest["demotions_e"][0]["type"], "SERVES")

    def test_supported_ingest_is_idempotent(self):
        payload = candidates()
        self.assertEqual(self.ingest(copy.deepcopy(payload), "--auto-accept-high"), 0)
        first = Graph.load()
        edges = [e for e in first.edges if e.type == "SERVES"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].confidence, "high")
        self.assertEqual(edges[0].excerpt, SOURCE)
        self.assertEqual(self.ingest(copy.deepcopy(payload), "--auto-accept-high"), 0)
        second = Graph.load()
        self.assertEqual(set(first.nodes), set(second.nodes))
        self.assertEqual(len(first.edges), len(second.edges))
        complete = [r for r in self.records if r["kind"] == "ingest_complete"][-1]
        self.assertEqual((complete["nodes_added"], complete["edges_added"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
