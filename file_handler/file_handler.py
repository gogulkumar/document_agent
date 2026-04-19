"""
file_handler.py — save uploaded files to disk with UUID prefix.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.getenv("NOTEBOOK_AGENT_UPLOAD_DIR", os.path.join(os.getcwd(), "uploads"))


def _sanitize_filename(name: str) -> str:
    """Remove unsafe characters from a filename."""
    name = re.sub(r"[^\w\-_. ]", "_", name)
    return name.strip()


def save_uploaded_file(
    file_bytes: bytes,
    original_name: str,
    run_id: str,
) -> Dict:
    """
    Save raw uploaded file bytes to disk.

    Returns a dict with file metadata (suitable for FileMeta).
    """
    file_id = uuid.uuid4().hex
    safe_name = _sanitize_filename(original_name)
    filename = f"{file_id[:8]}_{safe_name}"

    session_dir = os.path.join(UPLOAD_DIR, run_id)
    os.makedirs(session_dir, exist_ok=True)

    saved_path = os.path.join(session_dir, filename)
    with open(saved_path, "wb") as f:
        f.write(file_bytes)

    logger.info(f"Saved upload: {saved_path} ({len(file_bytes):,} bytes)")

    return {
        "file_id":       file_id,
        "name":          original_name,
        "saved_path":    saved_path,
        "size_bytes":    len(file_bytes),
        "uploaded_at":   datetime.utcnow().isoformat(),
    }
