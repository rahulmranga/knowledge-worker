import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mygraph.mygraph import Edge, Graph, Node


ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = [
    "</SCRIPT><img src=x onerror=alert(1)>",
    "</script><img src=x onerror=alert(1)>",
    "</ScRiPt >",
    "<!-- <script>",
]


def run_mykg(*args, graph_path):
    return subprocess.run(
        [sys.executable, "-m", "mygraph.mygraph", *args],
        cwd=ROOT,
        env={**os.environ, "MYGRAPH_PATH": str(graph_path)},
        text=True,
        capture_output=True,
        check=False,
    )


def write_hostile_graph(path):
    g = Graph()
    g.add_node(Node(id="source:s", type="source", label="source"))
    for i, payload in enumerate(PAYLOADS):
        nid = f"idea:{i}"
        g.add_node(Node(id=nid, type="idea", label=payload, body=payload))
        g.add_edge(Edge(nid, "source:s", "MENTIONED_IN", "source:s", excerpt=payload))
    g.save(str(path))


def embedded_json(html, name):
    return json.loads(re.search(rf"^const {name} = (.*);$", html, re.MULTILINE).group(1))


class HtmlEmbeddingTest(unittest.TestCase):
    def assert_inert(self, html, names):
        # The payloads survive as data rather than markup.
        self.assertNotIn("<img", html)
        self.assertNotIn("<!--", html)
        for name in names:
            line = re.search(rf"^const {name} = (.*);$", html, re.MULTILINE).group(1)
            self.assertNotIn("<", line)
        labels = {n["label"] for n in embedded_json(html, names[-1])["nodes"].values()}
        self.assertTrue(set(PAYLOADS) <= labels)

    def test_memory_audit_escapes_embedded_markup(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "graph.jsonld"
            write_hostile_graph(graph_path)
            html_path = Path(tmp) / "audit.html"
            result = run_mykg(
                "audit", "--out", str(Path(tmp) / "a.json"), "--html", str(html_path),
                graph_path=graph_path,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assert_inert(html_path.read_text(encoding="utf-8"), ["AUDIT", "GRAPH"])

    def test_memory_audit_keeps_placeholder_text_as_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "graph.jsonld"
            g = Graph()
            g.add_node(Node(id="source:s", type="source", label="source"))
            for name in ("AUDIT", "GRAPH"):
                nid = f"idea:{name.lower()}"
                g.add_node(Node(id=nid, type="idea", label=f"__{name}_JSON__"))
                g.add_edge(Edge(nid, "source:s", "MENTIONED_IN", "source:s"))
            g.save(str(graph_path))
            html_path = Path(tmp) / "audit.html"
            result = run_mykg(
                "audit", "--out", str(Path(tmp) / "a.json"), "--html", str(html_path),
                graph_path=graph_path,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            html = html_path.read_text(encoding="utf-8")
            embedded_json(html, "AUDIT")
            labels = {n["label"] for n in embedded_json(html, "GRAPH")["nodes"].values()}
            self.assertTrue({"__AUDIT_JSON__", "__GRAPH_JSON__"} <= labels)

    def test_viz_escapes_embedded_markup(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "graph.jsonld"
            write_hostile_graph(graph_path)
            html_path = Path(tmp) / "viz.html"
            result = run_mykg(
                "viz", "--no-open", "--out", str(html_path), graph_path=graph_path,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assert_inert(html_path.read_text(encoding="utf-8"), ["GRAPH_DATA"])


if __name__ == "__main__":
    unittest.main()
