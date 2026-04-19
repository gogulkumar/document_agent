"""
snapshot_recorder.py — lightweight JSON index of all agent runs.
Stores {message_id, run_id, created_at, analysis_goal, display_format}.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = os.path.join(os.getcwd(), "snapshot")
SNAPSHOTS_FILE = os.path.join(SNAPSHOT_DIR, "snapshots.json")


def _load() -> List[Dict]:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    if not os.path.exists(SNAPSHOTS_FILE):
        return []
    with open(SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(snapshots: List[Dict]) -> None:
    with open(SNAPSHOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, indent=2)


def record_snapshot(
    run_id: str,
    message_id: str,
    analysis_goal: str = "",
    display_format: str = "html",
) -> None:
    """Append a new snapshot record to the index."""
    snapshots = _load()
    snapshots.append({
        "message_id":    message_id,
        "run_id":        run_id,
        "created_at":    datetime.utcnow().isoformat(),
        "analysis_goal": analysis_goal,
        "display_format": display_format,
    })
    _save(snapshots)


def get_snapshots(run_id: Optional[str] = None) -> List[Dict]:
    """Return all snapshots, optionally filtered by run_id."""
    snapshots = _load()
    if run_id:
        return [s for s in snapshots if s.get("run_id") == run_id]
    return snapshots
