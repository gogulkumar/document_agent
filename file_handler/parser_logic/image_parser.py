"""Image parser — uses GPT-4 Vision to describe image content."""
from __future__ import annotations
import base64
import logging
import os
logger = logging.getLogger(__name__)

def parse(file_path: str) -> str:
    try:
        from openai import OpenAI
        with open(file_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif"}.get(ext, "image/png")
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        response = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image in detail, including all text, numbers, charts, and data visible."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_data}"}},
                ],
            }],
            max_tokens=2048,
        )
        return response.choices[0].message.content or "[No description]"
    except Exception as e:
        return f"[IMAGE PARSE ERROR: {e}]"
