"""XML parser — extracts text nodes using ElementTree."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

def parse(file_path: str) -> str:
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(file_path)
        texts = [elem.text.strip() for elem in tree.iter() if elem.text and elem.text.strip()]
        return "\n".join(texts)
    except Exception as e:
        return f"[XML PARSE ERROR: {e}]"
