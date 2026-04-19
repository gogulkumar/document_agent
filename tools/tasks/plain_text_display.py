"""task_plain_text_display — return a clean plain-text answer."""
from tools.tasks.task_base import invoke_task_llm

_PLAIN_PROMPT_SUFFIX = "\n\nRESPOND IN PLAIN TEXT ONLY. No markdown, no HTML, no special formatting."

def task_plain_text_display(task_description: str, dependency_payload: str, **kwargs) -> str:
    return invoke_task_llm(task_description + _PLAIN_PROMPT_SUFFIX, dependency_payload, task_type="writing")
