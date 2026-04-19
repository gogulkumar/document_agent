"""
LangGraph StateGraph definition for the Document AI Notebook Agent.

Flow:
    query_augmentor_node
        -> context_planner_node
            -> worker_tool_executor_node
                -> task_executor_node
                    -> END
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from langgraph.graph import StateGraph, START, END

from agents.state import AgentState
from agents.nodes.query_augmentor_node import query_augmentor_node
from agents.nodes.context_planner_node import context_planner_node
from agents.nodes.worker_tool_executor_node import worker_tool_executor_node
from agents.nodes.task_executor_node import task_executor_node

logger = logging.getLogger(__name__)


def build_basic_langgraph() -> Any:
    """
    Build and compile the LangGraph StateGraph.

    Returns:
        Compiled LangGraph graph ready for .invoke() or .stream()
    """
    graph = StateGraph(AgentState)

    # ── Add nodes ─────────────────────────────────────────────────────────────
    graph.add_node("query_augmentor", query_augmentor_node)
    graph.add_node("context_planner", context_planner_node)
    graph.add_node("worker_executor", worker_tool_executor_node)
    graph.add_node("task_executor", task_executor_node)

    # ── Add edges (linear pipeline) ────────────────────────────────────────────
    graph.add_edge(START, "query_augmentor")
    graph.add_edge("query_augmentor", "context_planner")
    graph.add_edge("context_planner", "worker_executor")
    graph.add_edge("worker_executor", "task_executor")
    graph.add_edge("task_executor", END)

    compiled = graph.compile()
    logger.info("LangGraph compiled successfully.")
    return compiled


# Singleton instance — imported by Flask app
_compiled_graph = None


def get_graph() -> Any:
    """Return a cached compiled graph (lazy singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_basic_langgraph()
    return _compiled_graph
