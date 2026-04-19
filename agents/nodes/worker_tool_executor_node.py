"""
Node 3: worker_tool_executor_node

Runs all workers from the ContextPlan in parallel using ThreadPoolExecutor.
Each worker reads a file chunk and extracts relevant information.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from agents.state import AgentState
from tools.workers.extraction_tools import worker_document_extractor

logger = logging.getLogger(__name__)

MAX_PARALLEL_WORKERS = 8


def _run_single_worker(worker: Dict, file_map: Dict[str, Dict]) -> Dict:
    """Execute a single worker and return its result record."""
    worker_id = worker.get("worker_id", "unknown")
    target_files = worker.get("target_files", [])

    if not target_files:
        return {
            "worker_id": worker_id,
            "tool_name": worker.get("tool_name"),
            "file_id": None,
            "output": "=== NO FILE ASSIGNED ===",
            "input_used": "",
            "error": "No target files specified",
        }

    file_id = target_files[0]
    file_meta = file_map.get(file_id, {})

    # Resolve file path: prefer snapshot (parsed markdown), fall back to raw upload
    file_path = file_meta.get("snapshot_path") or file_meta.get("saved_path", "")

    query = (
        f"Worker ID: {worker_id}\n"
        f"File: {file_meta.get('name', file_id)}\n"
        f"Chunk: chars {worker.get('char_start', 0)} – {worker.get('char_end', 18000)}\n\n"
        f"Instructions:\n{worker.get('description', '')}"
    )

    try:
        output = worker_document_extractor(
            query=query,
            file_path=file_path,
            max_chars=worker.get("max_chars", 18000),
            start_char=worker.get("char_start", 0),
            end_char=worker.get("char_end", 18000),
        )
        logger.info(f"Worker {worker_id} completed. Output length: {len(output)}")
    except Exception as e:
        logger.error(f"Worker {worker_id} failed: {e}")
        output = f"=== WORKER FAILED: {e} ==="

    return {
        "worker_id": worker_id,
        "tool_name": worker.get("tool_name"),
        "file_id": file_id,
        "saved_path": file_meta.get("saved_path"),
        "snapshot_path": file_meta.get("snapshot_path"),
        "output": output,
        "input_used": query[:500],  # store truncated input for debugging
    }


def worker_tool_executor_node(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph node: runs all extraction workers in parallel.

    Reads:  state.context_plan, state.available_files
    Writes: state.worker_results
    """
    context_plan = state.get("context_plan", {})
    available_files = state.get("available_files", [])

    workers: List[Dict] = context_plan.get("workers", [])
    file_map: Dict[str, Dict] = {f["file_id"]: f for f in available_files}

    if not workers:
        logger.warning("worker_tool_executor_node: No workers in context_plan.")
        return {"worker_results": []}

    logger.info(f"worker_tool_executor_node: Running {len(workers)} workers in parallel.")

    results: List[Dict] = []
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_WORKERS, len(workers))) as executor:
        future_map = {
            executor.submit(_run_single_worker, w, file_map): w
            for w in workers
        }
        for future in as_completed(future_map):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                worker = future_map[future]
                logger.error(f"Worker {worker.get('worker_id')} raised exception: {e}")
                results.append({
                    "worker_id": worker.get("worker_id"),
                    "output": f"=== WORKER EXCEPTION: {e} ===",
                    "error": str(e),
                })

    # Sort by worker_id for consistent ordering
    results.sort(key=lambda r: r.get("worker_id", ""))

    return {"worker_results": results}
