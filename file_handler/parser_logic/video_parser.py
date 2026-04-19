"""Video parser — extracts audio track and transcribes with Whisper."""
from __future__ import annotations
import logging
import os
import tempfile
logger = logging.getLogger(__name__)

def parse(file_path: str) -> str:
    try:
        import subprocess
        # Extract audio to temp wav file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ar", "16000", "-ac", "1", tmp_path, "-y"],
            capture_output=True, check=True,
        )
        from file_handler.parser_logic.audio_parser import parse as audio_parse
        result = audio_parse(tmp_path)
        os.unlink(tmp_path)
        return result
    except FileNotFoundError:
        return "[VIDEO PARSE ERROR: ffmpeg not found. Install ffmpeg to transcribe video files.]"
    except Exception as e:
        return f"[VIDEO PARSE ERROR: {e}]"
