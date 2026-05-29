import unittest

from mygraph.extractor import ensure_provenance_edges


class ExtractorProvenanceBackfillTest(unittest.TestCase):
    def test_backfills_missing_mentioned_in_edges(self):
        payload = {
            "source": {
                "id": "source:test-note",
                "label": "test-note.md",
                "body": "A note about durable memory.",
            },
            "nodes": [
                {
                    "id": "idea:durable-memory",
                    "type": "idea",
                    "label": "Durable memory",
                    "body": "Keep durable memory source-backed.",
                    "confidence": "high",
                    "excerpt": "durable memory",
                },
                {
                    "id": "goal:source-backed-recall",
                    "type": "goal",
                    "label": "Source-backed recall",
                    "body": "Recall should cite sources.",
                    "confidence": "medium",
                    "excerpt": "cite sources",
                },
            ],
            "edges": [],
        }

        injected = ensure_provenance_edges(payload)

        self.assertEqual(injected, 2)
        self.assertEqual(
            {
                (edge["src"], edge["dst"], edge["type"])
                for edge in payload["edges"]
            },
            {
                ("idea:durable-memory", "source:test-note", "MENTIONED_IN"),
                ("goal:source-backed-recall", "source:test-note", "MENTIONED_IN"),
            },
        )

    def test_keeps_existing_mentioned_in_edges(self):
        payload = {
            "source": {
                "id": "source:test-note",
                "label": "test-note.md",
                "body": "A note about durable memory.",
            },
            "nodes": [{
                "id": "idea:durable-memory",
                "type": "idea",
                "label": "Durable memory",
                "confidence": "high",
                "excerpt": "durable memory",
            }],
            "edges": [{
                "src": "idea:durable-memory",
                "dst": "source:test-note",
                "type": "MENTIONED_IN",
                "confidence": "high",
                "excerpt": "durable memory",
            }],
        }

        injected = ensure_provenance_edges(payload)

        self.assertEqual(injected, 0)
        self.assertEqual(len(payload["edges"]), 1)

    def test_handles_null_edges(self):
        payload = {
            "source": {"id": "source:test-note", "label": "test-note.md", "body": ""},
            "nodes": [{
                "id": "idea:durable-memory",
                "type": "idea",
                "label": "Durable memory",
                "confidence": "high",
                "excerpt": "durable memory",
            }],
            "edges": None,
        }

        injected = ensure_provenance_edges(payload)

        self.assertEqual(injected, 1)
        self.assertIsInstance(payload["edges"], list)


if __name__ == "__main__":
    unittest.main()
