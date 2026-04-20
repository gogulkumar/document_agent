"""task_dashboard_display — generate a dashboard spec (JSON + HTML)."""
from tools.tasks.task_base import invoke_task_llm, _save_export

_DASHBOARD_SUFFIX = """

Generate an interactive HTML dashboard with:
- KPI summary cards at the top (large bold numbers)
- Chart.js bar and line charts for trends
- A data table with key metrics
- A relationship map / information brain section that shows how metrics and themes connect
- A brainstorm panel with 3-5 suggested next analyses
- Clean, professional color scheme with strong hierarchy and editorial contrast
Respond with a complete self-contained HTML file including inline JavaScript for Chart.js (CDN).
"""

def task_dashboard_display(task_description: str, dependency_payload: str, **kwargs) -> str:
    html = invoke_task_llm(task_description + _DASHBOARD_SUFFIX, dependency_payload, task_type="generation", max_tokens=16000)
    return _save_export(html, "html")
