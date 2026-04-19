/* ── State ─────────────────────────────────────────────────────────────── */
let runId = null;
let messageCounter = 0;

/* ── DOM refs ──────────────────────────────────────────────────────────── */
const messagesEl    = document.getElementById('messages');
const userInput     = document.getElementById('user-input');
const sendBtn       = document.getElementById('send-btn');
const fileInput     = document.getElementById('file-input');
const dropZone      = document.getElementById('drop-zone');
const fileList      = document.getElementById('file-list');
const sessionDisplay= document.getElementById('session-id-display');
const loadingEl     = document.getElementById('loading');
const loadingMsg    = document.getElementById('loading-msg');
const exportBar     = document.getElementById('export-bar');
const newSessionBtn = document.getElementById('btn-new-session');

/* ── Session ───────────────────────────────────────────────────────────── */
async function initSession() {
  const res = await fetch('/api/session/new', { method: 'POST' });
  const data = await res.json();
  runId = data.run_id;
  sessionDisplay.textContent = runId.slice(0, 12) + '…';
}

newSessionBtn.addEventListener('click', async () => {
  await initSession();
  messagesEl.innerHTML = '';
  fileList.innerHTML = '';
  exportBar.style.display = 'none';
  addMessage('assistant', '🆕 New session started. Upload documents and ask a question.');
});

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

  showLoading('Parsing documents…');
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    // Update file list
    data.files.forEach(f => {
      updateFileItem(f.name, `${(f.chars/1000).toFixed(1)}k chars · ${f.topic}`, 'done');
    });
    addMessage('assistant', `✅ Parsed <strong>${data.files.length}</strong> file(s). Ready to answer questions.`);
  } catch (err) {
    addMessage('assistant', `❌ Upload failed: ${err.message}`);
  } finally {
    hideLoading();
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

/* ── Chat ──────────────────────────────────────────────────────────────── */
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
  showLoading('Analysing documents…');

  const webSearchEnabled = document.getElementById('web-search-toggle')?.checked || false;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId, message: text, message_id: msgId, web_search: webSearchEnabled }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    // Render output
    const output = data.output || '';
    if (output.trim().startsWith('<') && output.includes('</')) {
      // HTML output — render in iframe sandbox
      addMessageIframe('assistant', output);
    } else {
      addMessage('assistant', output || '(No output)');
    }

    // Show export buttons
    if (data.export_artifacts && data.export_artifacts.length > 0) {
      showExports(data.export_artifacts);
    }

  } catch (err) {
    addMessage('assistant', `❌ Error: ${err.message}`);
  } finally {
    hideLoading();
    sendBtn.disabled = false;
    userInput.focus();
  }
}

function addMessage(role, html) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.innerHTML = `<div class="message-content">${html}</div>`;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function addMessageIframe(role, html) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  const iframe = document.createElement('iframe');
  iframe.style.cssText = 'width:100%;height:500px;border:1px solid #2d3155;border-radius:8px;margin-top:8px;';
  iframe.sandbox = 'allow-scripts allow-same-origin';
  div.innerHTML = `<div class="message-content" style="max-width:90%"><p>📄 Report generated:</p></div>`;
  div.querySelector('.message-content').appendChild(iframe);
  messagesEl.appendChild(div);
  iframe.srcdoc = html;
  scrollToBottom();
}

function showExports(artifacts) {
  exportBar.innerHTML = '<span style="color:#8892aa;font-size:.78rem;">Downloads: </span>';
  artifacts.forEach(art => {
    if (!art.download_url) return;
    const a = document.createElement('a');
    a.href = art.download_url;
    a.className = 'export-btn';
    a.download = art.filename || 'export';
    a.textContent = `⬇ ${art.display_format || art.filename}`;
    exportBar.appendChild(a);
  });
  exportBar.style.display = 'flex';
}

/* ── Helpers ───────────────────────────────────────────────────────────── */
function scrollToBottom() {
  const container = document.getElementById('chat-container');
  container.scrollTop = container.scrollHeight;
}

function showLoading(msg) { loadingMsg.textContent = msg; loadingEl.style.display = 'flex'; }
function hideLoading() { loadingEl.style.display = 'none'; }

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

/* ── Init ──────────────────────────────────────────────────────────────── */
initSession();
