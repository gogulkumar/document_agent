"""Plain text / Markdown parser — reads file as-is."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

def parse(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"[TEXT PARSE ERROR: {e}]"
