"""
Central tool registry — maps tool names to callables.
"""

from tools.workers.extraction_tools import worker_document_extractor
from tools.tasks.unified_executor import task_unified_executor
from tools.tasks.plain_text_display import task_plain_text_display
from tools.tasks.markdown_display import task_markdown_display
from tools.tasks.html_export import task_html_export
from tools.tasks.dashboard_display import task_dashboard_display
from tools.tasks.ppt_export import task_ppt_export
from tools.tasks.pdf_export import task_pdf_export
from tools.tasks.word_export import task_word_export

WORKER_TOOLS = {
    "worker_document_extractor": worker_document_extractor,
}

TASK_TOOLS = {
    "task_unified_executor": task_unified_executor,
}

EXPORT_TOOLS = {
    "task_plain_text_display":  task_plain_text_display,
    "task_markdown_display":    task_markdown_display,
    "task_html_export":         task_html_export,
    "task_dashboard_display":   task_dashboard_display,
    "task_ppt_export":          task_ppt_export,
    "task_pdf_export":          task_pdf_export,
    "task_word_export":         task_word_export,
}

ALL_TOOLS = {**WORKER_TOOLS, **TASK_TOOLS, **EXPORT_TOOLS}
