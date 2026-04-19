"""task_pdf_export — generate an HTML report and convert to PDF using weasyprint."""
from __future__ import annotations
import logging
import os
import uuid

from tools.tasks.task_base import invoke_task_llm, EXPORT_ROOT, _save_export

logger = logging.getLogger(__name__)

_PDF_PROMPT = """
Generate a complete, self-contained HTML document suitable for PDF conversion.
Use clean styling with print-friendly CSS (@media print).
Include all data tables and analysis. No interactive elements.
"""

def task_pdf_export(task_description: str, dependency_payload: str, **kwargs) -> str:
    html_content = invoke_task_llm(
        task_description + _PDF_PROMPT,
        dependency_payload,
        task_type="generation",
        max_tokens=16000,
    )

    # Try weasyprint for PDF conversion
    try:
        from weasyprint import HTML  # type: ignore
        path = os.path.join(EXPORT_ROOT, f"{uuid.uuid4().hex}.pdf")
        HTML(string=html_content).write_pdf(path)
        logger.info(f"PDF saved: {path}")
        return path
    except ImportError:
        logger.warning("weasyprint not installed. Saving as HTML instead.")
        return _save_export(html_content, "html")
    except Exception as e:
        logger.error(f"PDF generation failed: {e}. Saving as HTML.")
        return _save_export(html_content, "html")
