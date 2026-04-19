"""
Node 2: context_planner_node

Creates a full ContextPlan: assigns workers (file chunks) and tasks (synthesis/export).
Runs _enforce_worker_distribution() to split large files into 18k-char chunks.

LLM: GPT-4.1 (planning, temperature=0.1, max_tokens=32000)
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List

from agents.state import AgentState
from agents.planner_models import ContextPlan, WorkerPlan
from agents.LLM_CALLs.llm_handler import llm_handler
from agents.prompts.planner_prompt import CONTEXT_PLANNER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_CHARS_PER_WORKER = 18_000


def _build_file_catalog_with_counts(available_files: list) -> str:
    lines = []
    total = 0
    for f in available_files:
        chars = f.get("num_chars", 0)
        total += chars
        workers_needed = math.ceil(chars / MAX_CHARS_PER_WORKER)
        lines.append(
            f"  file_id={f.get('file_id')} | name={f.get('name')} "
            f"| chars={chars:,} | workers_needed={workers_needed} "
            f"| topic={f.get('topic_hint', '')}"
        )
    lines.append(f"\nTotal characters across all files: {total:,}")
    return "\n".join(lines)


def _enforce_worker_distribution(plan: ContextPlan, available_files: list) -> ContextPlan:
    """
    Split workers for large files into char-windowed chunks.
    Ensures no single worker exceeds MAX_CHARS_PER_WORKER characters.
    Renumbers all workers sequentially after chunking.
    """
    file_map = {f["file_id"]: f for f in available_files}
    file_map_by_name = {f["name"]: f for f in available_files}
    new_workers: List[WorkerPlan] = []

    # Deduplicate by file_id (take first worker per file as template)
    seen_files: Dict[str, WorkerPlan] = {}
    
    # If LLM didn't return any workers but we have available files, 
    # we should create default workers for them.
    if not plan.workers and available_files:
        for f in available_files:
            seen_files[f["file_id"]] = WorkerPlan(
                worker_id="temp",
                target_files=[f["file_id"]],
                task_type="extraction",
                description=f"Extract relevant information related to the user prompt from {f.get('name')}.",
                tool_name="worker_document_extractor"
            )
    else:
        for worker in plan.workers:
            for fid in worker.target_files:
                if fid not in seen_files:
                    seen_files[fid] = worker

    for file_id, template_worker in seen_files.items():
        file_meta = file_map.get(file_id) or file_map_by_name.get(file_id)
        if not file_meta:
            logger.warning(f"File {file_id} not found in available_files — skipping.")
            continue

        total_chars = file_meta.get("num_chars", MAX_CHARS_PER_WORKER)
        chunk_count = math.ceil(total_chars / MAX_CHARS_PER_WORKER)

        for i in range(chunk_count):
            start = i * MAX_CHARS_PER_WORKER
            end = min(start + MAX_CHARS_PER_WORKER, total_chars)
            chunk_desc = (
                f"{template_worker.description}\n\n"
                f"[CHUNK INFO: Processing chunk {i+1} of {chunk_count} for file '{file_meta.get('name')}'. "
                f"Read characters {start:,} to {end:,}.]"
            )
            new_workers.append(
                WorkerPlan(
                    worker_id=f"worker_{len(new_workers)+1}",
                    target_files=[file_meta["file_id"]],
                    max_chars=MAX_CHARS_PER_WORKER,
                    task_type="extraction",
                    description=chunk_desc,
                    tool_name="worker_document_extractor",
                    char_start=start,
                    char_end=end,
                )
            )

    # Renumber sequentially
    for i, w in enumerate(new_workers):
        w.worker_id = f"worker_{i+1}"

    plan.workers = new_workers
    plan.total_chars_planned = sum(
        (w.char_end - w.char_start) for w in new_workers
    )
    return plan


def context_planner_node(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph node: produces a ContextPlan with workers and tasks.

    Reads:  state.planner_question, state.augmentor_payload, state.available_files
    Writes: state.context_plan, state.task_plan
    """
    planner_question = state.get("planner_question", "")
    augmentor_payload = state.get("augmentor_payload", {})
    available_files = state.get("available_files", [])

    file_catalog = _build_file_catalog_with_counts(available_files)

    user_content = (
        f"## Augmented Question Brief\n{planner_question}\n\n"
        f"## File Catalog\n{file_catalog}\n\n"
        f"## Augmentor Details\n{augmentor_payload}\n\n"
        f"Produce the ContextPlan JSON now."
    )

    try:
        plan: ContextPlan = llm_handler.call_structured(
            task_type="planning",
            system_prompt=CONTEXT_PLANNER_SYSTEM_PROMPT,
            user_content=user_content,
            output_schema=ContextPlan,
            temperature=0.1,
            max_tokens=32000,
        )

        # Enforce worker chunking
        plan = _enforce_worker_distribution(plan, available_files)

        logger.info(
            f"context_planner_node: {len(plan.workers)} workers, "
            f"{len(plan.tasks)} tasks, intent={plan.intent}"
        )

        return {
            "context_plan": plan.model_dump(),
            "task_plan": [t.model_dump() for t in plan.tasks],
        }

    except Exception as e:
        logger.error(f"context_planner_node failed: {e}")
        return {"context_plan": {}, "task_plan": []}
