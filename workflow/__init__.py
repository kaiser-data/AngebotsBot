"""Workflow package exports.

Avoid importing graph assembly at package import time; that creates a circular
dependency when individual agent modules import workflow.state in tests.
"""

from .state import AgentState

__all__ = ["AgentState"]
