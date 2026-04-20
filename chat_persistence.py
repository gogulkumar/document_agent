"""
Disk-backed chat/session persistence for the Flask UI.

Stores:
- chats/<run_id>/session.json          current session state
- chats/<run_id>/langgraph_events.jsonl  streaming trace/events
- chats/<run_id>/turns/<message_id>.json turn-level payloads
- memory/<run_id>/conversation_summary.md compressed memory
- uploads/<run_id>/...                 uploaded raw files and parser snapshots
- exports/<filename>                   exported artifacts referenced by this chat
- inmemory_conversation/<run_id>/...   legacy/local recorder directory
- snapshot/snapshots.json              global snapshot index entries
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage

from runtime_paths import CHAT_DIR, CONVERSATION_DIR, EXPORT_DIR, MEMORY_DIR, SNAPSHOT_DIR, UPLOAD_DIR


def _chat_session_dir(run_id: str) -> str:
    path = os.path.join(CHAT_DIR, run_id)
    os.makedirs(path, exist_ok=True)
    return path


def _memory_session_dir(run_id: str) -> str:
    path = os.path.join(MEMORY_DIR, run_id)
    os.makedirs(path, exist_ok=True)
    return path


def _message_to_dict(message: AnyMessage) -> Dict[str, str]:
    if isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, AIMessage):
        role = "assistant"
    elif isinstance(message, SystemMessage):
        role = "system"
    else:
        role = getattr(message, "type", "assistant")

    content = message.content if hasattr(message, "content") else str(message)
    if isinstance(content, list):
        content = json.dumps(content)
    return {"role": role, "content": content or ""}


def _dict_to_message(data: Dict[str, Any]) -> AnyMessage:
    role = data.get("role", "assistant")
    content = data.get("content", "")
    if role == "user":
        return HumanMessage(content=content)
    if role == "system":
        return SystemMessage(content=content)
    return AIMessage(content=content)


def save_session_state(run_id: str, session: Dict[str, Any]) -> None:
    path = os.path.join(_chat_session_dir(run_id), "session.json")
    payload = {
        "run_id": run_id,
        "updated_at": datetime.utcnow().isoformat(),
        "metadata": session.get("metadata", {}),
        "available_files": session.get("available_files", []),
        "messages": [_message_to_dict(msg) for msg in session.get("messages", [])],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def load_session_state(run_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(CHAT_DIR, run_id, "session.json")
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    return {
        "messages": [_dict_to_message(item) for item in data.get("messages", [])],
        "available_files": data.get("available_files", []),
        "metadata": data.get("metadata", {}),
    }


def append_langgraph_event(run_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    path = os.path.join(_chat_session_dir(run_id), "langgraph_events.jsonl")
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event_type,
        "payload": payload,
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def save_turn_payload(run_id: str, message_id: str, payload: Dict[str, Any]) -> None:
    turns_dir = os.path.join(_chat_session_dir(run_id), "turns")
    os.makedirs(turns_dir, exist_ok=True)
    path = os.path.join(turns_dir, f"{message_id}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def save_memory_summary(run_id: str, summary: str) -> None:
    path = os.path.join(_memory_session_dir(run_id), "conversation_summary.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(summary)


def serialize_messages_for_client(messages: List[AnyMessage]) -> List[Dict[str, str]]:
    return [_message_to_dict(message) for message in messages]


def list_saved_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    sessions: List[Dict[str, Any]] = []
    if not os.path.exists(CHAT_DIR):
        return sessions

    for run_id in os.listdir(CHAT_DIR):
        session_path = os.path.join(CHAT_DIR, run_id, "session.json")
        if not os.path.exists(session_path):
            continue
        try:
            with open(session_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            continue

        messages = data.get("messages", [])
        last_user = next((msg.get("content", "") for msg in reversed(messages) if msg.get("role") == "user"), "")
        available_files = data.get("available_files", [])
        sessions.append({
            "run_id": data.get("run_id", run_id),
            "updated_at": data.get("updated_at") or data.get("metadata", {}).get("created_at", ""),
            "preview": (last_user or "New session").strip()[:120],
            "message_count": len(messages),
            "file_count": len(available_files),
        })

    sessions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return sessions[:limit]


def _collect_export_paths(run_id: str) -> List[str]:
    export_paths: set[str] = set()
    turns_dir = os.path.join(CHAT_DIR, run_id, "turns")
    if not os.path.exists(turns_dir):
        return []

    for filename in os.listdir(turns_dir):
        if not filename.endswith(".json"):
            continue
        turn_path = os.path.join(turns_dir, filename)
        try:
            with open(turn_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            continue

        for artifact in payload.get("export_artifacts", []):
            artifact_name = (artifact.get("filename") or "").strip()
            if not artifact_name:
                continue
            candidate = os.path.abspath(os.path.join(EXPORT_DIR, artifact_name))
            if candidate.startswith(os.path.abspath(EXPORT_DIR) + os.sep) and os.path.exists(candidate):
                export_paths.add(candidate)

    return sorted(export_paths)


def _remove_snapshot_entries(run_id: str) -> bool:
    snapshots_file = os.path.join(SNAPSHOT_DIR, "snapshots.json")
    if not os.path.exists(snapshots_file):
        return False

    try:
        with open(snapshots_file, "r", encoding="utf-8") as handle:
            snapshots = json.load(handle)
    except Exception:
        return False

    if not isinstance(snapshots, list):
        return False

    filtered = [snapshot for snapshot in snapshots if snapshot.get("run_id") != run_id]
    if len(filtered) == len(snapshots):
        return False

    with open(snapshots_file, "w", encoding="utf-8") as handle:
        json.dump(filtered, handle, indent=2)
    return True


def delete_saved_session(run_id: str) -> bool:
    removed = False
    export_paths = _collect_export_paths(run_id)

    chat_dir = os.path.join(CHAT_DIR, run_id)
    memory_dir = os.path.join(MEMORY_DIR, run_id)
    upload_dir = os.path.join(UPLOAD_DIR, run_id)
    conversation_dir = os.path.join(CONVERSATION_DIR, run_id)

    for export_path in export_paths:
        try:
            os.remove(export_path)
            removed = True
        except FileNotFoundError:
            continue

    for target_dir in [chat_dir, memory_dir, upload_dir, conversation_dir]:
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir, ignore_errors=True)
            removed = True

    if _remove_snapshot_entries(run_id):
        removed = True

    return removed
