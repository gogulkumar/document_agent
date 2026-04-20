"""
inmemory_recorder.py — per-turn conversation log writer.
Builds the snapshot text that gets compressed into the rolling summary.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from runtime_paths import CHAT_DIR

logger = logging.getLogger(__name__)
RECORDER_DIR = CHAT_DIR


def _strip_html(text: str) -> str:
    """Strip HTML tags for compact storage."""
    return re.sub(r"<[^>]+>", "", text).strip()


def build_turn_snapshot(
    message_id: str,
    run_id: str,
    user_question: str,
    augmented_question: str,
    context_plan: Optional[Dict] = None,
    worker_results: Optional[List[Dict]] = None,
    task_results: Optional[List[Dict]] = None,
) -> str:
    """
    Build a Markdown snapshot for a single conversation turn.
    This snapshot is passed to the conversation summarizer.
    """
    plan_summary = ""
    if context_plan:
        plan_summary = (
            f"Intent: {context_plan.get('intent', '')}, "
            f"Workers: {len(context_plan.get('workers', []))}, "
            f"Tasks: {len(context_plan.get('tasks', []))}"
        )

    # Compact worker results (keep IDs and output length only)
    workers_summary = ""
    if worker_results:
        worker_lines = [
            f"  - {wr.get('worker_id')}: {len(wr.get('output', ''))} chars"
            for wr in worker_results
        ]
        workers_summary = "\n".join(worker_lines)

    # Final rendered output (last display task, HTML stripped)
    rendered = ""
    if task_results:
        for tr in reversed(task_results):
            if tr.get("type") == "display" or tr.get("display_format"):
                rendered = _strip_html(tr.get("output", ""))[:500]
                break

    snapshot = (
        f"## Message {message_id}\n"
        f"- created_at: {datetime.utcnow().isoformat()}\n"
        f"- run_id: {run_id}\n"
        f"- Summary:\n"
        f"  - user_question: {user_question[:300]}\n"
        f"  - augmented_question: {augmented_question[:500]}\n"
        f"  - plan: {plan_summary}\n"
        f"  - worker_results:\n{workers_summary}\n"
        f"  - rendered_output: {rendered}\n"
    )
    return snapshot


def save_turn_log(run_id: str, message_id: str, snapshot: str) -> None:
    """Save the per-turn snapshot to disk."""
    session_dir = os.path.join(RECORDER_DIR, run_id)
    os.makedirs(session_dir, exist_ok=True)
    path = os.path.join(session_dir, f"turn_{message_id}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(snapshot)
