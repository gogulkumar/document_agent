"""
conversation_summarizer.py — rolling LLM-compressed Markdown conversation memory.

Keeps a per-run_id summary file that stores compressed conversation history,
preventing context overflow on long multi-turn sessions.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from agents.LLM_CALLs.llm_handler import llm_handler

logger = logging.getLogger(__name__)

SUMMARY_DIR = os.path.join(os.getcwd(), "inmemory_conversation")
MAX_SUMMARY_CHARS = 20_000

SUMMARIZER_SYSTEM_PROMPT = """You are a conversation memory compressor for an IR research agent.

Compress the given conversation history into a structured Markdown summary that:
1. Preserves ALL persistent user rules, formatting preferences, and guardrails
2. Captures the key question, plan, evidence, and output for each turn
3. Strips raw document extractions (keep only final answers)
4. Highlights recurring themes or metrics the user cares about

Output format:
# Conversation Summary

## Persistent Rules & Formatting Instructions
(any rules/preferences the user stated across turns)

## Conversation Evolution Timeline

## Message {id}
- created_at: ...
- Summary:
  - user_question: ...
  - augmented_question: ...
  - plan: ...
  - key_findings: ...
  - rendered_output: (1-2 sentence summary)
"""


def _summary_path(run_id: str) -> str:
    os.makedirs(os.path.join(SUMMARY_DIR, run_id), exist_ok=True)
    return os.path.join(SUMMARY_DIR, run_id, "conversation_summary.md")


def should_summarize(run_id: str, new_snapshot: str) -> bool:
    """Return True if existing summary + new snapshot exceeds the char limit."""
    path = _summary_path(run_id)
    existing = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
    return len(existing) + len(new_snapshot) > MAX_SUMMARY_CHARS


def _compress(text: str, aggression: str = "normal") -> str:
    """Compress an existing summary using the LLM."""
    instructions = {
        "normal":      "Compress moderately. Keep all key data points.",
        "aggressive":  "Compress aggressively. Keep only essential facts and rules.",
        "ultra":       "Ultra-compress. Keep only persistent rules and 1-line summaries per turn.",
    }.get(aggression, "Compress moderately.")

    return llm_handler.call(
        task_type="conversation_summarizer",
        system_prompt=SUMMARIZER_SYSTEM_PROMPT + f"\n\nCompression level: {instructions}",
        user_content=text,
        temperature=0.1,
        max_tokens=8192,
    )


def compress_summary(run_id: str) -> None:
    """If existing summary is too large, compress it (up to 3 attempts)."""
    path = _summary_path(run_id)
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if len(content) <= MAX_SUMMARY_CHARS:
        return

    for aggression in ["normal", "aggressive", "ultra"]:
        compressed = _compress(content, aggression)
        if len(compressed) <= MAX_SUMMARY_CHARS:
            write_summary(run_id, compressed)
            return

    # Last resort: truncate to last MAX_SUMMARY_CHARS chars
    write_summary(run_id, content[-MAX_SUMMARY_CHARS:])


def summarize(run_id: str, new_snapshot: str) -> str:
    """Merge new_snapshot into existing summary. Returns the new summary text."""
    path = _summary_path(run_id)
    existing = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()

    combined = f"{existing}\n\n---\n\n{new_snapshot}"

    for attempt, aggression in enumerate(["normal", "aggressive", "ultra"], 1):
        try:
            result = _compress(combined, aggression)
            if len(result) <= MAX_SUMMARY_CHARS:
                return result
        except Exception as e:
            logger.warning(f"summarize attempt {attempt} failed: {e}")

    # Fallback: return truncated combined
    return combined[-MAX_SUMMARY_CHARS:]


def write_summary(run_id: str, content: str) -> None:
    """Write summary to disk."""
    path = _summary_path(run_id)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def read_summary(run_id: str) -> str:
    """Read and return the current summary for a run_id."""
    path = _summary_path(run_id)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def update_summary_file(run_id: str, new_snapshot: str) -> None:
    """
    High-level: compress existing if needed, then merge new snapshot.
    Called after each conversation turn.
    """
    compress_summary(run_id)
    new_summary = summarize(run_id, new_snapshot)
    write_summary(run_id, new_summary)
