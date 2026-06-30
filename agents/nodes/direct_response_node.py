"""
Node: direct_response_node

Handles Direct and Thinking chat modes — single-shot LLM call
that bypasses the worker/task pipeline.

Direct mode: straightforward answer using file context + conversation
Thinking mode: step-by-step reasoning before final answer
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from langchain_core.messages import HumanMessage

from agents.state import AgentState
from agents.LLM_CALLs.llm_handler import llm_handler

logger = logging.getLogger(__name__)

DIRECT_SYSTEM_PROMPT = """You are an expert Document Processing research assistant.

The user has uploaded documents and is asking a question. Answer directly and comprehensively 
using the provided document context and conversation history.

## Rules
- Cite source files for any data points: [Source: filename]
- Be precise with numbers, dates, and names
- If you cannot find the answer in the documents, say so clearly
- Format output as clean HTML with professional styling
"""

THINKING_SYSTEM_PROMPT = """You are an expert Document Processing research assistant.

Think carefully before answering, but do not reveal private chain-of-thought.

## Format
Return clean HTML with:
- a short "How I approached this" section summarizing the evidence checked
- the final answer
- any caveats or missing evidence

## Rules
- Cite source files for any data points: [Source: filename]
- Be precise with numbers, dates, and names
- Summarize conclusions and evidence without exposing hidden reasoning
- If you cannot find the answer in the documents, say so clearly
"""


def _build_file_context(available_files: list, max_chars: int = 50000) -> str:
    """Read and concatenate file snapshots up to max_chars."""
    import os
    parts = []
    total = 0
    for f in available_files:
        path = f.get("snapshot_path") or f.get("saved_path", "")
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            # Extract ## Content section
            if "## Content" in content:
                section = content.split("## Content", 1)[1]
                if "\n## " in section:
                    section = section.split("\n## ", 1)[0]
                content = section.strip()

            remaining = max_chars - total
            if remaining <= 0:
                break
            snippet = content[:remaining]
            parts.append(f"### File: {f.get('name', 'unknown')}\n{snippet}")
            total += len(snippet)
        except Exception as e:
            logger.warning(f"Failed to read {path}: {e}")
    return "\n\n---\n\n".join(parts) if parts else "No document content available."


def _build_conversation_context(messages) -> str:
    lines = []
    for msg in messages[:-1]:  # exclude latest (it's the current question)
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = msg.content if hasattr(msg, "content") else str(msg)
        lines.append(f"[{role}]: {content[:2000]}")
    return "\n\n".join(lines) if lines else "No prior conversation."


def build_direct_response_request(state: AgentState) -> Tuple[str, str]:
    """Build the prompt payload used by the direct-response path."""
    messages = state.get("messages", [])
    available_files = state.get("available_files", [])
    chat_mode = state.get("chat_mode", "direct")

    if not messages:
        return DIRECT_SYSTEM_PROMPT, "No user message provided."

    user_question = messages[-1].content if messages else ""
    planner_question = state.get("planner_question") or user_question
    conversation = _build_conversation_context(messages)
    file_context = _build_file_context(available_files)

    system_prompt = THINKING_SYSTEM_PROMPT if chat_mode == "thinking" else DIRECT_SYSTEM_PROMPT

    user_content = (
        f"## Conversation History\n{conversation}\n\n"
        f"## Augmented Brief\n{planner_question}\n\n"
        f"## Document Context\n{file_context}\n\n"
        f"## Current Question\n{user_question}\n\n"
        f"Provide your response now."
    )
    return system_prompt, user_content


def direct_response_node(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph node: single-shot LLM response (direct or thinking mode).
    Bypasses workers/tasks entirely.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"direct_response": "", "task_results": [], "export_artifacts": []}

    system_prompt, user_content = build_direct_response_request(state)

    try:
        response = llm_handler.call(
            task_type="synthesis",
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=0.2,
            max_tokens=16000,
        )
    except Exception as e:
        logger.error(f"direct_response_node failed: {e}")
        response = f"<p>Error generating response: {e}</p>"

    # Package as a task_result so the Flask app can render it uniformly
    task_results = [{
        "task_id": "direct_response",
        "type": "display",
        "tool_name": "direct_response",
        "display_format": "html",
        "output": response,
    }]

    return {
        "direct_response": response,
        "task_results": task_results,
        "export_artifacts": [],
    }
