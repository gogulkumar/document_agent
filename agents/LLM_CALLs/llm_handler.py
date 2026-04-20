"""
LLMHandler — central router that maps task_type -> model -> platform.

Task Type               Model                        Platform
-----------             --------------------------   ----------
analysis                gpt-4.1-mini                 OpenAI
planning                gpt-4.1-mini                 OpenAI
extraction              gpt-4.1                      OpenAI
reasoning               gpt-4.1                      OpenAI
decision                gpt-4.1                      OpenAI
thinking                gpt-4.1                      OpenAI
synthesis               gpt-4.1                      OpenAI
generation              claude-sonnet-4 (Bedrock)    AWS Bedrock
writing                 claude-sonnet-4 (Bedrock)    AWS Bedrock
summary                 gpt-4.1-mini                 OpenAI
conversation_summarizer gpt-4.1-mini                 OpenAI
image                   gpt-4.1                      OpenAI
"""

from __future__ import annotations

import json
import json5  # type: ignore
import logging
import os
import re
from typing import Any, Dict, Generator, List, Optional, Type, TypeVar

from pydantic import BaseModel

from agents.LLM_CALLs.llm_client import openai_chat, openai_chat_stream, bedrock_chat

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ── Model routing table ───────────────────────────────────────────────────────
OPENAI_TASK_TYPES = {
    "analysis", "planning", "extraction", "reasoning",
    "decision", "thinking", "conversation_summarizer", "image",
    "synthesis", "summary",
}

BEDROCK_TASK_TYPES = {
    "generation", "writing",
}

MODEL_MAP: Dict[str, str] = {
    "analysis":                 "gpt-4.1-mini",
    "planning":                 "gpt-4.1-mini",
    "extraction":               "gpt-4.1",
    "reasoning":                "gpt-4.1",
    "decision":                 "gpt-4.1",
    "thinking":                 "gpt-4.1",
    "synthesis":                "gpt-4.1",
    "summary":                  "gpt-4.1-mini",
    "conversation_summarizer":  "gpt-4.1-mini",
    "image":                    "gpt-4.1",
    "generation":               "anthropic.claude-sonnet-4-20250514-v1:0",
    "writing":                  "anthropic.claude-sonnet-4-20250514-v1:0",
}

# Default to OpenAI-only unless Bedrock is explicitly enabled.
_USE_BEDROCK = os.getenv("USE_BEDROCK", "false").lower() == "true"


class LLMHandler:
    """Route LLM calls to the correct model and platform."""

    def _dispatch(
        self,
        task_type: str,
        system_prompt: str,
        user_content: str,
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict] = None,
    ) -> str:
        """Route to OpenAI or Bedrock based on task_type."""
        model = MODEL_MAP.get(task_type, "gpt-4.1")

        if _USE_BEDROCK and task_type in BEDROCK_TASK_TYPES:
            logger.info(f"LLMHandler: task_type={task_type}, model={model}, platform=bedrock")
            return bedrock_chat(
                model_id=model,
                system_prompt=system_prompt,
                user_content=user_content,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            # Fallback to OpenAI for everything else (or if Bedrock disabled)
            if task_type in BEDROCK_TASK_TYPES and not _USE_BEDROCK:
                model = "gpt-4.1"  # OpenAI fallback
            logger.info(f"LLMHandler: task_type={task_type}, model={model}, platform=openai")
            return openai_chat(
                model=model,
                system_prompt=system_prompt,
                user_content=user_content,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )

    def call(
        self,
        task_type: str,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.1,
        max_tokens: int = 8192,
        response_format: Optional[Dict] = None,
    ) -> str:
        """
        Call the appropriate LLM for the given task_type.
        Returns the raw text response string.
        """
        return self._dispatch(
            task_type=task_type,
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    def call_stream(
        self,
        task_type: str,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> Generator[str, None, None]:
        """
        Streaming call — yields text chunks as they arrive.
        Currently only supports OpenAI streaming.
        """
        model = MODEL_MAP.get(task_type, "gpt-4.1")
        if task_type in BEDROCK_TASK_TYPES and _USE_BEDROCK:
            # Bedrock: fall back to non-streaming and yield whole response
            result = bedrock_chat(
                model_id=model,
                system_prompt=system_prompt,
                user_content=user_content,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            yield result
        else:
            if task_type in BEDROCK_TASK_TYPES and not _USE_BEDROCK:
                model = "gpt-4.1"
            yield from openai_chat_stream(
                model=model,
                system_prompt=system_prompt,
                user_content=user_content,
                temperature=temperature,
                max_tokens=max_tokens,
            )

    def call_structured(
        self,
        task_type: str,
        system_prompt: str,
        user_content: str,
        output_schema: Type[T],
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> T:
        """
        Call LLM and parse the response into a Pydantic model.
        Uses a 4-attempt JSON fallback chain.
        """
        schema_json = output_schema.model_json_schema()
        enhanced_prompt = (
            f"{system_prompt}\n\n"
            f"IMPORTANT: Respond ONLY with valid JSON matching this schema:\n"
            f"{json.dumps(schema_json, indent=2)}"
        )

        raw = self.call(
            task_type=task_type,
            system_prompt=enhanced_prompt,
            user_content=user_content,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return self._parse_json_with_fallback(raw, output_schema)

    # ── JSON fallback chain ───────────────────────────────────────────────────
    @staticmethod
    def _parse_json_with_fallback(raw: str, schema: Type[T]) -> T:
        """
        4-attempt JSON parsing chain:
          1. Raw json.loads
          2. Trailing-comma cleanup -> json.loads
          3. json5 lenient parser
          4. Extract JSON from markdown code blocks
        """
        text = raw.strip()

        # Attempt 1: direct parse
        try:
            data = json.loads(text)
            return schema.model_validate(data)
        except Exception:
            pass

        # Attempt 2: strip trailing commas
        try:
            cleaned = re.sub(r",\s*([}\]])", r"\1", text)
            data = json.loads(cleaned)
            return schema.model_validate(data)
        except Exception:
            pass

        # Attempt 3: json5
        try:
            data = json5.loads(text)
            return schema.model_validate(data)
        except Exception:
            pass

        # Attempt 4: extract from code block or first { … }
        try:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if not match:
                match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group(1) if match.lastindex else match.group(0))
                return schema.model_validate(data)
        except Exception:
            pass

        # Final fallback: return default instance
        logger.error("All JSON parsing attempts failed. Returning default model instance.")
        return schema()


# Module-level singleton
llm_handler = LLMHandler()
