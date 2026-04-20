"""
Flask Web UI — Document AI Notebook Agent
Handles file upload, chat (sync + SSE streaming), export downloads,
and conversation persistence.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

from dotenv import load_dotenv
from flask import (
    Flask, jsonify, redirect, render_template, request,
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
from agents.graph import route_after_augmentor, route_after_planner
from agents.nodes.context_planner_node import context_planner_node
from agents.nodes.direct_response_node import build_direct_response_request
from agents.nodes.query_augmentor_node import query_augmentor_node
from agents.nodes.task_executor_node import task_executor_node
from agents.nodes.worker_tool_executor_node import worker_tool_executor_node
from agents.state import AgentState, FileMeta
from agents.LLM_CALLs.llm_handler import llm_handler
from chat_persistence import (
    append_langgraph_event,
    delete_saved_session,
    list_saved_sessions,
    load_session_state,
    save_memory_summary,
    save_session_state,
    save_turn_payload,
    serialize_messages_for_client,
)
from file_handler.file_handler import save_uploaded_file
from file_handler.parser import parse_uploaded_file
from file_handler.parsed_output_storage import get_latest_snapshot_path
from conversation_summarizer import update_summary_file, read_summary
from inmemory_recorder import build_turn_snapshot, save_turn_log
from runtime_paths import EXPORT_DIR
from snapshot_recorder import record_snapshot
from tools.tasks.task_base import _save_export

# ── In-memory session store ───────────────────────────────────────────────────
# Keyed by run_id:
#   {"messages": [...], "available_files": [...], "metadata": {...}}
_SESSIONS: Dict[str, Dict[str, Any]] = {}

FEATURE_TITLES = {
    "mind-map": "Mind Map",
    "information-brain": "Information Brain",
    "brainstorm": "Brainstorm",
}

FEATURE_SYSTEM_PROMPTS = {
    "mind-map": """
You are generating a premium document-derived mind map as a complete self-contained HTML document.

Goal:
- Transform the source material into a connected mind map, not a plain summary
- Show the central theme, major branches, supporting evidence, and key dependencies
- Make the structure visually obvious, with clean hierarchy and strong spacing

Requirements:
- Respond with complete HTML only
- Include <html>, <head>, <body>, and an inline <style> block
- Build a clear visual map using HTML/CSS cards, connectors, clusters, or lanes
- Include a concise legend or framing note so users understand the map immediately
- Include citations to source files where possible
- Do not output markdown fences or commentary outside the HTML
""".strip(),
    "information-brain": """
You are generating an information brain as a complete self-contained HTML document.

Goal:
- Explain how the core ideas, entities, evidence, risks, and outcomes connect
- Emphasize relationships, tensions, cause/effect, and what matters most
- Present this as a structured knowledge system rather than a plain report

Requirements:
- Respond with complete HTML only
- Include <html>, <head>, <body>, and an inline <style> block
- Organize the page into connected nodes or panels such as themes, evidence, risks, actions, and implications
- Make cross-links and dependency paths explicit
- Include citations to source files where possible
- Do not output markdown fences or commentary outside the HTML
""".strip(),
    "brainstorm": """
You are generating a brainstorming board as a complete self-contained HTML document.

Goal:
- Produce bold, high-value next-step ideas from the available document context
- Group ideas into opportunities, risks, experiments, and strategic moves
- Make it feel like a working ideation board for a human operator

Requirements:
- Respond with complete HTML only
- Include <html>, <head>, <body>, and an inline <style> block
- Use strong hierarchy and clearly separated idea clusters
- Include sections for immediate actions, deeper investigations, and open questions
- Reference source material where possible
- Do not output markdown fences or commentary outside the HTML
""".strip(),
}


def _get_or_create_session(run_id: str) -> Dict[str, Any]:
    if run_id not in _SESSIONS:
        restored = load_session_state(run_id)
        if restored:
            restored_metadata = restored.get("metadata", {})
            restored_metadata.setdefault("run_id", run_id)
            _SESSIONS[run_id] = {
                "messages": restored.get("messages", []),
                "available_files": restored.get("available_files", []),
                "metadata": restored_metadata,
            }
        else:
            _SESSIONS[run_id] = {
                "messages": [],
                "available_files": [],
                "metadata": {
                    "run_id": run_id,
                    "created_at": datetime.utcnow().isoformat(),
                },
            }
    return _SESSIONS[run_id]


def _persist_session(run_id: str) -> None:
    save_session_state(run_id, _SESSIONS[run_id])


def _latest_message_content(session: Dict[str, Any], role: str) -> str:
    for message in reversed(session.get("messages", [])):
        if role == "assistant" and isinstance(message, AIMessage):
            return message.content if isinstance(message.content, str) else str(message.content)
        if role == "user" and isinstance(message, HumanMessage):
            return message.content if isinstance(message.content, str) else str(message.content)
    return ""


def _read_text_excerpt(path: str, max_chars: int = 3500) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(max_chars)
    except Exception as exc:
        logger.warning(f"Failed to read feature context from {path}: {exc}")
        return ""


def _build_feature_payload(run_id: str, session: Dict[str, Any], feature_kind: str) -> str:
    summary = read_summary(run_id).strip()
    latest_user = _latest_message_content(session, "user").strip()
    latest_assistant = _latest_message_content(session, "assistant").strip()

    file_summaries: List[str] = []
    for file_meta in session.get("available_files", [])[:4]:
        excerpt = _read_text_excerpt(file_meta.get("snapshot_path", ""), max_chars=2500).strip()
        file_summaries.append(
            "\n".join(
                part for part in [
                    f"File: {file_meta.get('name', 'Unknown')}",
                    f"Topic hint: {file_meta.get('topic_hint', '')}",
                    f"Parsed chars: {file_meta.get('num_chars', 0)}",
                    f"Excerpt:\n{excerpt}" if excerpt else "",
                ] if part
            )
        )

    sections = [
        f"Feature requested: {FEATURE_TITLES.get(feature_kind, feature_kind)}",
        f"Latest user request:\n{latest_user}" if latest_user else "",
        f"Latest assistant answer:\n{latest_assistant[:9000]}" if latest_assistant else "",
        f"Conversation memory summary:\n{summary[:9000]}" if summary else "",
        "Document context:\n" + "\n\n---\n\n".join(file_summaries) if file_summaries else "",
    ]
    return "\n\n".join(section for section in sections if section).strip() or "No document context available."


def _generate_feature_html(run_id: str, feature_kind: str) -> Dict[str, Any]:
    if feature_kind not in FEATURE_SYSTEM_PROMPTS:
        raise ValueError(f"Unsupported feature: {feature_kind}")

    session = _get_or_create_session(run_id)
    payload = _build_feature_payload(run_id, session, feature_kind)
    html = llm_handler.call(
        task_type="generation",
        system_prompt=FEATURE_SYSTEM_PROMPTS[feature_kind],
        user_content=payload,
        temperature=0.2,
        max_tokens=16000,
    )
    export_path = _save_export(html, "html")
    filename = os.path.basename(export_path)
    return {
        "feature": feature_kind,
        "title": FEATURE_TITLES[feature_kind],
        "output": html,
        "artifact": {
            "task_id": f"feature_{feature_kind}",
            "display_format": "html",
            "filename": filename,
            "download_url": f"/api/export/{filename}",
            "view_url": f"/api/export/view/{filename}",
        },
    }


def _record_turn_outputs(
    *,
    run_id: str,
    message_id: str,
    user_message: str,
    chat_mode: str,
    session: Dict[str, Any],
    result_state: Dict[str, Any],
    output_html: str,
    export_artifacts: List[Dict[str, Any]],
) -> None:
    context_plan = result_state.get("context_plan", {})
    task_results = result_state.get("task_results", [])
    planner_question = result_state.get("planner_question", user_message)

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
    summary = read_summary(run_id)
    save_memory_summary(run_id, summary)
    record_snapshot(
        run_id=run_id,
        message_id=message_id,
        analysis_goal=context_plan.get("analysis_goal", ""),
        display_format=task_results[-1].get("display_format", "html") if task_results else "html",
    )
    save_turn_payload(run_id, message_id, {
        "run_id": run_id,
        "message_id": message_id,
        "chat_mode": chat_mode,
        "user_message": user_message,
        "planner_question": planner_question,
        "output": output_html,
        "task_results": task_results,
        "export_artifacts": export_artifacts,
        "context_plan": context_plan,
        "worker_results": result_state.get("worker_results", []),
        "saved_at": datetime.utcnow().isoformat(),
    })
    _persist_session(run_id)


def _clean_export_artifacts(export_artifacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clean_artifacts = []
    for art in export_artifacts:
        path = art.get("path", "")
        filename = os.path.basename(path) if path else ""
        clean_artifacts.append({
            "task_id":        art.get("task_id"),
            "display_format": art.get("display_format"),
            "filename":       filename,
            "download_url":   f"/api/export/{filename}" if path else "",
            "view_url":       f"/api/export/view/{filename}" if path else "",
        })
    return clean_artifacts


def _extract_best_output(task_results: List[Dict[str, Any]]) -> str:
    """Pick the best displayable output from task results.

    Priority:
      1. 'action' type tasks (synthesis/unified executor) — these produce the answer text
      2. 'display' type tasks that aren't export tools
      3. Any non-failed output as fallback

    Export tasks (html_export, pdf_export, etc.) return file paths and are
    served as downloadable artifacts — they should NOT be used as inline output.
    """
    EXPORT_TOOL_NAMES = {"task_html_export", "task_ppt_export", "task_pdf_export", "task_word_export"}

    # First pass: find action/synthesis task output
    for tr in task_results:
        out = tr.get("output", "")
        if not out or (out.startswith("<!-- Task") and "failed" in out):
            continue
        tool_name = tr.get("tool_name", "")
        if tool_name in EXPORT_TOOL_NAMES:
            continue
        if tr.get("type") == "action" or tool_name in ("task_unified_executor", "direct_response"):
            return out

    # Second pass: any non-export, non-failed output
    for tr in task_results:
        out = tr.get("output", "")
        if not out or (out.startswith("<!-- Task") and "failed" in out):
            continue
        tool_name = tr.get("tool_name", "")
        if tool_name in EXPORT_TOOL_NAMES:
            continue
        return out

    # Last resort: first non-empty output
    for tr in task_results:
        out = tr.get("output", "")
        if out and not (out.startswith("<!-- Task") and "failed" in out):
            return out

    return ""


def _normalize_render_output(output: str) -> str:
    """
    If a task accidentally returns an HTML file path instead of inline HTML,
    load the file so the frontend can render it.
    """
    if not output:
        return output

    candidate = output.strip()
    if not candidate.lower().endswith(".html"):
        return output

    if not os.path.isabs(candidate):
        return output

    if not os.path.exists(candidate):
        return output

    try:
        with open(candidate, "r", encoding="utf-8", errors="replace") as handle:
            contents = handle.read()
        if "<html" in contents.lower():
            return contents
    except Exception as exc:
        logger.warning(f"Failed to normalize HTML render output from {candidate}: {exc}")

    return output


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


# ── SSE helper ────────────────────────────────────────────────────────────────
def _sse_event(event: str, data: Any) -> str:
    """Format a Server-Sent Event string."""
    payload = json.dumps(data) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {payload}\n\n"


# ═══════════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Redirect to the Next.js frontend."""
    return redirect(os.getenv("NEXT_UI_URL", "http://127.0.0.1:3001"), code=302)


@app.route("/api/session/new", methods=["POST"])
def new_session():
    """Create a new session and return its run_id."""
    run_id = uuid.uuid4().hex
    _get_or_create_session(run_id)
    _persist_session(run_id)
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

    _persist_session(run_id)
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
    _persist_session(run_id)

    return jsonify({"file_id": file_meta["file_id"], "chars": file_meta.get("num_chars", 0)})


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """
    SSE streaming chat endpoint. Runs the full LangGraph pipeline and
    emits progress events as each stage completes.

    Request JSON:
        run_id: str
        message: str
        message_id: str (optional)
        chat_mode: str (auto/direct/thinking/react)
        web_search: bool

    Response: text/event-stream with SSE events:
        augmentor_start  — query classification begun
        retrieval_plan   — context plan ready
        worker_progress  — per-worker extraction status
        checklist_init   — pipeline checklist (dynamic)
        task_progress    — task updates
        synthesis_start  — final synthesis begun
        token_stream     — real-time tokens (future)
        final_response   — complete rendered output + exports
        error            — error if pipeline fails
    """
    data = request.get_json()
    run_id = data.get("run_id", uuid.uuid4().hex)
    user_message = data.get("message", "").strip()
    message_id = data.get("message_id", uuid.uuid4().hex)
    chat_mode = data.get("chat_mode", "auto")
    web_search_enabled = data.get("web_search", False)

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    session = _get_or_create_session(run_id)
    session["messages"].append(HumanMessage(content=user_message))
    _persist_session(run_id)

    def generate():
        try:
            # Build AgentState
            state: AgentState = {
                "messages":        session["messages"],
                "available_files": session["available_files"],
                "chat_mode":       chat_mode,
                "metadata": {
                    **session["metadata"],
                    "message_id": message_id,
                    "user_id":    data.get("user_id", "anonymous"),
                    "web_search_enabled": web_search_enabled,
                    "chat_mode": chat_mode,
                },
            }

            def emit(event_name: str, payload: Dict[str, Any]) -> str:
                append_langgraph_event(run_id, event_name, payload)
                return _sse_event(event_name, payload)

            result_state: Dict[str, Any] = dict(state)

            if chat_mode == "react":
                yield emit("checklist_init", {
                    "steps": [
                        {"id": "augmentor", "label": "Query Analysis", "status": "pending"},
                        {"id": "planner", "label": "Context Planning", "status": "pending"},
                        {"id": "workers", "label": "Document Extraction", "status": "pending"},
                        {"id": "tasks", "label": "Synthesis & Delivery", "status": "pending"},
                    ]
                })
            elif chat_mode in ("direct", "thinking"):
                yield emit("checklist_init", {
                    "steps": [
                        {"id": "augmentor", "label": "Query Analysis", "status": "pending"},
                        {"id": "direct", "label": "Generating Response", "status": "pending"},
                    ]
                })

            augmentor_output = query_augmentor_node(result_state)
            result_state.update(augmentor_output)
            yield emit("augmentor_start", {
                "intent": result_state.get("augmentor_payload", {}).get("query_intent", "unknown"),
                "aim": result_state.get("augmentor_payload", {}).get("aim", ""),
            })

            next_route = route_after_augmentor(result_state)

            if next_route == "direct_response":
                if chat_mode == "auto":
                    yield emit("checklist_init", {
                        "steps": [
                            {"id": "augmentor", "label": "Query Analysis", "status": "done"},
                            {"id": "direct", "label": "Generating Response", "status": "active"},
                        ]
                    })

                yield emit("synthesis_start", {"mode": chat_mode})
                system_prompt, prompt_payload = build_direct_response_request(result_state)
                chunks: List[str] = []
                for delta in llm_handler.call_stream(
                    task_type="synthesis",
                    system_prompt=system_prompt,
                    user_content=prompt_payload,
                    temperature=0.2,
                    max_tokens=16000,
                ):
                    chunks.append(delta)
                    yield emit("token_stream", {"delta": delta})

                response = "".join(chunks)
                result_state.update({
                    "direct_response": response,
                    "task_results": [{
                        "task_id": "direct_response",
                        "type": "display",
                        "tool_name": "direct_response",
                        "display_format": "html",
                        "output": response,
                    }],
                    "export_artifacts": [],
                })
            else:
                if chat_mode == "auto":
                    yield emit("checklist_init", {
                        "steps": [
                            {"id": "augmentor", "label": "Query Analysis", "status": "done"},
                            {"id": "planner", "label": "Context Planning", "status": "active"},
                            {"id": "workers", "label": "Document Extraction", "status": "pending"},
                            {"id": "tasks", "label": "Synthesis & Delivery", "status": "pending"},
                        ]
                    })

                planner_output = context_planner_node(result_state)
                result_state.update(planner_output)
                plan = result_state.get("context_plan", {})
                yield emit("retrieval_plan", {
                    "num_workers": len(plan.get("workers", [])),
                    "num_tasks": len(plan.get("tasks", [])),
                    "analysis_goal": plan.get("analysis_goal", ""),
                })

                planner_route = route_after_planner(result_state)
                if planner_route == "worker_executor":
                    worker_output = worker_tool_executor_node(result_state)
                    result_state.update(worker_output)
                    yield emit("worker_progress", {
                        "completed": len(result_state.get("worker_results", [])),
                        "total": len(result_state.get("context_plan", {}).get("workers", [])),
                    })

                task_output = task_executor_node(result_state)
                result_state.update(task_output)
                yield emit("synthesis_start", {
                    "num_tasks": len(result_state.get("task_results", [])),
                })

            task_results: List[Dict[str, Any]] = result_state.get("task_results", [])
            export_artifacts: List[Dict[str, Any]] = result_state.get("export_artifacts", [])
            output_html = _normalize_render_output(_extract_best_output(task_results))

            session["messages"].append(AIMessage(content=output_html))
            clean_artifacts = _clean_export_artifacts(export_artifacts)
            _record_turn_outputs(
                run_id=run_id,
                message_id=message_id,
                user_message=user_message,
                chat_mode=chat_mode,
                session=session,
                result_state=result_state,
                output_html=output_html,
                export_artifacts=clean_artifacts,
            )

            yield emit("final_response", {
                "run_id":           run_id,
                "message_id":       message_id,
                "output":           output_html,
                "export_artifacts": clean_artifacts,
                "task_results":     [
                    {"task_id": tr["task_id"], "type": tr["type"], "display_format": tr.get("display_format")}
                    for tr in task_results
                ],
                "chat_mode": chat_mode,
            })

        except Exception as e:
            logger.error(f"SSE stream failed: {e}", exc_info=True)
            append_langgraph_event(run_id, "error", {"message": str(e)})
            yield _sse_event("error", {"message": str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Synchronous chat endpoint (backwards compatible).
    Runs the full LangGraph pipeline.

    Request JSON:
        run_id: str
        message: str
        message_id: str (optional)
        chat_mode: str (auto/direct/thinking/react)
        web_search: bool

    Response JSON:
        output: str
        export_artifacts: list
        task_results: list
        run_id: str
        message_id: str
    """
    data = request.get_json()
    run_id = data.get("run_id", uuid.uuid4().hex)
    user_message = data.get("message", "").strip()
    message_id = data.get("message_id", uuid.uuid4().hex)
    chat_mode = data.get("chat_mode", "auto")
    web_search_enabled = data.get("web_search", False)

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    session = _get_or_create_session(run_id)
    session["messages"].append(HumanMessage(content=user_message))
    _persist_session(run_id)

    # Build AgentState
    state: AgentState = {
        "messages":        session["messages"],
        "available_files": session["available_files"],
        "chat_mode":       chat_mode,
        "metadata": {
            **session["metadata"],
            "message_id": message_id,
            "user_id":    data.get("user_id", "anonymous"),
            "web_search_enabled": web_search_enabled,
            "chat_mode": chat_mode,
        },
    }

    # Optional Langfuse tracing
    callbacks = []
    lf = _get_langfuse_callback()
    if lf:
        callbacks.append(lf)

    try:
        result_state: Dict[str, Any] = dict(state)
        result_state.update(query_augmentor_node(result_state))

        if route_after_augmentor(result_state) == "direct_response":
            system_prompt, prompt_payload = build_direct_response_request(result_state)
            response = llm_handler.call(
                task_type="synthesis",
                system_prompt=system_prompt,
                user_content=prompt_payload,
                temperature=0.2,
                max_tokens=16000,
            )
            result_state.update({
                "direct_response": response,
                "task_results": [{
                    "task_id": "direct_response",
                    "type": "display",
                    "tool_name": "direct_response",
                    "display_format": "html",
                    "output": response,
                }],
                "export_artifacts": [],
            })
        else:
            result_state.update(context_planner_node(result_state))
            if route_after_planner(result_state) == "worker_executor":
                result_state.update(worker_tool_executor_node(result_state))
            result_state.update(task_executor_node(result_state))
    except Exception as e:
        logger.error(f"Graph invocation failed: {e}", exc_info=True)
        append_langgraph_event(run_id, "error", {"message": str(e)})
        return jsonify({"error": str(e)}), 500

    # Extract outputs
    task_results: List[Dict] = result_state.get("task_results", [])
    export_artifacts: List[Dict] = result_state.get("export_artifacts", [])

    output_html = _normalize_render_output(_extract_best_output(task_results))

    # Append AI response to conversation history
    session["messages"].append(AIMessage(content=output_html))
    clean_artifacts = _clean_export_artifacts(export_artifacts)
    _record_turn_outputs(
        run_id=run_id,
        message_id=message_id,
        user_message=user_message,
        chat_mode=chat_mode,
        session=session,
        result_state=result_state,
        output_html=output_html,
        export_artifacts=clean_artifacts,
    )

    return jsonify({
        "run_id":           run_id,
        "message_id":       message_id,
        "output":           output_html,
        "export_artifacts": clean_artifacts,
        "task_results":     [
            {"task_id": tr["task_id"], "type": tr["type"], "display_format": tr.get("display_format")}
            for tr in task_results
        ],
        "chat_mode": chat_mode,
    })


@app.route("/api/export/<filename>", methods=["GET"])
def download_export(filename: str):
    """Serve an exported file (PDF, PPT, Word, HTML) for download."""
    export_dir = EXPORT_DIR
    file_path = os.path.join(export_dir, filename)

    # Security: ensure path is inside export_dir
    if not os.path.abspath(file_path).startswith(export_dir):
        return jsonify({"error": "Invalid path"}), 403

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    return send_file(file_path, as_attachment=True)


@app.route("/api/export/view/<filename>", methods=["GET"])
def view_export(filename: str):
    """Serve an exported file inline for preview panels."""
    export_dir = EXPORT_DIR
    file_path = os.path.join(export_dir, filename)

    if not os.path.abspath(file_path).startswith(export_dir):
        return jsonify({"error": "Invalid path"}), 403

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    return send_file(file_path, as_attachment=False)


@app.route("/api/session/<run_id>/files", methods=["GET"])
def get_session_files(run_id: str):
    """Return the file catalog for a session."""
    session = _SESSIONS.get(run_id, {})
    files = session.get("available_files", [])
    return jsonify([
        {"file_id": f["file_id"], "name": f["name"], "chars": f.get("num_chars", 0)}
        for f in files
    ])


@app.route("/api/session/<run_id>", methods=["GET"])
def get_session(run_id: str):
    """Return a persisted session for UI restore."""
    session = _get_or_create_session(run_id)
    return jsonify({
        "run_id": run_id,
        "metadata": session.get("metadata", {}),
        "available_files": session.get("available_files", []),
        "messages": serialize_messages_for_client(session.get("messages", [])),
    })


@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    """Return saved local sessions for the chat history sidebar."""
    limit = request.args.get("limit", default=50, type=int)
    return jsonify({"sessions": list_saved_sessions(limit=max(1, min(limit, 200)))})


@app.route("/api/session/<run_id>", methods=["DELETE"])
def delete_session(run_id: str):
    """Delete a saved local session and its memory summary."""
    _SESSIONS.pop(run_id, None)
    removed = delete_saved_session(run_id)
    if not removed:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({"ok": True, "run_id": run_id})


@app.route("/api/session/<run_id>/summary", methods=["GET"])
def get_session_summary(run_id: str):
    """Return the compressed conversation summary for a session."""
    return jsonify({"summary": read_summary(run_id)})


@app.route("/api/features/<feature_kind>", methods=["POST"])
def generate_feature(feature_kind: str):
    """Generate a dedicated non-chat feature view such as mind map or information brain."""
    data = request.get_json() or {}
    run_id = data.get("run_id", "").strip()
    if not run_id:
        return jsonify({"error": "Missing run_id"}), 400

    try:
        result = _generate_feature_html(run_id, feature_kind)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.error(f"Feature generation failed for {feature_kind}: {exc}", exc_info=True)
        return jsonify({"error": str(exc)}), 500


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
