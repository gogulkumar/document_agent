"""
Pydantic v2 models for the Query Augmentor node output.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QueryClarity(str, Enum):
    FOCUSED = "FOCUSED"
    VAGUE = "VAGUE"


class QueryIntent(str, Enum):
    NEW_REQUEST = "new_request"
    REFINEMENT = "refinement"
    FORMAT_CHANGE = "format_change"
    DEEP_DIVE = "deep_dive"
    COMPARISON = "comparison"
    SUMMARY = "summary"
    OTHER = "other"


class RefinementContext(BaseModel):
    """Context for iterative query refinements."""
    is_refinement: bool = False
    required_changes: List[str] = Field(default_factory=list)
    execution_plan: str = ""


class FileExtractionDirective(BaseModel):
    """Per-file extraction instruction for the planner."""
    file_id: str
    file_name: str
    focus_areas: List[str] = Field(default_factory=list)
    priority: str = "normal"  # high / normal / low


class OutputExpectations(BaseModel):
    """Describes what the final output should look like."""
    format: str = "html"          # html / plain_text / markdown / ppt / pdf / word
    instructions: str = ""
    requested_sections: List[str] = Field(default_factory=list)


class AugmentedQuery(BaseModel):
    """
    Structured output from the query_augmentor_node.
    The augmentor parses the user message and enriches it with
    IR-domain context before passing it to the planner.
    """
    query_clarity: QueryClarity = QueryClarity.FOCUSED
    query_clarity_explanation: str = ""

    query_intent: QueryIntent = QueryIntent.NEW_REQUEST
    refinement_context: RefinementContext = Field(default_factory=RefinementContext)

    # High-level processing objective
    aim: str = ""

    # What the agent must do (bullet list)
    actions: List[str] = Field(default_factory=list)

    # Step-by-step execution plan (Step 1…N)
    approach: str = ""

    # Per-file extraction directives
    file_extraction_plan: List[FileExtractionDirective] = Field(default_factory=list)

    # Metrics / KPIs to search for
    information_targets: List[str] = Field(default_factory=list)

    # Testable analytical hypotheses
    hypotheses: List[str] = Field(default_factory=list)

    # What to exclude
    exclusions_and_guardrails: Dict[str, Any] = Field(default_factory=dict)

    # Output format
    output_expectations: OutputExpectations = Field(default_factory=OutputExpectations)

    # Verbatim user-provided HTML template (if any)
    user_output_format: str = ""

    # Verbatim user directives
    user_instructions: str = ""

    # User education / frameworks
    user_education: str = ""

    # Web search queries (if proactive internet search is determined necessary)
    search_queries: List[str] = Field(default_factory=list)

    # Verbatim output templates
    template_examples: str = ""

    # Export request: ppt / pdf / html / word / none
    export: str = "none"

    def to_brief(self) -> str:
        """Render as a plain-text augmented brief for the planner."""
        lines = [
            f"AUGMENTED QUESTION BRIEF",
            f"========================",
            f"Aim: {self.aim}",
            f"Intent: {self.query_intent.value}",
            f"Clarity: {self.query_clarity.value} — {self.query_clarity_explanation}",
            f"",
            f"Actions:",
        ]
        for i, action in enumerate(self.actions, 1):
            lines.append(f"  {i}. {action}")
        lines += [
            f"",
            f"Approach:\n{self.approach}",
            f"",
            f"Information Targets: {', '.join(self.information_targets)}",
            f"",
            f"Export Requested: {self.export}",
        ]
        if self.user_instructions:
            lines += [f"", f"User Instructions: {self.user_instructions}"]
        if self.user_output_format:
            lines += [f"", f"Output Format Template:", f"{self.user_output_format}"]
        return "\n".join(lines)
