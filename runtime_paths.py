"""
Centralized filesystem paths for runtime-generated Document Agent data.

These defaults intentionally resolve from the repository root instead of the
current working directory, so the app behaves the same whether it is launched
from the repo root, the Flask subdirectory, or Docker.
"""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_runtime_dir(env_var: str, default_name: str) -> str:
    raw_value = os.getenv(env_var, "").strip()
    if raw_value:
        candidate = Path(raw_value).expanduser()
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
    else:
        candidate = PROJECT_ROOT / default_name

    candidate.mkdir(parents=True, exist_ok=True)
    return str(candidate.resolve())


UPLOAD_DIR = _resolve_runtime_dir("NOTEBOOK_AGENT_UPLOAD_DIR", "uploads")
EXPORT_DIR = _resolve_runtime_dir("NOTEBOOK_AGENT_EXPORT_DIR", "exports")
SNAPSHOT_DIR = _resolve_runtime_dir("NOTEBOOK_AGENT_SNAPSHOT_DIR", "snapshot")
MEMORY_DIR = _resolve_runtime_dir("NOTEBOOK_AGENT_MEMORY_DIR", "memory")
CHAT_DIR = _resolve_runtime_dir("NOTEBOOK_AGENT_CHAT_DIR", "chats")
CONVERSATION_DIR = _resolve_runtime_dir(
    "NOTEBOOK_AGENT_CONVERSATION_DIR",
    "inmemory_conversation",
)
