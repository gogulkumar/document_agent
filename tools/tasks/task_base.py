"""
Base utility for all task tools.
invoke_task_llm() is the single call all task tools use.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from agents.LLM_CALLs.llm_handler import llm_handler

logger = logging.getLogger(__name__)

# Root directory where exported files are saved
EXPORT_ROOT = os.getenv("NOTEBOOK_AGENT_EXPORT_DIR", os.path.join(os.getcwd(), "exports"))
os.makedirs(EXPORT_ROOT, exist_ok=True)


def invoke_task_llm(
    task_description: str,
    dependency_payload: str,
    task_type: str = "synthesis",
    temperature: float = 0.1,
    max_tokens: int = 16000,
) -> str:
    """
    Call the synthesis LLM (Claude Sonnet 4 via Bedrock) with:
      - system_prompt = task_description (self-contained planner instruction)
      - user content  = all dependency text

    Returns the raw LLM response string.
    """
    return llm_handler.call(
        task_type=task_type,
        system_prompt=task_description,
        user_content=dependency_payload or "No upstream data provided.",
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _save_export(content: str, extension: str) -> str:
    """Save content to EXPORT_ROOT and return the file path."""
    filename = f"{uuid.uuid4().hex}.{extension}"
    path = os.path.join(EXPORT_ROOT, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Export saved: {path}")
    return path
