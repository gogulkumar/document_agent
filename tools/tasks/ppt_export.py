"""task_ppt_export — generate a PowerPoint presentation using python-pptx."""
from __future__ import annotations
import json
import logging
import os
import uuid

from tools.tasks.task_base import invoke_task_llm, EXPORT_ROOT

logger = logging.getLogger(__name__)

_PPT_PROMPT = """
Generate a PowerPoint outline as JSON with this structure:
{
  "title": "Presentation Title",
  "slides": [
    {
      "title": "Slide Title",
      "bullets": ["Point 1", "Point 2"],
      "notes": "Speaker notes for this slide"
    }
  ]
}
Respond ONLY with valid JSON. No markdown wrapping.
"""

def task_ppt_export(task_description: str, dependency_payload: str, **kwargs) -> str:
    try:
        from pptx import Presentation  # type: ignore
        from pptx.util import Inches, Pt  # type: ignore
    except ImportError:
        logger.error("python-pptx not installed. Run: pip install python-pptx")
        return "ERROR: python-pptx not installed"

    raw = invoke_task_llm(task_description + _PPT_PROMPT, dependency_payload, task_type="generation")

    try:
        import json5  # type: ignore
        data = json5.loads(raw)
    except Exception:
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group(0)) if match else {"title": "Report", "slides": []}

    prs = Presentation()
    slide_layout = prs.slide_layouts[1]  # title + content

    # Title slide
    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = data.get("title", "Report")

    for slide_data in data.get("slides", []):
        slide = prs.slides.add_slide(slide_layout)
        slide.shapes.title.text = slide_data.get("title", "")
        tf = slide.placeholders[1].text_frame
        tf.clear()
        for bullet in slide_data.get("bullets", []):
            p = tf.add_paragraph()
            p.text = bullet
            p.level = 0
        if slide_data.get("notes"):
            slide.notes_slide.notes_text_frame.text = slide_data["notes"]

    path = os.path.join(EXPORT_ROOT, f"{uuid.uuid4().hex}.pptx")
    prs.save(path)
    logger.info(f"PPT saved: {path}")
    return path
