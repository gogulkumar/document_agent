"""
Flask Web UI — Document AI Notebook Agent
Handles file upload, chat, export downloads, and conversation persistence.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

from dotenv import load_dotenv
from flask import (
    Flask, jsonify, render_template, request,
    send_file, stream_with_context, Response,
)
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── App factory ───────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB upload limit

# ── Local imports (after sys.path is set) ─────────────────────────────────────
import sys
# Ensure project root is on the path when running from context_agent_UI/flask_app
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agents.graph import get_graph
from agents.state import AgentState, FileMeta
from file_handler.file_handler import save_uploaded_file
from file_handler.parser import parse_uploaded_file
from file_handler.parsed_output_storage import get_latest_snapshot_path
from conversation_summarizer import update_summary_file, read_summary
from inmemory_recorder import build_turn_snapshot, save_turn_log
from snapshot_recorder import record_snapshot

# ── In-memory session store ───────────────────────────────────────────────────
# Keyed by run_id:
#   {"messages": [...], "available_files": [...], "metadata": {...}}
_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _get_or_create_session(run_id: str) -> Dict[str, Any]:
    if run_id not in _SESSIONS:
        _SESSIONS[run_id] = {
            "messages": [],
            "available_files": [],
            "metadata": {
                "run_id": run_id,
                "created_at": datetime.utcnow().isoformat(),
            },
        }
    return _SESSIONS[run_id]


# ── Langfuse tracing (optional) ───────────────────────────────────────────────
def _get_langfuse_callback():
    host = os.getenv("LANGFUSE_HOST", "")
    secret = os.getenv("LANGFUSE_SECRET_KEY", "")
    public = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    if not (host and secret and public):
        return None
    try:
        import requests as req
        req.get(host, timeout=2)
        from langfuse.callback import CallbackHandler  # type: ignore
        return CallbackHandler(public_key=public, secret_key=secret, host=host)
    except Exception as e:
        logger.warning(f"Langfuse not available: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Serve the main chat UI."""
    return render_template("index.html")


@app.route("/api/session/new", methods=["POST"])
def new_session():
    """Create a new session and return its run_id."""
    run_id = uuid.uuid4().hex
    _get_or_create_session(run_id)
    return jsonify({"run_id": run_id})


@app.route("/api/upload", methods=["POST"])
def handle_file_upload():
    """
    Upload and parse one or more files.
    Returns updated file catalog for the session.
    """
    run_id = request.form.get("run_id", uuid.uuid4().hex)
    session = _get_or_create_session(run_id)

    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    uploaded = []
    for file in request.files.getlist("files"):
        if not file.filename:
            continue

        # Save raw bytes
        file_bytes = file.read()
        file_meta = save_uploaded_file(
            file_bytes=file_bytes,
            original_name=file.filename,
            run_id=run_id,
        )

        # Parse and snapshot
        file_meta = parse_uploaded_file(file_meta)

        # Attach snapshot_path if missing
        if not file_meta.get("snapshot_path"):
            sp = get_latest_snapshot_path(file_meta["saved_path"])
            if sp:
                file_meta["snapshot_path"] = sp

        session["available_files"].append(file_meta)
        uploaded.append({
            "file_id": file_meta["file_id"],
            "name":    file_meta["name"],
            "chars":   file_meta.get("num_chars", 0),
            "topic":   file_meta.get("topic_hint", ""),
        })
        logger.info(f"Uploaded & parsed: {file.filename} (run_id={run_id})")

    return jsonify({"run_id": run_id, "files": uploaded})


@app.route("/api/ingest", methods=["POST"])
def ingest_existing_file():
    """Re-ingest a file already on disk (cache hit skips re-parsing)."""
    data = request.get_json()
    run_id = data.get("run_id", "")
    saved_path = data.get("saved_path", "")

    if not os.path.exists(saved_path):
        return jsonify({"error": f"File not found: {saved_path}"}), 404

    session = _get_or_create_session(run_id)
    file_meta = {
        "file_id":    uuid.uuid4().hex,
        "name":       os.path.basename(saved_path),
        "saved_path": saved_path,
        "num_chars":  0,
    }
    file_meta = parse_uploaded_file(file_meta)
    session["available_files"].append(file_meta)

    return jsonify({"file_id": file_meta["file_id"], "chars": file_meta.get("num_chars", 0)})


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Main chat endpoint. Runs the full LangGraph pipeline.

    Request JSON:
        run_id: str
        message: str
        message_id: str (optional)

    Response JSON:
        output: str          (rendered HTML of last display task)
        export_artifacts: list
        task_results: list
        run_id: str
        message_id: str
    """
    data = request.get_json()
    run_id = data.get("run_id", uuid.uuid4().hex)
    user_message = data.get("message", "").strip()
    message_id = data.get("message_id", uuid.uuid4().hex)
    web_search_enabled = data.get("web_search", False)

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    session = _get_or_create_session(run_id)
    session["messages"].append(HumanMessage(content=user_message))

    # Build AgentState
    state: AgentState = {
        "messages":        session["messages"],
        "available_files": session["available_files"],
        "metadata": {
            **session["metadata"],
            "message_id": message_id,
            "user_id":    data.get("user_id", "anonymous"),
            "web_search_enabled": web_search_enabled,
        },
    }

    # Optional Langfuse tracing
    callbacks = []
    lf = _get_langfuse_callback()
    if lf:
        callbacks.append(lf)

    # Run the graph
    graph = get_graph()
    try:
        config = {"callbacks": callbacks} if callbacks else {}
        result_state = graph.invoke(state, config=config)
    except Exception as e:
        logger.error(f"Graph invocation failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    # Extract outputs
    task_results: List[Dict] = result_state.get("task_results", [])
    export_artifacts: List[Dict] = result_state.get("export_artifacts", [])

    # Find the last display task output for rendering
    output_html = ""
    for tr in reversed(task_results):
        if tr.get("type") == "display" or tr.get("display_format"):
            output_html = tr.get("output", "")
            break
    if not output_html and task_results:
        output_html = task_results[-1].get("output", "")

    # Append AI response to conversation history
    session["messages"].append(AIMessage(content=output_html[:2000]))

    # Persist conversation summary
    augmentor_payload = result_state.get("augmentor_payload", {})
    planner_question = result_state.get("planner_question", user_message)
    context_plan = result_state.get("context_plan", {})

    snapshot = build_turn_snapshot(
        message_id=message_id,
        run_id=run_id,
        user_question=user_message,
        augmented_question=planner_question,
        context_plan=context_plan,
        worker_results=result_state.get("worker_results", []),
        task_results=task_results,
    )
    save_turn_log(run_id, message_id, snapshot)
    update_summary_file(run_id, snapshot)
    record_snapshot(
        run_id=run_id,
        message_id=message_id,
        analysis_goal=context_plan.get("analysis_goal", ""),
        display_format=task_results[-1].get("display_format", "html") if task_results else "html",
    )

    # Make export artifact paths relative for the frontend
    clean_artifacts = []
    for art in export_artifacts:
        path = art.get("path", "")
        clean_artifacts.append({
            "task_id":        art.get("task_id"),
            "display_format": art.get("display_format"),
            "filename":       os.path.basename(path) if path else "",
            "download_url":   f"/api/export/{os.path.basename(path)}" if path else "",
        })

    return jsonify({
        "run_id":           run_id,
        "message_id":       message_id,
        "output":           output_html,
        "export_artifacts": clean_artifacts,
        "task_results":     [
            {"task_id": tr["task_id"], "type": tr["type"], "display_format": tr.get("display_format")}
            for tr in task_results
        ],
    })


@app.route("/api/export/<filename>", methods=["GET"])
def download_export(filename: str):
    """Serve an exported file (PDF, PPT, Word, HTML) for download."""
    export_dir = os.path.abspath(os.getenv("NOTEBOOK_AGENT_EXPORT_DIR", os.path.join(os.getcwd(), "exports")))
    file_path = os.path.join(export_dir, filename)

    # Security: ensure path is inside export_dir
    if not os.path.abspath(file_path).startswith(export_dir):
        return jsonify({"error": "Invalid path"}), 403

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    return send_file(file_path, as_attachment=True)


@app.route("/api/session/<run_id>/files", methods=["GET"])
def get_session_files(run_id: str):
    """Return the file catalog for a session."""
    session = _SESSIONS.get(run_id, {})
    files = session.get("available_files", [])
    return jsonify([
        {"file_id": f["file_id"], "name": f["name"], "chars": f.get("num_chars", 0)}
        for f in files
    ])


@app.route("/api/session/<run_id>/summary", methods=["GET"])
def get_session_summary(run_id: str):
    """Return the compressed conversation summary for a session."""
    return jsonify({"summary": read_summary(run_id)})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Starting Document AI Agent on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
