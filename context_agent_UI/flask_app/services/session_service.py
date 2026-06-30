from typing import Any, Dict
from datetime import datetime
import uuid
from chat_persistence import load_session_state, save_session_state

_SESSIONS: Dict[str, Dict[str, Any]] = {}

def get_or_create_session(run_id: str) -> Dict[str, Any]:
    if run_id not in _SESSIONS:
        restored = load_session_state(run_id)
        if restored:
            restored_metadata = restored.get("metadata", {})
            restored_metadata.setdefault("run_id", run_id)
            _SESSIONS[run_id] = {
                "messages": restored.get("messages", []),
                "available_files": restored.get("available_files", []),
                "metadata": restored_metadata,
            }
        else:
            _SESSIONS[run_id] = {
                "messages": [],
                "available_files": [],
                "metadata": {
                    "run_id": run_id,
                    "created_at": datetime.utcnow().isoformat(),
                },
            }
    return _SESSIONS[run_id]

def persist_session(run_id: str) -> None:
    if run_id in _SESSIONS:
        save_session_state(run_id, _SESSIONS[run_id])

def delete_session_data(run_id: str) -> None:
    _SESSIONS.pop(run_id, None)
