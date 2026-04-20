"""
Low-level HTTP clients for OpenAI and AWS Bedrock.
Reads configuration from environment variables / .env file.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Generator, List, Optional

import boto3  # type: ignore
from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Runtime mode ─────────────────────────────────────────────────────────────
RUNTIME = os.getenv("NOTEBOOK_AGENT_RUNTIME", "local")  # "local" | "workflow"


def _get_openai_client() -> OpenAI:
    """Return a configured OpenAI client (cached per-thread via OpenAI internals)."""
    if RUNTIME == "workflow":
        key = os.getenv("WORKFLOW_OPENAI_KEY", "")
    else:
        key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "OpenAI API key not found. Set OPENAI_API_KEY in your .env file."
        )
    return OpenAI(api_key=key)


def openai_chat(
    model: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.1,
    max_tokens: int = 8192,
    response_format: Optional[Dict] = None,
) -> str:
    """
    Call the OpenAI Chat Completions API.

    Returns the assistant message text.
    """
    client = _get_openai_client()

    kwargs: Dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    if response_format:
        kwargs["response_format"] = response_format

    logger.debug(f"OpenAI call: model={model}, temp={temperature}, max_tokens={max_tokens}")
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def openai_chat_stream(
    model: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.1,
    max_tokens: int = 8192,
) -> Generator[str, None, None]:
    """
    Streaming call to OpenAI Chat Completions.
    Yields text chunks as they arrive from the API.
    """
    client = _get_openai_client()

    kwargs: Dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }

    logger.debug(f"OpenAI stream: model={model}, temp={temperature}, max_tokens={max_tokens}")
    stream = client.chat.completions.create(**kwargs)

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


def bedrock_chat(
    model_id: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.1,
    max_tokens: int = 8192,
) -> str:
    """
    Call AWS Bedrock (Anthropic Claude) via boto3.

    Requires AWS credentials to be configured (IAM role, env vars, or ~/.aws/credentials).
    """
    region = os.getenv("AWS_REGION", "us-east-1")
    client = boto3.client("bedrock-runtime", region_name=region)

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }

    logger.debug(f"Bedrock call: model_id={model_id}, temp={temperature}, max_tokens={max_tokens}")
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    result = json.loads(response["body"].read())
    return result["content"][0]["text"]
