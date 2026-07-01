"""
owl_io.py — RDF sibling serializations for the graph.

JSON stays canonical. RDF exports are generated from JSON at any time. Turtle
can be re-imported losslessly (round-trip on node + edge counts is a hard test).

Mapping follows the graph model in SPEC.md and the pipeline in DESIGN.md:

  - Node type           → owl:Class under rb:Concept
  - Edge type           → owl:ObjectProperty
  - Node id             → IRI <http://mygraph.local/{id}>
  - Node label / body   → rdfs:label / rdfs:comment
  - Edge metadata       → rb:Assertion (reified) with rb:confidence,
                          rb:excerpt, rb:sourceId, rb:createdAt, rb:lastSeen
  - Source node         → rb:Source (subclass of dcterms:ProvenanceEntity)

Requires `rdflib` (`pip install -e ".[rdf]"`).
"""

from __future__ import annotations

import sys
from pathlib import Path

from mygraph import Graph, Node, Edge, NODE_TYPES, EDGE_TYPES, resolve_graph_path

NS = "http://mygraph.local/"
RB = "http://mygraph.local/schema#"
DCTERMS = "http://purl.org/dc/terms/"


def _require_rdflib():
    try:
        import rdflib  # type: ignore
        return rdflib
    except ImportError as e:
        raise SystemExit(
            "owl_io: `rdflib` is not installed. Run:\n"
            '    pip install -e ".[rdf]"'
        ) from e


def _iri(rdflib, suffix: str):
    # rdflib URIRef accepts strings; we keep IDs verbatim (slug already URL-safe except `:`)
    safe = suffix.replace(":", "/")
    return rdflib.URIRef(NS + safe)


def to_rdflib_graph(g: Graph):
    rdflib = _require_rdflib()
    from rdflib import Graph as RG, Literal, RDF, RDFS, OWL, Namespace
    rg = RG()
    rb_ns = Namespace(RB)
    dc_ns = Namespace(DCTERMS)
    rg.bind("rb", rb_ns)
    rg.bind("dcterms", dc_ns)
    rg.bind("mg", Namespace(NS))

    # ontology: classes/properties include public schema plus any legacy/private
    # types already present in the graph.
    rg.add((rb_ns.Concept, RDF.type, OWL.Class))
    rg.add((rb_ns.Source, RDF.type, OWL.Class))
    rg.add((rb_ns.Source, RDFS.subClassOf, dc_ns.ProvenanceEntity))
    node_types = NODE_TYPES | {n.type for n in g.nodes.values()}
    edge_types = EDGE_TYPES | {e.type for e in g.edges}
    for t in sorted(node_types):
        cls = rb_ns[t.capitalize()]
        rg.add((cls, RDF.type, OWL.Class))
        if t == "source":
            rg.add((cls, RDFS.subClassOf, rb_ns.Source))
        else:
            rg.add((cls, RDFS.subClassOf, rb_ns.Concept))
    for t in sorted(edge_types):
        rg.add((rb_ns[t], RDF.type, OWL.ObjectProperty))

    # nodes
    for nid, n in g.nodes.items():
        iri = _iri(rdflib, nid)
        rg.add((iri, RDF.type, rb_ns[n.type.capitalize()]))
        rg.add((iri, RDFS.label, Literal(n.label)))
        if n.body:
            rg.add((iri, RDFS.comment, Literal(n.body)))
        rg.add((iri, rb_ns.confidence, Literal(n.confidence)))
        rg.add((iri, rb_ns.createdAt, Literal(n.created_at)))
        rg.add((iri, rb_ns.nodeId, Literal(nid)))

    # edges (direct triple + reified rb:Assertion holding metadata)
    for i, e in enumerate(g.edges):
        s = _iri(rdflib, e.src)
        o = _iri(rdflib, e.dst)
        p = rb_ns[e.type]
        rg.add((s, p, o))
        # reify
        a_iri = rdflib.URIRef(f"{NS}_assertion/{i}")
        rg.add((a_iri, RDF.type, rb_ns.Assertion))
        rg.add((a_iri, RDF.subject, s))
        rg.add((a_iri, RDF.predicate, p))
        rg.add((a_iri, RDF.object, o))
        rg.add((a_iri, rb_ns.sourceId, Literal(e.source_id)))
        rg.add((a_iri, rb_ns.confidence, Literal(e.confidence)))
        rg.add((a_iri, rb_ns.createdAt, Literal(e.created_at)))
        rg.add((a_iri, rb_ns.lastSeen, Literal(e.last_seen)))
        rg.add((a_iri, rb_ns.edgeType, Literal(e.type)))
        rg.add((a_iri, rb_ns.srcId, Literal(e.src)))
        rg.add((a_iri, rb_ns.dstId, Literal(e.dst)))
        if e.excerpt:
            rg.add((a_iri, rb_ns.excerpt, Literal(e.excerpt)))

    return rg


def to_turtle(g: Graph) -> str:
    rg = to_rdflib_graph(g)
    return rg.serialize(format="turtle")


def to_jsonld(g: Graph) -> str:
    rg = to_rdflib_graph(g)
    return rg.serialize(format="json-ld", indent=2)


def from_turtle(path: Path) -> Graph:
    """Reimport a graph from Turtle. Reads from the rb:Assertion reifications
    (which carry the full edge metadata) — direct triples are redundant."""
    rdflib = _require_rdflib()
    from rdflib import Graph as RG, Literal, RDF, RDFS, Namespace
    rg = RG()
    rg.parse(str(path), format="turtle")
    rb_ns = Namespace(RB)

    nodes: dict[str, Node] = {}
    # iterate all subjects with rb:nodeId set
    for s, _, lit in rg.triples((None, rb_ns.nodeId, None)):
        nid = str(lit)
        # type from rdf:type (capitalize → lowercase mapping)
        t_iri = next(rg.objects(s, RDF.type), None)
        type_str = (str(t_iri).rsplit("#", 1)[-1] if t_iri else "idea").lower()
        label = str(next(rg.objects(s, RDFS.label), Literal("")))
        body = str(next(rg.objects(s, RDFS.comment), Literal("")))
        conf = str(next(rg.objects(s, rb_ns.confidence), Literal("medium")))
        created = str(next(rg.objects(s, rb_ns.createdAt),
                           Literal("1970-01-01T00:00:00+00:00")))
        nodes[nid] = Node(id=nid, type=type_str, label=label, body=body,
                          confidence=conf, created_at=created)

    edges: list[Edge] = []
    for a_iri, _, _ in rg.triples((None, RDF.type, rb_ns.Assertion)):
        src = str(next(rg.objects(a_iri, rb_ns.srcId), Literal("")))
        dst = str(next(rg.objects(a_iri, rb_ns.dstId), Literal("")))
        etype = str(next(rg.objects(a_iri, rb_ns.edgeType), Literal("")))
        if not etype:
            continue
        sid = str(next(rg.objects(a_iri, rb_ns.sourceId), Literal("")))
        conf = str(next(rg.objects(a_iri, rb_ns.confidence), Literal("medium")))
        created = str(next(rg.objects(a_iri, rb_ns.createdAt),
                           Literal("1970-01-01T00:00:00+00:00")))
        last = str(next(rg.objects(a_iri, rb_ns.lastSeen), Literal(created)))
        excerpt = str(next(rg.objects(a_iri, rb_ns.excerpt), Literal("")))
        edges.append(Edge(src=src, dst=dst, type=etype, source_id=sid,
                          excerpt=excerpt, confidence=conf,
                          created_at=created, last_seen=last))
    return Graph(nodes=nodes, edges=edges)


def round_trip_test(graph_path: Path | None = None) -> tuple[bool, str]:
    import tempfile
    active_path = graph_path or Path(resolve_graph_path())
    g = Graph.load(str(active_path))
    ttl = to_turtle(g)
    with tempfile.NamedTemporaryFile("w", suffix=".ttl", delete=False) as f:
        f.write(ttl)
        tmp = Path(f.name)
    try:
        g2 = from_turtle(tmp)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    n_match = len(g.nodes) == len(g2.nodes)
    e_match = len(g.edges) == len(g2.edges)
    if n_match and e_match:
        return True, f"OK: {len(g.nodes)} nodes / {len(g.edges)} edges round-tripped"
    return False, (f"MISMATCH: orig {len(g.nodes)}/{len(g.edges)} "
                   f"vs reimport {len(g2.nodes)}/{len(g2.edges)}")


def run_export(args: list[str]) -> int:
    if "--ttl" not in args and "--jsonld" not in args:
        print("Usage: mykg export (--ttl | --jsonld) [--graph <path>] [--out <path>] [--round-trip]")
        return 1
    if "--ttl" in args and "--jsonld" in args:
        print("Usage: choose one export format: --ttl or --jsonld")
        return 1
    graph_path = Path(resolve_graph_path())
    if "--graph" in args:
        i = args.index("--graph")
        graph_path = Path(args[i + 1]).expanduser().resolve()
    is_jsonld = "--jsonld" in args
    out = graph_path.with_suffix(".jsonld" if is_jsonld else ".ttl")
    if "--out" in args:
        i = args.index("--out")
        out = Path(args[i + 1]).expanduser().resolve()
    g = Graph.load(str(graph_path))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_jsonld(g) if is_jsonld else to_turtle(g), encoding="utf-8")
    print(f"export: wrote {out}")
    if "--round-trip" in args:
        if is_jsonld:
            print("round-trip: only --ttl supports round-trip import today")
            return 1
        ok, msg = round_trip_test(graph_path)
        print(f"round-trip: {msg}")
        return 0 if ok else 2
    return 0


if __name__ == "__main__":
    sys.exit(run_export(sys.argv[1:]))
