"""JSON parser — pretty-prints JSON content."""
from __future__ import annotations
import json
import logging
logger = logging.getLogger(__name__)

def parse(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return json.dumps(data, indent=2)
    except Exception as e:
        return f"[JSON PARSE ERROR: {e}]"
