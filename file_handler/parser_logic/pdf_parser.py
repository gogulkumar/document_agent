"""PDF parser — extracts text using pdfplumber, falls back to PyMuPDF."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

def parse(file_path: str) -> str:
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(file_path) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                table_text = ""
                for table in tables:
                    for row in table:
                        table_text += " | ".join(str(c or "") for c in row) + "\n"
                pages.append(f"--- Page {i+1} ---\n{text}\n{table_text}")
            return "\n\n".join(pages)
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}. Trying PyMuPDF.")
    try:
        import fitz  # type: ignore  (PyMuPDF)
        doc = fitz.open(file_path)
        return "\n\n".join(page.get_text() for page in doc)
    except Exception as e2:
        return f"[PDF PARSE ERROR: {e2}]"
