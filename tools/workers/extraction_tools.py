"""
Worker tools — extract relevant text slices from parsed document snapshots.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from agents.LLM_CALLs.llm_handler import llm_handler

logger = logging.getLogger(__name__)

WORKER_SYSTEM_PROMPT = """You are a precise document extraction specialist for a Document Processing agent.

Your job is to read the provided document chunk and extract ONLY the information that is directly relevant to the query.

## Extraction Rules
1. Extract verbatim quotes or close paraphrases — never fabricate data.
2. Preserve numbers, dates, names, and percentages exactly as they appear.
3. Add a citation for every extracted piece: [CITATION: file_name=<name>, approx_position=<N>]
4. If no relevant information exists in this chunk, respond with exactly: === NO RELEVANT INFORMATION ===
5. Do not summarize or interpret — extract raw evidence only.
6. Format extracted items as a numbered list for clarity.

## Output Format
[Extracted item 1] [CITATION: file_name=X, approx_position=1000]
[Extracted item 2] [CITATION: file_name=X, approx_position=2500]
…
"""


def _extract_file_slice(file_path: str, start_char: int, end_char: int) -> str:
    """Read a character-window slice from a file."""
    if not file_path or not os.path.exists(file_path):
        return f"[FILE NOT FOUND: {file_path}]"
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return content[start_char:end_char]
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        return f"[FILE READ ERROR: {e}]"


def _extract_markdown_content(text: str) -> str:
    """Isolate the ## Content section of a markdown snapshot."""
    if "## Content" in text:
        parts = text.split("## Content", 1)
        content = parts[1]
        # Stop at next ## section
        if "\n## " in content:
            content = content.split("\n## ", 1)[0]
        return content.strip()
    return text.strip()


def worker_document_extractor(
    query: str,
    file_path: str,
    max_chars: int = 18000,
    start_char: int = 0,
    end_char: int = 18000,
) -> str:
    """
    Read a slice of a parsed markdown snapshot and extract relevant information.

    Args:
        query:      Combined worker instructions + question
        file_path:  Path to parsed markdown snapshot
        max_chars:  Character budget (soft cap)
        start_char: Start offset in the file
        end_char:   End offset in the file

    Returns:
        Extracted text with citations, or "=== NO RELEVANT INFORMATION ==="
    """
    raw_slice = _extract_file_slice(file_path, start_char, end_char)
    content = _extract_markdown_content(raw_slice)

    if not content.strip():
        return "=== NO RELEVANT INFORMATION ==="

    user_content = (
        f"## Worker Instructions\n{query}\n\n"
        f"## Document Content (chunk {start_char}–{end_char})\n{content}"
    )

    try:
        result = llm_handler.call(
            task_type="extraction",
            system_prompt=WORKER_SYSTEM_PROMPT,
            user_content=user_content,
            temperature=0.1,
            max_tokens=4096,
        )
        return result.strip() or "=== NO RELEVANT INFORMATION ==="
    except Exception as e:
        logger.error(f"worker_document_extractor LLM call failed: {e}")
        return f"=== EXTRACTION FAILED: {e} ==="
