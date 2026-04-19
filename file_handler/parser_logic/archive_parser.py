"""Archive parser — lists contents and extracts text files from ZIP/tar archives."""
from __future__ import annotations
import logging
import os
import tempfile
logger = logging.getLogger(__name__)

def parse(file_path: str) -> str:
    try:
        import zipfile
        import tarfile
        lines = []
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, "r") as zf:
                for name in zf.namelist():
                    lines.append(f"[Archive member]: {name}")
                    if name.endswith((".txt", ".md", ".csv")):
                        try:
                            content = zf.read(name).decode("utf-8", errors="replace")[:5000]
                            lines.append(content)
                        except Exception:
                            pass
        elif tarfile.is_tarfile(file_path):
            with tarfile.open(file_path, "r:*") as tf:
                for member in tf.getmembers():
                    lines.append(f"[Archive member]: {member.name}")
        return "\n".join(lines) or "[Empty archive]"
    except Exception as e:
        return f"[ARCHIVE PARSE ERROR: {e}]"
