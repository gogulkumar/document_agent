"""
parser.py — dispatch uploaded files to the correct parser by extension.
"""

from __future__ import annotations

import logging
import os
from typing import Dict

from file_handler.parsed_output_storage import (
    get_latest_snapshot_path,
    is_snapshot_fresh,
    save_snapshot,
)

logger = logging.getLogger(__name__)


def _get_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower().lstrip(".")


def parse_uploaded_file(file_meta: Dict) -> Dict:
    """
    Parse a file and return updated FileMeta with:
      - snapshot_path: path to parsed .md snapshot
      - num_chars:     character count of parsed text
      - topic_hint:    auto-detected topic
    """
    saved_path = file_meta.get("saved_path", "")
    name = file_meta.get("name", "")
    ext = _get_extension(name)

    # Cache hit: re-use existing snapshot
    if is_snapshot_fresh(saved_path):
        snapshot_path = get_latest_snapshot_path(saved_path)
        with open(snapshot_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"Cache hit for {name}. Using existing snapshot.")
        file_meta["snapshot_path"] = snapshot_path
        file_meta["num_chars"] = len(content)
        return file_meta

    # Route to correct parser
    parser_fn = _get_parser(ext)
    try:
        parsed_text = parser_fn(saved_path)
    except Exception as e:
        logger.error(f"Parser failed for {name} ({ext}): {e}")
        parsed_text = f"[PARSE ERROR: {e}]"

    # Wrap in snapshot format
    snapshot_content = f"## Content\n\n{parsed_text}\n\n## Artifacts\n\n(none)\n"
    snapshot_path = save_snapshot(saved_path, snapshot_content)

    file_meta["snapshot_path"] = snapshot_path
    file_meta["num_chars"] = len(parsed_text)
    file_meta["topic_hint"] = _auto_topic_hint(name, ext)

    return file_meta


def _get_parser(ext: str):
    """Return the parser function for a given file extension."""
    from file_handler.parser_logic import (
        pdf_parser, presentation_parser, document_parser,
        spreadsheet_parser, tabular_parser, image_parser,
        audio_parser, video_parser, html_parser,
        json_parser, xml_parser, archive_parser, text_parser,
    )
    mapping = {
        "pdf":          pdf_parser.parse,
        "pptx":         presentation_parser.parse,
        "ppt":          presentation_parser.parse,
        "docx":         document_parser.parse,
        "doc":          document_parser.parse,
        "xlsx":         spreadsheet_parser.parse,
        "xls":          spreadsheet_parser.parse,
        "csv":          tabular_parser.parse,
        "tsv":          tabular_parser.parse,
        "png":          image_parser.parse,
        "jpg":          image_parser.parse,
        "jpeg":         image_parser.parse,
        "gif":          image_parser.parse,
        "mp3":          audio_parser.parse,
        "wav":          audio_parser.parse,
        "mp4":          video_parser.parse,
        "mov":          video_parser.parse,
        "html":         html_parser.parse,
        "htm":          html_parser.parse,
        "json":         json_parser.parse,
        "xml":          xml_parser.parse,
        "zip":          archive_parser.parse,
        "tar":          archive_parser.parse,
        "gz":           archive_parser.parse,
        "txt":          text_parser.parse,
        "md":           text_parser.parse,
    }
    return mapping.get(ext, text_parser.parse)


def _auto_topic_hint(name: str, ext: str) -> str:
    """Generate a short topic hint from the filename."""
    base = os.path.splitext(name)[0].replace("_", " ").replace("-", " ")
    return f"{base} ({ext.upper()})"
