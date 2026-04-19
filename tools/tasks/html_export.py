"""task_html_export — generate a styled HTML report and save it to disk."""
from tools.tasks.task_base import invoke_task_llm, _save_export

_HTML_PROMPT_SUFFIX = """

RESPOND WITH A COMPLETE, SELF-CONTAINED HTML DOCUMENT.
Requirements:
- Include <html>, <head>, <body> tags
- Embed a <style> block with professional IR report styling (clean fonts, table borders, color accents)
- Use <table> for financial data
- Add a header with the report title and date
- Every data point must cite its source file
- Do NOT include any markdown or non-HTML text outside the HTML tags
"""

def task_html_export(task_description: str, dependency_payload: str, **kwargs) -> str:
    html_content = invoke_task_llm(
        task_description + _HTML_PROMPT_SUFFIX,
        dependency_payload,
        task_type="generation",
        max_tokens=16000,
    )
    return _save_export(html_content, "html")
