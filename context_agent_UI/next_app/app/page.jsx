"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const FEATURE_ONLY_ACTIONS = new Set(["mind-map", "information-brain", "brainstorm"]);

const FEATURE_LABELS = {
  "mind-map": "Mind Map",
  "information-brain": "Information Brain",
  brainstorm: "Brainstorm",
  powerpoint: "PowerPoint",
  pdf: "Export PDF",
  word: "Export Word",
};

function makeMessage(role, content, kind = "text") {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content,
    kind,
  };
}

function looksLikeRenderableHtml(content) {
  const stripped = String(content || "").replace(/<!--[\s\S]*?-->/g, "").trim();
  if (!stripped) return false;
  if (/<!doctype html/i.test(stripped)) return true;
  if (/<html[\s>]/i.test(stripped) || /<body[\s>]/i.test(stripped) || /<head[\s>]/i.test(stripped)) return true;
  return /<(div|section|article|main|table|h1|h2|h3|p|ul|ol|li|style)\b/i.test(stripped) && /<\/[a-z]+>/i.test(stripped);
}

function formatHistoryMeta(session) {
  const stamp = session.updated_at ? new Date(session.updated_at).toLocaleString() : "Unknown time";
  return `${session.message_count || 0} msgs · ${session.file_count || 0} files · ${stamp}`;
}

function buildPresetPrompt(preset, latestAssistantOutput) {
  const latest = latestAssistantOutput
    ? `Use the latest analysis in this conversation as the primary source.\n\nLatest analysis:\n${latestAssistantOutput.slice(0, 5000)}\n\n`
    : "";

  switch (preset) {
    case "powerpoint":
      return `${latest}Convert the latest analysis into a polished PowerPoint deck with a title slide, executive summary, information brain, mind map, and brainstorm slide.`;
    case "pdf":
      return `${latest}Convert the latest analysis into a polished PDF report with executive summary, information brain, mind map, and brainstorm recommendations.`;
    case "word":
      return `${latest}Convert the latest analysis into a polished Word document with executive summary, information brain, mind map outline, and brainstorm recommendations.`;
    default:
      return "";
  }
}

export default function Page() {
  const [runId, setRunId] = useState(null);
  const [messages, setMessages] = useState([
    makeMessage("assistant", "Welcome! Upload documents, ask a question, then open a feature view or export from the latest answer."),
  ]);
  const [history, setHistory] = useState([]);
  const [files, setFiles] = useState([]);
  const [chatMode, setChatMode] = useState("auto");
  const [webSearch, setWebSearch] = useState(true);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [thinkingLabel, setThinkingLabel] = useState("");
  const [thinkingSteps, setThinkingSteps] = useState([]);
  const [streamingOutput, setStreamingOutput] = useState("");
  const [lastAssistantOutput, setLastAssistantOutput] = useState("");
  const [exportArtifacts, setExportArtifacts] = useState([]);
  const [preview, setPreview] = useState({ open: false, title: "Rendered output", html: "", url: "" });
  const [loadingFeature, setLoadingFeature] = useState("");
  const [booted, setBooted] = useState(false);

  const chatContainerRef = useRef(null);
  const messageCounter = useRef(0);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, streamingOutput, thinkingLabel, thinkingSteps]);

  async function refreshHistory() {
    try {
      const res = await fetch("/api/sessions?limit=50");
      const data = await res.json();
      setHistory(data.sessions || []);
    } catch {
      setHistory([]);
    }
  }

  async function createSession() {
    const res = await fetch("/api/session/new", { method: "POST" });
    const data = await res.json();
    localStorage.setItem("document-agent-run-id", data.run_id);
    setRunId(data.run_id);
    return data.run_id;
  }

  async function restoreOrCreateSession() {
    const savedRunId = typeof window !== "undefined" ? localStorage.getItem("document-agent-run-id") : null;

    if (savedRunId) {
      const res = await fetch(`/api/session/${savedRunId}`);
      if (res.ok) {
        const data = await res.json();
        setRunId(data.run_id);
        setFiles(data.available_files || []);
        const restoredMessages = (data.messages || []).length
          ? data.messages.map((message) => {
              if (message.role === "assistant" && looksLikeRenderableHtml(message.content || "")) {
                return makeMessage("assistant", message.content, "rendered");
              }
              return makeMessage(message.role === "user" ? "user" : "assistant", message.content || "", "text");
            })
          : [makeMessage("assistant", "This session is ready. Upload documents or continue from here.")];
        setMessages(restoredMessages);
        const latestAssistant = [...(data.messages || [])]
          .reverse()
          .find((message) => message.role === "assistant");
        setLastAssistantOutput(latestAssistant?.content || "");
        await refreshHistory();
        setBooted(true);
        return;
      }
    }

    await createSession();
    await refreshHistory();
    setBooted(true);
  }

  useEffect(() => {
    restoreOrCreateSession();
  }, []);

  function openHtmlPreview(html, title = "HTML Preview") {
    setPreview({ open: true, title, html, url: "" });
  }

  function openFilePreview(url, title = "Document Preview") {
    setPreview({ open: true, title, html: "", url });
  }

  function closePreview() {
    setPreview((current) => ({ ...current, open: false }));
  }

  function addTextMessage(role, content) {
    setMessages((current) => [...current, makeMessage(role, content)]);
  }

  function addRenderedMessage(html, title = "Rendered HTML") {
    setMessages((current) => [...current, { ...makeMessage("assistant", html, "rendered"), title }]);
  }

  function resetWorkingState() {
    setThinkingLabel("");
    setThinkingSteps([]);
    setStreamingOutput("");
  }

  function showExports(artifacts) {
    setExportArtifacts(artifacts || []);
  }

  async function handleNewSession() {
    const newRunId = await createSession();
    setFiles([]);
    setExportArtifacts([]);
    setLastAssistantOutput("");
    setPreview({ open: false, title: "Rendered output", html: "", url: "" });
    resetWorkingState();
    setMessages([makeMessage("assistant", "New session started. Upload documents and ask a question.")]);
    await refreshHistory();
    return newRunId;
  }

  async function handleDeleteSession(targetRunId) {
    if (!window.confirm("Delete this saved chat from local storage?")) return;
    const res = await fetch(`/api/session/${targetRunId}`, { method: "DELETE" });
    if (!res.ok) return;

    if (targetRunId === runId) {
      localStorage.removeItem("document-agent-run-id");
      await handleNewSession();
      return;
    }

    await refreshHistory();
  }

  async function handleOpenSession(targetRunId) {
    const res = await fetch(`/api/session/${targetRunId}`);
    if (!res.ok) return;
    const data = await res.json();
    localStorage.setItem("document-agent-run-id", data.run_id);
    setRunId(data.run_id);
    setFiles(data.available_files || []);
    setExportArtifacts([]);
    setPreview({ open: false, title: "Rendered output", html: "", url: "" });
    resetWorkingState();
    const restoredMessages = (data.messages || []).length
      ? data.messages.map((message) => {
          if (message.role === "assistant" && looksLikeRenderableHtml(message.content || "")) {
            return makeMessage("assistant", message.content, "rendered");
          }
          return makeMessage(message.role === "user" ? "user" : "assistant", message.content || "", "text");
        })
      : [makeMessage("assistant", "This session does not have any saved messages yet.")];
    setMessages(restoredMessages);
    const latestAssistant = [...(data.messages || [])].reverse().find((message) => message.role === "assistant");
    setLastAssistantOutput(latestAssistant?.content || "");
    await refreshHistory();
  }

  async function handleFiles(fileList) {
    const selected = Array.from(fileList || []);
    if (!selected.length) return;

    let activeRunId = runId;
    if (!activeRunId) {
      activeRunId = await createSession();
    }

    const optimistic = selected.map((file) => ({
      name: file.name,
      num_chars: 0,
      topic_hint: "Uploading…",
      __optimistic: true,
    }));
    setFiles((current) => [...current, ...optimistic]);

    const formData = new FormData();
    formData.append("run_id", activeRunId);
    selected.forEach((file) => formData.append("files", file));

    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setFiles((current) => [
        ...current.filter((file) => !file.__optimistic),
        ...(data.files || []).map((file) => ({
          name: file.name,
          num_chars: file.chars,
          topic_hint: file.topic,
        })),
      ]);
      addTextMessage("assistant", `Parsed ${data.files.length} file(s). Ready to answer questions.`);
      await refreshHistory();
    } catch (error) {
      setFiles((current) => current.filter((file) => !file.__optimistic));
      addTextMessage("assistant", `Upload failed: ${error.message}`);
    }
  }

  function updateThinkingStep(label, status, detail = "") {
    setThinkingSteps((current) => {
      const existing = current.filter((step) => step.label !== label);
      return [...existing, { label, status, detail }];
    });
  }

  async function sendMessageWithText(text) {
    if (!text.trim() || isSending) return;

    let activeRunId = runId;
    if (!activeRunId) {
      activeRunId = await createSession();
    }

    setIsSending(true);
    setExportArtifacts([]);
    setMessages((current) => [...current, makeMessage("user", text)]);
    setInput("");
    setThinkingLabel("Thinking…");
    setThinkingSteps([]);
    setStreamingOutput("");

    const messageId = `msg_${++messageCounter.current}_${Date.now()}`;
    const body = JSON.stringify({
      run_id: activeRunId,
      message: text,
      message_id: messageId,
      chat_mode: chatMode,
      web_search: webSearch,
    });

    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || `HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ") && currentEvent) {
            const payload = JSON.parse(line.slice(6));

            switch (currentEvent) {
              case "checklist_init":
                setThinkingSteps((payload.steps || []).map((step) => ({ label: step.label, status: step.status, detail: "" })));
                break;
              case "augmentor_start":
                setThinkingLabel("Analyzing query…");
                updateThinkingStep("Query Analysis", "done", payload.aim ? payload.aim.slice(0, 80) : "");
                break;
              case "retrieval_plan":
                setThinkingLabel(`Extracting from ${payload.num_workers} chunks…`);
                setThinkingSteps([
                  { label: "Query Analysis", status: "done", detail: "" },
                  { label: "Context Planning", status: "done", detail: `${payload.num_workers} workers, ${payload.num_tasks} tasks` },
                  { label: "Document Extraction", status: "active", detail: "" },
                ]);
                break;
              case "worker_progress":
                setThinkingLabel(`Extracted ${payload.completed}/${payload.total} chunks…`);
                if (payload.completed >= payload.total) {
                  setThinkingSteps([
                    { label: "Query Analysis", status: "done", detail: "" },
                    { label: "Context Planning", status: "done", detail: "" },
                    { label: "Document Extraction", status: "done", detail: `${payload.completed} chunks extracted` },
                    { label: "Synthesis & Delivery", status: "active", detail: "" },
                  ]);
                }
                break;
              case "synthesis_start":
                setThinkingLabel("Synthesizing response…");
                break;
              case "token_stream":
                setStreamingOutput((current) => current + (payload.delta || ""));
                break;
              case "final_response": {
                const output = payload.output || "";
                setLastAssistantOutput(output);
                if (looksLikeRenderableHtml(output)) {
                  addRenderedMessage(output, "Rendered HTML");
                  openHtmlPreview(output, "Rendered HTML");
                } else {
                  addTextMessage("assistant", output || "(No output)");
                }
                showExports(payload.export_artifacts || []);
                resetWorkingState();
                await refreshHistory();
                break;
              }
              case "error":
                addTextMessage("assistant", `Pipeline error: ${payload.message}`);
                resetWorkingState();
                break;
              default:
                break;
            }

            currentEvent = null;
          }
        }
      }
    } catch (error) {
      addTextMessage("assistant", `Error: ${error.message}`);
      resetWorkingState();
    } finally {
      setIsSending(false);
    }
  }

  async function triggerFeatureAction(featureKind) {
    let activeRunId = runId;
    if (!activeRunId) {
      activeRunId = await createSession();
    }

    setLoadingFeature(featureKind);
    openHtmlPreview(
      `<html><body style="margin:0;font-family:Inter,Arial,sans-serif;background:#fffdf8;color:#1d1a16;display:grid;place-items:center;min-height:100vh"><div style="padding:28px;border:1px solid rgba(73,61,43,.14);border-radius:20px;max-width:540px"><h1 style="margin:0 0 10px;font-size:1.1rem">${FEATURE_LABELS[featureKind]}</h1><p style="margin:0;color:#6e655a;line-height:1.6">Building a dedicated feature view from the current session context.</p></div></body></html>`,
      FEATURE_LABELS[featureKind]
    );

    try {
      const res = await fetch(`/api/features/${featureKind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: activeRunId }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || "Feature generation failed");
      if (data.output) openHtmlPreview(data.output, data.title || FEATURE_LABELS[featureKind]);
      if (data.artifact) showExports([data.artifact]);
      await refreshHistory();
    } catch (error) {
      openHtmlPreview(
        `<html><body style="margin:0;font-family:Inter,Arial,sans-serif;background:#fffaf7;color:#1d1a16;padding:32px"><div style="border:1px solid rgba(178,61,47,.18);background:#fff4f1;border-radius:18px;padding:20px;max-width:640px"><h1 style="margin:0 0 10px;font-size:1.1rem">${FEATURE_LABELS[featureKind]} failed</h1><p style="margin:0;color:#7a4a41;line-height:1.6">${error.message}</p></div></body></html>`,
        `${FEATURE_LABELS[featureKind]} error`
      );
    } finally {
      setLoadingFeature("");
    }
  }

  async function handleAction(preset) {
    if (FEATURE_ONLY_ACTIONS.has(preset)) {
      await triggerFeatureAction(preset);
      return;
    }

    const prompt = buildPresetPrompt(preset, lastAssistantOutput);
    if (prompt) {
      await sendMessageWithText(prompt);
    }
  }

  const activeHistory = useMemo(() => new Set([runId]), [runId]);

  if (!booted) {
    return <main className="boot">Loading Document Agent…</main>;
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-card">
          <div>
            <p className="eyebrow">Workspace</p>
            <h1>Document Agent</h1>
          </div>
          <button className="icon-btn" onClick={handleNewSession}>+</button>
        </div>

        <section className="panel">
          <p className="panel-label">Upload Documents</p>
          <label className="upload-card">
            <input
              type="file"
              multiple
              className="hidden-input"
              accept=".pdf,.pptx,.docx,.xlsx,.csv,.txt,.md,.html,.json,.xml,.png,.jpg,.mp3,.mp4,.zip"
              onChange={(event) => handleFiles(event.target.files)}
            />
            <span>Drop files or click to upload</span>
          </label>
          <div className="file-list">
            {files.length === 0 ? (
              <p className="muted">No files in this session yet.</p>
            ) : (
              files.map((file, index) => (
                <div className="file-item" key={`${file.name}-${index}`}>
                  <strong>{file.name}</strong>
                  <span>{((file.num_chars || file.chars || 0) / 1000).toFixed(1)}k chars · {file.topic_hint || file.topic || "Ready"}</span>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="panel">
          <p className="panel-label">Session</p>
          <code className="session-id">{runId || "No session"}</code>
        </section>

        <section className="panel history-panel">
          <p className="panel-label">Chat History</p>
          <div className="history-list">
            {history.length === 0 ? (
              <p className="muted">No saved chats yet.</p>
            ) : (
              history.map((session) => (
                <div className={`history-item ${activeHistory.has(session.run_id) ? "active" : ""}`} key={session.run_id}>
                  <button className="history-open" onClick={() => handleOpenSession(session.run_id)}>
                    <strong>{session.preview || "Untitled chat"}</strong>
                    <span>{formatHistoryMeta(session)}</span>
                  </button>
                  <button className="history-delete" onClick={() => handleDeleteSession(session.run_id)}>Delete</button>
                </div>
              ))
            )}
          </div>
        </section>
      </aside>

      <section className={`workspace ${preview.open ? "preview-open" : ""}`}>
        <div className="conversation">
          <header className="hero">
            <div>
              <p className="eyebrow">Research Workbench</p>
              <h2>Ask, analyze, and turn the result into something usable.</h2>
              <p className="hero-copy">
                The new React workspace keeps your active session stable across refreshes and gives generated documents their own preview area.
              </p>
            </div>
            <div className="hero-chips">
              <span>Persistent local history</span>
              <span>Streaming answers</span>
              <span>Feature views + exports</span>
            </div>
          </header>

          <div className="chat-feed" ref={chatContainerRef}>
            {messages.map((message) => (
              <div className={`message ${message.role}`} key={message.id}>
                <div className="message-bubble">
                  {message.kind === "rendered" ? (
                    <div className="render-card">
                      <strong>{message.title || "Rendered document"}</strong>
                      <p>This result was generated as a document view. Open it in the preview pane.</p>
                      <button onClick={() => openHtmlPreview(message.content, message.title || "Rendered HTML")}>Open Preview</button>
                    </div>
                  ) : (
                    <p>{message.content}</p>
                  )}
                </div>
              </div>
            ))}

            {(thinkingLabel || streamingOutput) && (
              <div className="message assistant">
                <div className="message-bubble thinking">
                  {thinkingLabel ? <strong>{thinkingLabel}</strong> : null}
                  {thinkingSteps.length ? (
                    <ul className="thinking-list">
                      {thinkingSteps.map((step) => (
                        <li key={step.label}>
                          <span>{step.label}</span>
                          <small>{step.status}{step.detail ? ` · ${step.detail}` : ""}</small>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {streamingOutput ? <p className="streaming-output">{streamingOutput}</p> : null}
                </div>
              </div>
            )}
          </div>

          <div className="composer-wrap">
            <div className="exports">
              {exportArtifacts.length ? (
                exportArtifacts.map((artifact) => (
                  <button
                    key={artifact.filename}
                    className="export-chip"
                    onClick={() => {
                      const isPreviewable = (artifact.filename || "").toLowerCase().endsWith(".html") || (artifact.filename || "").toLowerCase().endsWith(".pdf");
                      if (isPreviewable) {
                        openFilePreview(artifact.view_url || artifact.download_url, artifact.filename || artifact.display_format || "Preview");
                      } else {
                        window.open(artifact.download_url, "_blank", "noopener,noreferrer");
                      }
                    }}
                  >
                    {artifact.display_format || artifact.filename}
                  </button>
                ))
              ) : (
                <span className="muted">Generated downloads will appear here.</span>
              )}
            </div>

            <div className="action-strip">
              {["mind-map", "information-brain", "brainstorm", "powerpoint", "pdf", "word"].map((preset) => (
                <button
                  key={preset}
                  className="action-btn"
                  disabled={isSending || loadingFeature === preset}
                  onClick={() => handleAction(preset)}
                >
                  {loadingFeature === preset ? "Generating…" : FEATURE_LABELS[preset]}
                </button>
              ))}
            </div>

            <div className="composer">
              <div className="composer-controls">
                <label>
                  <span>Mode</span>
                  <select value={chatMode} onChange={(event) => setChatMode(event.target.value)}>
                    <option value="auto">Auto</option>
                    <option value="direct">Direct</option>
                    <option value="thinking">Thinking</option>
                    <option value="react">ReAct</option>
                  </select>
                </label>
                <label className="checkbox">
                  <input type="checkbox" checked={webSearch} onChange={(event) => setWebSearch(event.target.checked)} />
                  <span>Web Search</span>
                </label>
              </div>

              <div className="composer-row">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      sendMessageWithText(input);
                    }
                  }}
                  placeholder="Ask about your documents, the web, or the latest answer."
                />
                <button className="send-btn" disabled={isSending || !input.trim()} onClick={() => sendMessageWithText(input)}>
                  Send
                </button>
              </div>
            </div>
          </div>
        </div>

        <aside className={`preview-pane ${preview.open ? "open" : "hidden"}`}>
          <div className="preview-toolbar">
            <div>
              <p className="panel-label">Preview</p>
              <strong>{preview.title}</strong>
            </div>
            <div className="preview-actions">
              {preview.url ? (
                <button onClick={() => window.open(preview.url, "_blank", "noopener,noreferrer")}>Open</button>
              ) : null}
              <button onClick={closePreview}>Close</button>
            </div>
          </div>
          <div className="preview-frame-wrap">
            {preview.open ? (
              <iframe
                key={`${preview.title}-${preview.url ? "url" : "html"}`}
                className="preview-frame"
                src={preview.url || undefined}
                srcDoc={preview.html || undefined}
                sandbox="allow-same-origin allow-scripts"
              />
            ) : (
              <div className="preview-empty">
                <h3>Preview Workspace</h3>
                <p>Generated reports, feature views, HTML, and PDFs open here.</p>
              </div>
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}
