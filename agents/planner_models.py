"""
Pydantic v2 models for the Context Planner node output.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    NEW_ANALYSIS = "new_analysis"
    REFINEMENT = "refinement"
    DEEP_DIVE = "deep_dive"
    FORMAT_CHANGE = "format_change"
    STRUCTURE_CHANGE = "structure_change"
    DISPLAY_CHANGE = "display_change"
    COMPARISON = "comparison"
    SUMMARY = "summary"


class WorkerPlan(BaseModel):
    """
    Defines a single extraction worker.
    Each worker is assigned one file chunk and returns extracted snippets.
    """
    worker_id: str                        # "worker_1", "worker_2", …
    target_files: List[str]               # list of file_ids (usually one)
    max_chars: int = 18000                # character budget for this worker
    task_type: str = "extraction"
    description: str                      # SELF-CONTAINED system prompt
    tool_name: str = "worker_document_extractor"
    char_start: int = 0
    char_end: int = 18000


class TaskPlan(BaseModel):
    """
    Defines a single action or display task that runs after all workers complete.
    """
    id: str                              # "task_1", "task_2", …
    type: str                            # "action" | "display"
    description: str                     # SELF-CONTAINED system prompt
    depends_on: List[str] = Field(default_factory=list)  # ALL upstream worker_ids or task_ids
    display_format: Optional[str] = None  # html / plain_text / markdown / export_ppt / …
    tool_name: Optional[str] = None


class ContextPlan(BaseModel):
    """
    Full plan produced by the context_planner_node.
    Contains all workers (extraction) and tasks (action / display).
    """
    intent: IntentType = IntentType.NEW_ANALYSIS
    user_question: str = ""
    analysis_goal: str = ""
    selected_files: List[str] = Field(default_factory=list)
    workers: List[WorkerPlan] = Field(default_factory=list)
    tasks: List[TaskPlan] = Field(default_factory=list)
    max_chars_per_worker: int = 18000
    total_chars_planned: int = 0
    needs_rerun_with_more_context: bool = False
    notes_for_executor: str = ""
