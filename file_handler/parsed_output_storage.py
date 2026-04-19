"""
parsed_output_storage.py — cache parsed file snapshots alongside uploads.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def save_snapshot(saved_path: str, content: str) -> str:
    """
    Save parsed markdown snapshot next to the raw uploaded file.

    Returns the snapshot file path.
    """
    snapshot_path = saved_path + ".snapshot.md"
    with open(snapshot_path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Snapshot saved: {snapshot_path} ({len(content):,} chars)")
    return snapshot_path


def get_latest_snapshot_path(saved_path: str) -> str | None:
    """Return snapshot path if it exists, else None."""
    snapshot_path = saved_path + ".snapshot.md"
    return snapshot_path if os.path.exists(snapshot_path) else None


def load_snapshot(snapshot_path: str) -> str:
    """Read and return snapshot content."""
    with open(snapshot_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def is_snapshot_fresh(saved_path: str) -> bool:
    """Return True if snapshot exists and is newer than the raw file."""
    snapshot_path = saved_path + ".snapshot.md"
    if not os.path.exists(snapshot_path):
        return False
    raw_mtime = os.path.getmtime(saved_path)
    snap_mtime = os.path.getmtime(snapshot_path)
    return snap_mtime >= raw_mtime
