"""Audio parser — transcribes using OpenAI Whisper API."""
from __future__ import annotations
import logging
import os
logger = logging.getLogger(__name__)

def parse(file_path: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        with open(file_path, "rb") as f:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=f)
        return transcript.text
    except Exception as e:
        return f"[AUDIO PARSE ERROR: {e}]"
