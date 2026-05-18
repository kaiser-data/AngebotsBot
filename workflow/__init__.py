"""Workflow package exports.

Expose ``build_graph`` lazily to avoid importing graph assembly at package
import time, which creates a circular dependency in unit tests.
"""

from .state import AgentState

__all__ = ["AgentState", "build_graph"]


def __getattr__(name: str):
    if name == "build_graph":
        from .graph import build_graph
        return build_graph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
