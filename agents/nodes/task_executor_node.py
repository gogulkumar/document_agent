"""
Node 4: task_executor_node

Runs all tasks from the ContextPlan in topological order.
Routes each task to the correct tool based on type and display_format.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from agents.state import AgentState

logger = logging.getLogger(__name__)

# ── Tool imports ──────────────────────────────────────────────────────────────
from tools.tasks.unified_executor import task_unified_executor
from tools.tasks.plain_text_display import task_plain_text_display
from tools.tasks.markdown_display import task_markdown_display
from tools.tasks.html_export import task_html_export
from tools.tasks.dashboard_display import task_dashboard_display
from tools.tasks.ppt_export import task_ppt_export
from tools.tasks.pdf_export import task_pdf_export
from tools.tasks.word_export import task_word_export

TOOL_MAP = {
    "task_unified_executor":    task_unified_executor,
    "task_plain_text_display":  task_plain_text_display,
    "task_markdown_display":    task_markdown_display,
    "task_html_export":         task_html_export,
    "task_dashboard_display":   task_dashboard_display,
    "task_ppt_export":          task_ppt_export,
    "task_pdf_export":          task_pdf_export,
    "task_word_export":         task_word_export,
}

DISPLAY_FORMAT_TOOL_MAP = {
    "plain_text":   "task_plain_text_display",
    "markdown":     "task_markdown_display",
    "html":         "task_html_export",
    "html_table":   "task_html_export",
    "dashboard":    "task_dashboard_display",
    "export_ppt":   "task_ppt_export",
    "export_pdf":   "task_pdf_export",
    "export_word":  "task_word_export",
}

EXPORT_TOOL_SUFFIXES = {"_export"}
HTML_RENDER_TOOLS = {"task_html_export", "task_dashboard_display"}


def _topological_sort(tasks: List[Dict]) -> List[Dict]:
    """
    Sort tasks by depends_on DAG.
    Raises ValueError if a circular dependency is detected.
    """
    task_map = {t["id"]: t for t in tasks}
    visited = set()
    result = []

    def visit(task_id: str, ancestors: set):
        if task_id in ancestors:
            raise ValueError(f"Circular dependency detected at task '{task_id}'")
        if task_id in visited:
            return
        ancestors.add(task_id)
        for dep in task_map.get(task_id, {}).get("depends_on", []):
            if dep in task_map:  # skip worker_ids (they're already done)
                visit(dep, ancestors.copy())
        visited.add(task_id)
        result.append(task_map[task_id])

    for task in tasks:
        visit(task["id"], set())

    return result


def _resolve_tool(task: Dict):
    """Return the callable tool for a given task."""
    tool_name = task.get("tool_name")
    task_type = task.get("type", "action")
    display_format = task.get("display_format", "")

    if tool_name and tool_name in TOOL_MAP:
        return TOOL_MAP[tool_name], tool_name

    if task_type == "action":
        return task_unified_executor, "task_unified_executor"

    # display task: route by display_format
    mapped = DISPLAY_FORMAT_TOOL_MAP.get(display_format, "task_html_export")
    return TOOL_MAP[mapped], mapped


def _build_dependency_payload(
    task: Dict,
    worker_results: List[Dict],
    completed_tasks: Dict[str, str],
) -> str:
    """Concatenate outputs from all listed worker_ids and task_ids."""
    depends_on = task.get("depends_on", [])
    parts = []

    for dep_id in depends_on:
        if dep_id.startswith("worker_"):
            # Find matching worker result
            for wr in worker_results:
                if wr.get("worker_id") == dep_id:
                    parts.append(f"[Worker {dep_id}]\n{wr.get('output', '')}")
                    break
        elif dep_id in completed_tasks:
            parts.append(f"[Task {dep_id}]\n{completed_tasks[dep_id]}")

    return "\n\n---\n\n".join(parts)


def _strip_dependency_headers(text: str) -> str:
    """Remove [Worker X] / [Task X] headers from dependency payload."""
    return re.sub(r"\[(?:Worker|Task) \S+\]\n", "", text)


def _load_renderable_output(tool_name: str, raw_output: str) -> str:
    """
    HTML export tools save a file path; load the saved document so the UI can
    render the actual report instead of showing the path string.
    """
    if tool_name not in HTML_RENDER_TOOLS:
        return raw_output

    if not raw_output or not os.path.exists(raw_output):
        return raw_output

    try:
        with open(raw_output, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except Exception as exc:
        logger.warning(f"Failed to load renderable HTML from {raw_output}: {exc}")
        return raw_output


def task_executor_node(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph node: runs all tasks in topological order.

    Reads:  state.context_plan, state.worker_results
    Writes: state.task_results, state.export_artifacts
    """
    context_plan = state.get("context_plan", {})
    worker_results = state.get("worker_results", [])

    tasks: List[Dict] = context_plan.get("tasks", [])

    if not tasks:
        logger.warning("task_executor_node: No tasks in context_plan.")
        return {"task_results": [], "export_artifacts": []}

    # Topological sort
    try:
        ordered_tasks = _topological_sort(tasks)
    except ValueError as e:
        logger.error(f"task_executor_node: {e}")
        return {"task_results": [], "export_artifacts": []}

    completed_tasks: Dict[str, str] = {}
    task_results: List[Dict] = []
    export_artifacts: List[Dict] = []

    for task in ordered_tasks:
        task_id = task.get("id", "unknown")
        task_description = task.get("description", "")
        display_format = task.get("display_format", "")

        # Build dependency payload
        dep_payload = _build_dependency_payload(task, worker_results, completed_tasks)
        clean_payload = _strip_dependency_headers(dep_payload)

        # Resolve tool
        tool_fn, tool_name = _resolve_tool(task)

        logger.info(f"task_executor_node: Running {task_id} with tool={tool_name}")

        try:
            raw_output = tool_fn(
                task_description=task_description,
                dependency_payload=clean_payload,
                display_format=display_format,
            )
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            raw_output = f"<!-- Task {task_id} failed: {e} -->"

        output = _load_renderable_output(tool_name, raw_output)

        completed_tasks[task_id] = output

        result_record = {
            "task_id": task_id,
            "type": task.get("type"),
            "tool_name": tool_name,
            "display_format": display_format,
            "output": output,
        }
        task_results.append(result_record)

        # Track export artifacts
        if any(tool_name.endswith(suffix) for suffix in EXPORT_TOOL_SUFFIXES):
            export_artifacts.append({
                "task_id": task_id,
                "tool_name": tool_name,
                "path": raw_output,  # export tools return file paths
                "display_format": display_format,
            })

    return {
        "task_results": task_results,
        "export_artifacts": export_artifacts,
    }
