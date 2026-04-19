"""task_markdown_display — return a well-structured Markdown answer."""
from tools.tasks.task_base import invoke_task_llm

_MD_PROMPT_SUFFIX = "\n\nRESPOND IN MARKDOWN FORMAT. Use headers (##), bullet points, bold for key metrics, and tables where appropriate."

def task_markdown_display(task_description: str, dependency_payload: str, **kwargs) -> str:
    return invoke_task_llm(task_description + _MD_PROMPT_SUFFIX, dependency_payload, task_type="writing")
