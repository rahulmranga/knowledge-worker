"""Public package surface for the knowledge-worker graph toolkit."""

__all__ = [
    "CONFIDENCE",
    "DEFAULT_GRAPH_PATH",
    "EDGE_TYPES",
    "GRAPH_PATH",
    "NODE_TYPES",
    "Edge",
    "Graph",
    "Node",
    "nid",
    "resolve_graph_path",
    "slug",
]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import mygraph as _core

    return getattr(_core, name)
