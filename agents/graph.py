"""
LangGraph StateGraph definition for the Document AI Notebook Agent.

Supports 4 chat modes:
  - auto:     Full pipeline (augmentor → planner → workers → tasks)
  - direct:   Single-shot LLM call (augmentor → direct_response)
  - thinking: Step-by-step reasoning (augmentor → direct_response with CoT)
  - react:    Full pipeline with reasoning (same as auto for now)

Conditional routing:
  - After augmentor: route based on chat_mode
  - After planner: skip workers if no files or if needs_rerun flagged
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal

from langgraph.graph import StateGraph, START, END

from agents.state import AgentState
from agents.nodes.query_augmentor_node import query_augmentor_node
from agents.nodes.context_planner_node import context_planner_node
from agents.nodes.worker_tool_executor_node import worker_tool_executor_node
from agents.nodes.task_executor_node import task_executor_node
from agents.nodes.direct_response_node import direct_response_node

logger = logging.getLogger(__name__)


def _should_auto_use_direct_response(state: AgentState) -> bool:
    """
    Keep auto mode lightweight when the request does not require document
    planning/extraction.
    """
    available_files = state.get("available_files", [])
    augmentor_payload = state.get("augmentor_payload", {}) or {}
    export_requested = (augmentor_payload.get("export") or "none").lower()

    # No uploaded files means there is nothing to plan/extract from, so use the
    # direct response path even if web search is enabled.
    if not available_files and export_requested == "none":
        return True

    return False


def _route_after_augmentor(state: AgentState) -> Literal["context_planner", "direct_response"]:
    """
    Route based on chat_mode:
      - direct / thinking → direct_response (single-shot)
      - auto / react      → context_planner (full pipeline)
    """
    mode = state.get("chat_mode", "auto")
    if mode in ("direct", "thinking"):
        logger.info(f"Routing to direct_response (chat_mode={mode})")
        return "direct_response"
    if mode == "auto" and _should_auto_use_direct_response(state):
        logger.info("Routing to direct_response (chat_mode=auto, lightweight path)")
        return "direct_response"
    return "context_planner"


def _route_after_planner(state: AgentState) -> Literal["worker_executor", "task_executor"]:
    """
    Skip workers if:
      - No workers in plan (e.g. no files uploaded)
      - Plan flagged needs_rerun_with_more_context (handled by re-planning later)
    """
    context_plan = state.get("context_plan", {})
    workers = context_plan.get("workers", [])

    if not workers:
        logger.info("No workers in plan — skipping to task_executor")
        return "task_executor"

    return "worker_executor"


def build_graph() -> Any:
    """
    Build and compile the LangGraph StateGraph with conditional routing.

    Returns:
        Compiled LangGraph graph ready for .invoke() or .stream()
    """
    graph = StateGraph(AgentState)

    # ── Add nodes ─────────────────────────────────────────────────────────────
    graph.add_node("query_augmentor", query_augmentor_node)
    graph.add_node("context_planner", context_planner_node)
    graph.add_node("worker_executor", worker_tool_executor_node)
    graph.add_node("task_executor", task_executor_node)
    graph.add_node("direct_response", direct_response_node)

    # ── Edges ─────────────────────────────────────────────────────────────────
    graph.add_edge(START, "query_augmentor")

    # After augmentor: route by chat_mode
    graph.add_conditional_edges(
        "query_augmentor",
        _route_after_augmentor,
        {
            "context_planner": "context_planner",
            "direct_response": "direct_response",
        },
    )

    # After planner: skip workers if none planned
    graph.add_conditional_edges(
        "context_planner",
        _route_after_planner,
        {
            "worker_executor": "worker_executor",
            "task_executor": "task_executor",
        },
    )

    # Linear: workers → tasks → END
    graph.add_edge("worker_executor", "task_executor")
    graph.add_edge("task_executor", END)

    # Direct response → END
    graph.add_edge("direct_response", END)

    compiled = graph.compile()
    logger.info("LangGraph compiled with conditional routing.")
    return compiled


# ── Legacy alias ──────────────────────────────────────────────────────────────
build_basic_langgraph = build_graph

# Singleton instance — imported by Flask app
_compiled_graph = None


def get_graph() -> Any:
    """Return a cached compiled graph (lazy singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


route_after_augmentor = _route_after_augmentor
route_after_planner = _route_after_planner
