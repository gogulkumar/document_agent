"""task_unified_executor — general-purpose action/reasoning step (Claude Sonnet 4)."""
from tools.tasks.task_base import invoke_task_llm

def task_unified_executor(task_description: str, dependency_payload: str, **kwargs) -> str:
    return invoke_task_llm(task_description, dependency_payload, task_type="synthesis")
