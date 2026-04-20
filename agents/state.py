"""
AgentState — the shared data envelope that flows through every LangGraph node.
All nodes read from this dict and return partial updates that get merged back.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage


class ChatMode(str, Enum):
    """Chat modes for Document Agent."""
    AUTO = "auto"           # Pipeline selects best approach
    DIRECT = "direct"       # Single-shot LLM call (skip workers)
    THINKING = "thinking"   # Step-by-step reasoning
    REACT = "react"         # Tool-use reasoning


class FileMeta(TypedDict, total=False):
    """Metadata for a single uploaded/parsed file."""
    file_id: str           # UUID-based unique identifier
    name: str              # original filename
    num_chars: int         # character count of parsed text
    topic_hint: str        # short description of the file topic
    saved_path: str        # path to the raw uploaded file
    snapshot_path: str     # path to the parsed Markdown snapshot


class AgentState(TypedDict, total=False):
    """
    Central state object passed through every node of the LangGraph pipeline.

    Nodes read from this dict and return partial dicts that LangGraph merges
    back into state automatically.
    """
    # ── Conversation ──────────────────────────────────────────────────────────
    messages: List[AnyMessage]          # full conversation history (HumanMessage / AIMessage)

    # ── File catalog ─────────────────────────────────────────────────────────
    available_files: List[FileMeta]     # parsed file metadata for this session

    # ── Session metadata ─────────────────────────────────────────────────────
    metadata: Dict[str, Any]           # user_id, run_id, session date, chat_mode, etc.

    # ── Chat mode ─────────────────────────────────────────────────────────────
    chat_mode: str                     # auto / direct / thinking / react

    # ── Query augmentor outputs ───────────────────────────────────────────────
    planner_question: Optional[str]             # augmented / normalised question
    augmentor_payload: Optional[Dict[str, Any]] # full AugmentedQuery JSON

    # ── Context planner outputs ───────────────────────────────────────────────
    context_plan: Optional[Dict[str, Any]]  # ContextPlan dict (workers + tasks)
    task_plan: Optional[List[Dict]]         # list of TaskPlan dicts (convenience)
    needs_rerun: bool                       # planner flagged insufficient context

    # ── Worker executor outputs ───────────────────────────────────────────────
    worker_results: Optional[List[Dict]]    # extraction results per worker

    # ── Task executor outputs ─────────────────────────────────────────────────
    task_results: Optional[List[Dict]]      # action / display task outputs
    export_artifacts: Optional[List[Dict]]  # paths of exported files

    # ── Direct mode output ────────────────────────────────────────────────────
    direct_response: Optional[str]          # single-shot LLM response (direct mode)
