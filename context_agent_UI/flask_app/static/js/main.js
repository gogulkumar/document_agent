/* ── State ─────────────────────────────────────────────────────────────── */
let runId = null;
let messageCounter = 0;
let thinkingEl = null;  // current inline thinking block
let streamingMessageEl = null;
let streamingBuffer = '';
let lastAssistantOutput = '';

/* ── DOM refs ──────────────────────────────────────────────────────────── */
const messagesEl      = document.getElementById('messages');
const userInput       = document.getElementById('user-input');
const sendBtn         = document.getElementById('send-btn');
const fileInput       = document.getElementById('file-input');
const dropZone        = document.getElementById('drop-zone');
const fileList        = document.getElementById('file-list');
const sessionDisplay  = document.getElementById('session-id-display');
const exportBar       = document.getElementById('export-bar');
const newSessionBtn   = document.getElementById('btn-new-session');
const chatModeSelect  = document.getElementById('chat-mode-select');
const historyList     = document.getElementById('history-list');
const previewPanel    = document.getElementById('preview-panel');
const previewFrame    = document.getElementById('preview-frame');
const previewTitle    = document.getElementById('preview-title');
const previewOpenBtn  = document.getElementById('preview-open-btn');
const previewCloseBtn = document.getElementById('preview-close-btn');
const workspaceShell  = document.querySelector('.workspace-shell');
const featureButtons = document.querySelectorAll('.feature-btn');
let previewSourceUrl = '';
let previewSourceHtml = '';

/* ── Session ───────────────────────────────────────────────────────────── */
async function initSession() {
  const res = await fetch('/api/session/new', { method: 'POST' });
  const data = await res.json();
  runId = data.run_id;
  sessionDisplay.textContent = runId.slice(0, 12) + '…';
  localStorage.setItem('document-agent-run-id', runId);
  await refreshHistory();
}

newSessionBtn.addEventListener('click', async () => {
  await initSession();
  messagesEl.innerHTML = '';
  fileList.innerHTML = '';
  exportBar.style.display = 'none';
  lastAssistantOutput = '';
  addMessage('assistant', 'New session started. Upload documents and ask a question.');
});

async function refreshHistory() {
  if (!historyList) return;
  try {
    const res = await fetch('/api/sessions?limit=50');
    if (!res.ok) throw new Error('Failed to load history');
    const data = await res.json();
    renderHistory(data.sessions || []);
  } catch (err) {
    historyList.innerHTML = '<div class="history-empty">Unable to load saved chats.</div>';
  }
}

function formatHistoryMeta(session) {
  const stamp = session.updated_at ? new Date(session.updated_at).toLocaleString() : 'Unknown time';
  return `${session.message_count || 0} msgs · ${session.file_count || 0} files · ${stamp}`;
}

function renderHistory(sessions) {
  if (!historyList) return;
  if (!sessions.length) {
    historyList.innerHTML = '<div class="history-empty">No saved chats yet.</div>';
    return;
  }

  historyList.innerHTML = '';
  sessions.forEach(session => {
    const item = document.createElement('div');
    item.className = `history-item ${session.run_id === runId ? 'active' : ''}`;
    item.innerHTML = `
      <button type="button" class="history-open">
        <div class="history-preview">${escapeHtml(session.preview || 'Untitled chat')}</div>
        <div class="history-meta">${escapeHtml(formatHistoryMeta(session))}</div>
      </button>
      <button type="button" class="history-delete" aria-label="Delete chat">Delete</button>
    `;
    item.querySelector('.history-open')?.addEventListener('click', () => openHistorySession(session.run_id));
    item.querySelector('.history-delete')?.addEventListener('click', (event) => {
      event.stopPropagation();
      deleteHistorySession(session.run_id);
    });
    historyList.appendChild(item);
  });
}

async function deleteHistorySession(targetRunId) {
  const confirmed = window.confirm('Delete this saved chat from local storage?');
  if (!confirmed) return;

  const res = await fetch(`/api/session/${targetRunId}`, { method: 'DELETE' });
  if (!res.ok) return;

  if (targetRunId === runId) {
    localStorage.removeItem('document-agent-run-id');
    runId = null;
    sessionDisplay.textContent = 'No session';
    messagesEl.innerHTML = '';
    fileList.innerHTML = '';
    exportBar.style.display = 'none';
    lastAssistantOutput = '';
    closePreview();
    await initSession();
    addMessage('assistant', 'Chat deleted. A new session is ready.');
  } else {
    await refreshHistory();
  }
}

async function openHistorySession(targetRunId) {
  const res = await fetch(`/api/session/${targetRunId}`);
  if (!res.ok) return;

  const data = await res.json();
  runId = data.run_id;
  localStorage.setItem('document-agent-run-id', runId);
  sessionDisplay.textContent = runId.slice(0, 12) + '…';
  messagesEl.innerHTML = '';
  fileList.innerHTML = '';
  exportBar.style.display = 'none';
  lastAssistantOutput = '';

  (data.available_files || []).forEach(file => {
    addFileItem(file.name, `${((file.num_chars || file.chars || 0)/1000).toFixed(1)}k chars · ${file.topic_hint || file.topic || ''}`, 'done');
  });

  if ((data.messages || []).length === 0) {
    addMessage('assistant', 'This session does not have any saved messages yet.');
  } else {
    data.messages.forEach(message => renderStoredMessage(message.role, message.content));
  }

  await refreshHistory();
}

featureButtons.forEach(button => {
  button.addEventListener('click', async () => {
    const preset = button.dataset.preset || '';
    if (['mind-map', 'information-brain', 'brainstorm'].includes(preset)) {
      await triggerFeatureAction(button, preset);
      return;
    }

    const prompt = buildPresetPrompt(preset);
    if (!prompt) return;
    userInput.value = prompt;
    sendMessage();
  });
});

previewCloseBtn?.addEventListener('click', () => closePreview());
previewOpenBtn?.addEventListener('click', () => {
  if (previewSourceUrl) {
    window.open(previewSourceUrl, '_blank', 'noopener,noreferrer');
  }
});

async function restoreSession() {
  const savedRunId = localStorage.getItem('document-agent-run-id');
  if (!savedRunId) return false;

  const res = await fetch(`/api/session/${savedRunId}`);
  if (!res.ok) return false;

  const data = await res.json();
  runId = data.run_id;
  sessionDisplay.textContent = runId.slice(0, 12) + '…';
  messagesEl.innerHTML = '';
  fileList.innerHTML = '';
  exportBar.style.display = 'none';

  (data.available_files || []).forEach(file => {
    addFileItem(file.name, `${((file.num_chars || file.chars || 0)/1000).toFixed(1)}k chars · ${file.topic_hint || file.topic || ''}`, 'done');
  });

  if ((data.messages || []).length === 0) {
    return false;
  }

  data.messages.forEach(message => renderStoredMessage(message.role, message.content));
  await refreshHistory();
  return true;
}

/* ── File upload ───────────────────────────────────────────────────────── */
fileInput.addEventListener('change', () => handleFiles(fileInput.files));

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  handleFiles(e.dataTransfer.files);
});

async function handleFiles(files) {
  if (!runId) await initSession();
  if (!files || files.length === 0) return;

  const formData = new FormData();
  formData.append('run_id', runId);
  for (const file of files) {
    formData.append('files', file);
    addFileItem(file.name, 'Uploading…', 'uploading');
  }

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    data.files.forEach(f => {
      updateFileItem(f.name, `${(f.chars/1000).toFixed(1)}k chars · ${f.topic}`, 'done');
    });
    addMessage('assistant', `Parsed <strong>${data.files.length}</strong> file(s). Ready to answer questions.`);
    await refreshHistory();
  } catch (err) {
    addMessage('assistant', `Upload failed: ${err.message}`);
  }
}

function addFileItem(name, meta, status) {
  const el = document.createElement('div');
  el.className = `file-item ${status}`;
  el.dataset.filename = name;
  el.innerHTML = `<div class="file-name">${escapeHtml(name)}</div><div class="file-meta">${escapeHtml(meta)}</div>`;
  fileList.appendChild(el);
}

function updateFileItem(name, meta, status) {
  const el = fileList.querySelector(`[data-filename="${CSS.escape(name)}"]`);
  if (el) {
    el.className = `file-item ${status}`;
    el.querySelector('.file-meta').textContent = meta;
  }
}

/* ── Inline thinking ───────────────────────────────────────────────────── */
function startThinking() {
  const wrapper = document.createElement('div');
  wrapper.className = 'message assistant';
  wrapper.innerHTML = `
    <div class="message-content thinking-message">
      <div class="thinking-block">
        <div class="thinking-header" onclick="this.closest('.thinking-block').classList.toggle('collapsed')">
          <div class="thinking-spinner"></div>
          <span class="thinking-label">Thinking…</span>
          <svg class="thinking-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="thinking-steps"></div>
      </div>
    </div>`;
  messagesEl.appendChild(wrapper);
  scrollToBottom();
  thinkingEl = wrapper;
  return wrapper;
}

function addThinkingStep(label, status, detail) {
  if (!thinkingEl) return;
  const stepsEl = thinkingEl.querySelector('.thinking-steps');
  const stepId = label.toLowerCase().replace(/\s+/g, '-');

  let stepEl = stepsEl.querySelector(`[data-step="${stepId}"]`);
  if (!stepEl) {
    stepEl = document.createElement('div');
    stepEl.className = 'thinking-step';
    stepEl.dataset.step = stepId;
    stepsEl.appendChild(stepEl);
  }

  const icon = status === 'done' ? '✓' : status === 'active' ? '◉' : '○';
  const statusClass = status === 'done' ? 'done' : status === 'active' ? 'active' : '';
  stepEl.className = `thinking-step ${statusClass}`;
  stepEl.innerHTML = `<span class="step-icon">${icon}</span><span class="step-label">${escapeHtml(label)}</span>${detail ? `<span class="step-detail"> — ${escapeHtml(detail)}</span>` : ''}`;
  scrollToBottom();
}

function clearThinkingSteps() {
  if (!thinkingEl) return;
  const stepsEl = thinkingEl.querySelector('.thinking-steps');
  if (stepsEl) stepsEl.innerHTML = '';
}

function updateThinkingLabel(text) {
  if (!thinkingEl) return;
  thinkingEl.querySelector('.thinking-label').textContent = text;
}

function finishThinking() {
  if (!thinkingEl) return;
  const spinner = thinkingEl.querySelector('.thinking-spinner');
  if (spinner) spinner.classList.add('done');
  thinkingEl.querySelector('.thinking-label').textContent = 'Thought process';
  thinkingEl.querySelector('.thinking-block').classList.add('collapsed');
  thinkingEl = null;
}

function startStreamingResponse() {
  if (streamingMessageEl) return streamingMessageEl;
  streamingBuffer = '';
  const div = document.createElement('div');
  div.className = 'message assistant';
  div.innerHTML = `<div class="message-content streaming-message"><div class="streaming-output"></div></div>`;
  messagesEl.appendChild(div);
  scrollToBottom();
  streamingMessageEl = div;
  return div;
}

function appendStreamingToken(delta) {
  startStreamingResponse();
  streamingBuffer += delta;
  const output = streamingMessageEl.querySelector('.streaming-output');
  output.innerHTML = escapeHtml(streamingBuffer).replace(/\n/g, '<br>');
  scrollToBottom();
}

function clearStreamingResponse() {
  if (streamingMessageEl) {
    streamingMessageEl.remove();
  }
  streamingMessageEl = null;
  streamingBuffer = '';
}

function openHtmlPreview(html, title = 'HTML Preview') {
  if (!previewPanel || !previewFrame) return;
  previewSourceHtml = html || '';
  previewSourceUrl = '';
  previewTitle.textContent = title;
  previewOpenBtn.textContent = 'Open';
  previewFrame.removeAttribute('src');
  previewFrame.srcdoc = previewSourceHtml;
  previewPanel.classList.remove('hidden');
  workspaceShell?.classList.add('preview-open');
}

function openFilePreview(url, title = 'Document Preview') {
  if (!previewPanel || !previewFrame) return;
  previewSourceUrl = url || '';
  previewSourceHtml = '';
  previewTitle.textContent = title;
  previewOpenBtn.textContent = 'Open';
  previewFrame.removeAttribute('srcdoc');
  previewFrame.src = previewSourceUrl;
  previewPanel.classList.remove('hidden');
  workspaceShell?.classList.add('preview-open');
}

function closePreview() {
  if (!previewPanel || !previewFrame) return;
  previewPanel.classList.add('hidden');
  previewFrame.removeAttribute('src');
  previewFrame.removeAttribute('srcdoc');
  previewSourceUrl = '';
  previewSourceHtml = '';
  workspaceShell?.classList.remove('preview-open');
}

async function triggerFeatureAction(button, featureKind) {
  if (!runId) await initSession();

  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = 'Generating…';

  openHtmlPreview(`
    <html>
      <head>
        <style>
          body {
            margin: 0;
            font-family: "Manrope", sans-serif;
            background: #fffdf8;
            color: #1d1a16;
            display: grid;
            place-items: center;
            min-height: 100vh;
          }
          .status {
            padding: 24px 28px;
            border: 1px solid rgba(73,61,43,0.14);
            border-radius: 20px;
            box-shadow: 0 18px 40px rgba(74,48,19,0.08);
            max-width: 560px;
          }
          h1 { margin: 0 0 10px; font-size: 1.1rem; }
          p { margin: 0; line-height: 1.6; color: #6e655a; }
        </style>
      </head>
      <body>
        <div class="status">
          <h1>${escapeHtml(originalLabel)}</h1>
          <p>Building a dedicated feature view from the latest session context.</p>
        </div>
      </body>
    </html>
  `, originalLabel);

  try {
    const res = await fetch(`/api/features/${featureKind}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId }),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Feature generation failed');

    if (data.output) {
      openHtmlPreview(data.output, data.title || originalLabel);
    }
    if (data.artifact) {
      showExports([data.artifact]);
    }
  } catch (err) {
    openHtmlPreview(`
      <html>
        <head><style>body{font-family:"Manrope",sans-serif;padding:32px;background:#fffaf7;color:#1d1a16} .error{border:1px solid rgba(178,61,47,.18);background:#fff4f1;border-radius:18px;padding:20px;max-width:640px} h1{margin:0 0 10px;font-size:1.1rem} p{margin:0;line-height:1.6;color:#7a4a41}</style></head>
        <body><div class="error"><h1>${escapeHtml(originalLabel)} failed</h1><p>${escapeHtml(err.message || 'Unknown error')}</p></div></body>
      </html>
    `, `${originalLabel} error`);
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

function looksLikeRenderableHtml(content) {
  const stripped = (content || '').replace(/<!--[\s\S]*?-->/g, '').trim();
  if (!stripped) return false;

  if (/<!doctype html/i.test(stripped)) return true;
  if (/<html[\s>]/i.test(stripped) || /<body[\s>]/i.test(stripped) || /<head[\s>]/i.test(stripped)) return true;
  if (/<(div|section|article|main|table|h1|h2|h3|p|ul|ol|li|style)\b/i.test(stripped) && /<\/[a-z]+>/i.test(stripped)) return true;
  return false;
}

function buildPresetPrompt(preset) {
  const latest = lastAssistantOutput
    ? `Use the latest analysis in this conversation as the primary source.\n\nLatest analysis:\n${lastAssistantOutput.slice(0, 5000)}\n\n`
    : '';

  switch (preset) {
    case 'mind-map':
      return `${latest}Create a polished mind map from the latest findings. Cluster related ideas, show what influences what, and keep the output easy to scan.`;
    case 'information-brain':
      return `${latest}Build an information brain that explains how the main themes, evidence, entities, and conclusions connect. Highlight the strongest relationships and tensions.`;
    case 'brainstorm':
      return `${latest}Brainstorm bold next-step ideas from the latest analysis. Organize them by opportunity, risk, and experiment.`;
    case 'powerpoint':
      return `${latest}Convert the latest analysis into a polished PowerPoint deck with a title slide, executive summary, information brain, mind map, and brainstorm slide.`;
    case 'pdf':
      return `${latest}Convert the latest analysis into a polished PDF report with executive summary, information brain, mind map, and brainstorm recommendations.`;
    case 'word':
      return `${latest}Convert the latest analysis into a polished Word document with executive summary, information brain, mind map outline, and brainstorm recommendations.`;
    default:
      return '';
  }
}

/* ── Chat (SSE streaming) ─────────────────────────────────────────────── */
sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || sendBtn.disabled) return;
  if (!runId) await initSession();

  userInput.value = '';
  sendBtn.disabled = true;
  addMessage('user', escapeHtml(text));
  exportBar.style.display = 'none';

  const msgId = `msg_${++messageCounter}_${Date.now()}`;
  const chatMode = chatModeSelect.value;
  const webSearchEnabled = document.getElementById('web-search-toggle')?.checked || false;

  startThinking();

  const body = JSON.stringify({
    run_id: runId,
    message: text,
    message_id: msgId,
    chat_mode: chatMode,
    web_search: webSearchEnabled,
  });

  try {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
    });

    if (!response.ok) {
      const errData = await response.json();
      throw new Error(errData.error || `HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      let eventType = null;
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith('data: ') && eventType) {
          try {
            const data = JSON.parse(line.slice(6));
            handleSSEEvent(eventType, data);
          } catch (e) {
            // non-JSON data, skip
          }
          eventType = null;
        }
      }
    }

  } catch (err) {
    finishThinking();
    addMessage('assistant', `Error: ${err.message}`);
  } finally {
    sendBtn.disabled = false;
    userInput.focus();
  }
}

function handleSSEEvent(event, data) {
  switch (event) {
    case 'checklist_init':
      clearThinkingSteps();
      (data.steps || []).forEach(step => {
        addThinkingStep(step.label, step.status);
      });
      break;

    case 'augmentor_start':
      updateThinkingLabel('Analyzing query…');
      addThinkingStep('Query Analysis', 'done', data.aim ? data.aim.slice(0, 80) : '');
      break;

    case 'retrieval_plan':
      clearThinkingSteps();
      addThinkingStep('Query Analysis', 'done');
      updateThinkingLabel(`Extracting from ${data.num_workers} chunks…`);
      addThinkingStep('Context Planning', 'done', `${data.num_workers} workers, ${data.num_tasks} tasks`);
      addThinkingStep('Document Extraction', 'active');
      break;

    case 'worker_progress':
      updateThinkingLabel(`Extracted ${data.completed}/${data.total} chunks…`);
      if (data.completed >= data.total) {
        addThinkingStep('Document Extraction', 'done', `${data.completed} chunks extracted`);
        addThinkingStep('Synthesis & Delivery', 'active');
      }
      break;

    case 'synthesis_start':
      updateThinkingLabel('Synthesizing response…');
      if (data.mode) {
        addThinkingStep('Generating Response', 'active');
        startStreamingResponse();
      } else {
        addThinkingStep('Synthesis & Delivery', 'active');
      }
      break;

    case 'token_stream':
      appendStreamingToken(data.delta || '');
      break;

    case 'final_response':
      finishThinking();
      clearStreamingResponse();

      const output = data.output || '';
      lastAssistantOutput = output;
      const stripped = output.replace(/<!--[\s\S]*?-->/g, '').trim();
      if (looksLikeRenderableHtml(output)) {
        addMessageIframe('assistant', output);
        openHtmlPreview(output, 'Rendered HTML');
      } else {
        addMessage('assistant', stripped || output || '(No output)');
      }

      if (data.export_artifacts && data.export_artifacts.length > 0) {
        showExports(data.export_artifacts);
      }
      refreshHistory();
      break;

    case 'error':
      finishThinking();
      clearStreamingResponse();
      addMessage('assistant', `Pipeline error: ${data.message}`);
      break;
  }
}

/* ── Fallback: synchronous chat (if SSE fails) ─────────────────────────── */
async function sendMessageSync() {
  const text = userInput.value.trim();
  if (!text || sendBtn.disabled) return;
  if (!runId) await initSession();

  userInput.value = '';
  sendBtn.disabled = true;
  addMessage('user', escapeHtml(text));

  const msgId = `msg_${++messageCounter}_${Date.now()}`;
  const chatMode = chatModeSelect.value;
  const webSearchEnabled = document.getElementById('web-search-toggle')?.checked || false;

  startThinking();
  updateThinkingLabel('Processing…');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        run_id: runId,
        message: text,
        message_id: msgId,
        chat_mode: chatMode,
        web_search: webSearchEnabled,
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    const output = data.output || '';
    lastAssistantOutput = output;
    if (looksLikeRenderableHtml(output)) {
      addMessageIframe('assistant', output);
      openHtmlPreview(output, 'Rendered HTML');
    } else {
      addMessage('assistant', output || '(No output)');
    }

    if (data.export_artifacts && data.export_artifacts.length > 0) {
      showExports(data.export_artifacts);
    }
    refreshHistory();
  } catch (err) {
    finishThinking();
    addMessage('assistant', `Error: ${err.message}`);
  } finally {
    finishThinking();
    sendBtn.disabled = false;
    userInput.focus();
  }
}

/* ── Message rendering ─────────────────────────────────────────────────── */
function addMessage(role, html) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.innerHTML = `<div class="message-content">${html}</div>`;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function renderStoredMessage(role, content) {
  if (role === 'assistant') {
    lastAssistantOutput = content || lastAssistantOutput;
    if (looksLikeRenderableHtml(content || '')) {
      addMessageIframe('assistant', content);
      return;
    }
  }
  addMessage(role === 'user' ? 'user' : 'assistant', role === 'user' ? escapeHtml(content || '') : (content || ''));
}

function addMessageIframe(role, html) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  const iframe = document.createElement('iframe');
  iframe.style.cssText = 'width:100%;height:500px;border:1px solid #2d3155;border-radius:8px;margin-top:8px;';
  iframe.sandbox = 'allow-scripts allow-same-origin';
  div.innerHTML = `<div class="message-content" style="max-width:90%"><p>Report generated:</p></div>`;
  div.querySelector('.message-content').appendChild(iframe);
  messagesEl.appendChild(div);
  iframe.srcdoc = html;
  scrollToBottom();
}

function showExports(artifacts) {
  exportBar.innerHTML = '<span style="color:#8892aa;font-size:.78rem;">Downloads: </span>';
  artifacts.forEach(art => {
    if (!art.download_url) return;
    const viewUrl = art.view_url || art.download_url;
    const a = document.createElement('a');
    a.href = art.download_url;
    a.className = 'export-btn';
    a.download = art.filename || 'export';
    a.textContent = `⬇ ${art.display_format || art.filename}`;
    a.addEventListener('click', (event) => {
      if ((art.display_format || '').includes('pdf') || (art.filename || '').toLowerCase().endsWith('.pdf')) {
        event.preventDefault();
        openFilePreview(viewUrl, art.filename || 'PDF Preview');
      } else if ((art.display_format || '').includes('html') || (art.filename || '').toLowerCase().endsWith('.html')) {
        event.preventDefault();
        openFilePreview(viewUrl, art.filename || 'HTML Preview');
      }
    });
    exportBar.appendChild(a);
  });
  exportBar.style.display = 'flex';
}

/* ── Helpers ───────────────────────────────────────────────────────────── */
function scrollToBottom() {
  const container = document.getElementById('chat-container');
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

/* ── Init ──────────────────────────────────────────────────────────────── */
(async function boot() {
  const restored = await restoreSession();
  if (!restored) {
    await initSession();
  } else {
    await refreshHistory();
  }
})();
