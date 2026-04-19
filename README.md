# Document AI — Notebook Agent

An **Investor Relations research copilot** powered by LangGraph, OpenAI GPT-4.1, and AWS Bedrock Claude Sonnet 4. Upload earnings calls, PDFs, Excel, PPT, or any other document and ask natural-language questions. The agent plans, extracts, synthesises, and exports results as HTML, PDF, PowerPoint, or Word.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Architecture Overview](#architecture-overview)
3. [Tech Stack](#tech-stack)
4. [Project Structure](#project-structure)
5. [Quick Start (Local)](#quick-start-local)
6. [Configuration (.env)](#configuration-env)
7. [Running with Docker](#running-with-docker)
8. [API Reference](#api-reference)
9. [How to Host](#how-to-host)
10. [LLM Routing](#llm-routing)
11. [Supported File Types](#supported-file-types)
12. [Export Formats](#export-formats)
13. [Extending the Agent](#extending-the-agent)
14. [Troubleshooting](#troubleshooting)

---

## What It Does

Given uploaded documents and a natural-language question, the Notebook Agent:

1. **Augments** your question with IR-domain context and a structured execution plan
2. **Plans** which files to read and how, splitting large files into parallel extraction workers
3. **Extracts** relevant snippets from each document chunk, with citations
4. **Synthesises** a high-quality answer using long-context Claude Sonnet 4
5. **Exports** results as HTML report, PDF, PowerPoint, or Word document

The core design principle is **executor isolation** — each node only receives data that the upstream node explicitly provides, eliminating hallucination chains.

---

## Architecture Overview

```
User Question + Uploaded Files
          │
          ▼
┌─────────────────────────────────────────────┐
│              Flask Web UI                   │
│  (upload, chat interface, export downloads) │
└──────────────────┬──────────────────────────┘
                   │  AgentState
                   ▼
┌─────────────────────────────────────────────┐
│           LangGraph StateGraph              │
│                                             │
│  query_augmentor_node  (GPT-4.1, temp=0.2) │
│          │                                  │
│          ▼                                  │
│  context_planner_node  (GPT-4.1, temp=0.1) │
│          │                                  │
│          ▼                                  │
│  worker_tool_executor_node  (parallel)      │
│    ├── worker_1 → file_chunk_1             │
│    ├── worker_2 → file_chunk_2             │
│    └── worker_N → file_chunk_N             │
│          │                                  │
│          ▼                                  │
│  task_executor_node  (topological order)    │
│    ├── action tasks  (Claude Sonnet 4)      │
│    └── display/export tasks                │
└─────────────────────────────────────────────┘
          │
          ▼
   Output: HTML / PDF / PPT / Word + download links
```

### The 4 LangGraph Nodes

| Node | File | LLM | Role |
|---|---|---|---|
| `query_augmentor_node` | `agents/nodes/query_augmentor_node.py` | GPT-4.1, temp=0.2 | Parse question intent, build extraction plan |
| `context_planner_node` | `agents/nodes/context_planner_node.py` | GPT-4.1, temp=0.1 | Create workers + tasks, chunk large files |
| `worker_tool_executor_node` | `agents/nodes/worker_tool_executor_node.py` | GPT-4.1 (via worker tool) | Parallel document extraction |
| `task_executor_node` | `agents/nodes/task_executor_node.py` | Claude Sonnet 4 | Synthesis + export |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent Framework | **LangGraph** (StateGraph) |
| LLM — Planning/Extraction | **OpenAI GPT-4.1** (`gpt-4.1-2025-04-14`) |
| LLM — Synthesis/Writing | **AWS Bedrock** (Claude Sonnet 4) |
| Data Validation | **Pydantic v2** |
| Web UI | **Flask 3** |
| Document Parsing | pdfplumber, PyMuPDF, python-pptx, python-docx, openpyxl, pandas |
| Export | python-pptx, python-docx, weasyprint (PDF) |
| Observability | **Langfuse** (optional) |
| Containerisation | Docker + docker-compose |

---

## Project Structure

```
document_agent/
├── agents/
│   ├── graph.py                    ← LangGraph definition
│   ├── state.py                    ← AgentState TypedDict
│   ├── planner_models.py           ← Pydantic: ContextPlan, WorkerPlan, TaskPlan
│   ├── augmenter_models.py         ← Pydantic: AugmentedQuery
│   ├── nodes/
│   │   ├── query_augmentor_node.py
│   │   ├── context_planner_node.py
│   │   ├── worker_tool_executor_node.py
│   │   └── task_executor_node.py
│   ├── prompts/
│   │   ├── augmenter_prompt.py
│   │   └── planner_prompt.py
│   └── LLM_CALLs/
│       ├── llm_handler.py          ← Task-type → model routing
│       └── llm_client.py          ← OpenAI + Bedrock HTTP clients
├── tools/
│   ├── registry.py                 ← All tool callables
│   ├── workers/
│   │   └── extraction_tools.py    ← worker_document_extractor
│   └── tasks/
│       ├── task_base.py           ← invoke_task_llm(), EXPORT_ROOT
│       ├── unified_executor.py
│       ├── html_export.py
│       ├── pdf_export.py
│       ├── ppt_export.py
│       ├── word_export.py
│       ├── markdown_display.py
│       ├── plain_text_display.py
│       └── dashboard_display.py
├── file_handler/
│   ├── file_handler.py            ← save_uploaded_file()
│   ├── parser.py                  ← parse_uploaded_file() dispatcher
│   ├── parsed_output_storage.py   ← snapshot caching
│   └── parser_logic/              ← per-format parsers
│       ├── pdf_parser.py
│       ├── presentation_parser.py
│       ├── document_parser.py
│       ├── spreadsheet_parser.py
│       ├── tabular_parser.py
│       ├── image_parser.py
│       ├── audio_parser.py
│       ├── video_parser.py
│       ├── html_parser.py
│       ├── json_parser.py
│       ├── xml_parser.py
│       ├── archive_parser.py
│       └── text_parser.py
├── conversation_summarizer.py     ← Rolling LLM-compressed memory
├── snapshot_recorder.py           ← Run index (snapshots.json)
├── inmemory_recorder.py           ← Per-turn conversation log
└── context_agent_UI/
    └── flask_app/
        ├── app.py                 ← Flask app + all API routes
        ├── templates/index.html   ← Chat UI
        └── static/
            ├── css/style.css
            └── js/main.js
```

---

## Quick Start (Local)

### Prerequisites

- Python 3.11+
- An OpenAI API key (for GPT-4.1)
- AWS credentials configured (for Claude Sonnet 4 via Bedrock)
- Optional: `ffmpeg` installed (for video transcription)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/gogulkumar/document_agent.git
cd document_agent

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env — set your OpenAI API key and AWS credentials

# 5. Run the Flask app
cd context_agent_UI/flask_app
python app.py
```

Open your browser at **http://localhost:5000**

---

## Configuration (.env)

Copy `.env.example` to `.env` and fill in:

```env
# Required: OpenAI key
OPENAI_API_KEY=sk-...

# Required: AWS region (Bedrock)
AWS_REGION=us-east-1
# Also set AWS credentials via IAM role, env vars, or ~/.aws/credentials

# Optional: directories
NOTEBOOK_AGENT_UPLOAD_DIR=./uploads
NOTEBOOK_AGENT_EXPORT_DIR=./exports

# Optional: Langfuse tracing
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

# Flask
FLASK_PORT=5000
FLASK_DEBUG=false
```

### AWS Bedrock Setup

The agent uses **Claude Sonnet 4** for synthesis tasks via AWS Bedrock. You need to:

1. Enable the model in the [AWS Bedrock console](https://console.aws.amazon.com/bedrock/) under **Model access**
2. Ensure your IAM user/role has `bedrock:InvokeModel` permission
3. Set `AWS_REGION` to a region where Bedrock is available (e.g., `us-east-1`)

If you want to use **OpenAI only** (skip Bedrock), edit `agents/LLM_CALLs/llm_handler.py` and move `synthesis`, `generation`, `writing`, `summary` to the `OPENAI_TASK_TYPES` set and map them to a GPT model.

---

## Running with Docker

```bash
# 1. Configure environment
cp .env.example .env   # fill in your keys

# 2. Build and start
docker-compose up --build

# 3. Access
open http://localhost:5000
```

To run without docker-compose:

```bash
docker build -t notebook-agent .
docker run -p 5000:5000 --env-file .env notebook-agent
```

---

## API Reference

All endpoints are served by the Flask app. Base URL: `http://localhost:5000`

### `POST /api/session/new`
Create a new session. Returns `{ run_id: string }`.

### `POST /api/upload`
Upload and parse files.

**Form data:**
- `run_id` (string)
- `files` (multipart, one or more files)

**Response:** `{ run_id, files: [{ file_id, name, chars, topic }] }`

### `POST /api/chat`
Run the full agent pipeline.

**JSON body:**
```json
{
  "run_id": "...",
  "message": "What was revenue growth in Q4?",
  "message_id": "msg_001"
}
```

**Response:**
```json
{
  "output": "<html>...</html>",
  "export_artifacts": [{ "download_url": "/api/export/abc.pdf", "display_format": "export_pdf" }],
  "task_results": [...],
  "run_id": "...",
  "message_id": "..."
}
```

### `GET /api/export/<filename>`
Download an exported file.

### `GET /api/session/<run_id>/files`
List files in a session.

### `GET /health`
Health check. Returns `{ status: "ok" }`.

---

## How to Host

### Option 1: AWS EC2 (Recommended — native Bedrock access)

EC2 gives you native IAM role access to Bedrock (no need to manage AWS keys).

```bash
# 1. Launch an EC2 instance (Amazon Linux 2023, t3.medium or larger)
# 2. Attach an IAM role with bedrock:InvokeModel permission
# 3. SSH in and run:

sudo dnf install -y python3.11 python3.11-pip git docker
sudo systemctl start docker
git clone https://github.com/gogulkumar/document_agent.git
cd document_agent
cp .env.example .env
# Only set OPENAI_API_KEY — Bedrock uses the instance IAM role

# With Docker (recommended):
sudo docker-compose up -d

# Or directly:
pip3.11 install -r requirements.txt
cd context_agent_UI/flask_app
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 300 app:app
```

Add **NGINX** as a reverse proxy for HTTPS and a custom domain.

### Option 2: Railway (Simplest — one command)

[Railway](https://railway.app) auto-detects Dockerfile and deploys instantly.

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login

# Deploy
cd document_agent
railway up
```

Set environment variables in the Railway dashboard. Note: you'll still need AWS credentials configured (use Railway's env vars for `AWS_ACCESS_KEY_ID` etc.).

### Option 3: Render

1. Push to GitHub (done after following this README)
2. Create a new **Web Service** on [render.com](https://render.com)
3. Connect your `gogulkumar/document_agent` repo
4. Set **Build Command**: `pip install -r requirements.txt`
5. Set **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --chdir context_agent_UI/flask_app --timeout 300 app:app`
6. Add all environment variables in the Render dashboard

### Option 4: AWS ECS / App Runner (Production)

For production scale, use **AWS App Runner** with a Docker image pushed to ECR:

```bash
# Build and push to ECR
aws ecr create-repository --repository-name notebook-agent
docker build -t notebook-agent .
docker tag notebook-agent:latest <account>.dkr.ecr.<region>.amazonaws.com/notebook-agent:latest
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker push <account>.dkr.ecr.<region>.amazonaws.com/notebook-agent:latest

# Create App Runner service via AWS Console or CLI
```

App Runner auto-scales, handles HTTPS, and your ECS task role gives native Bedrock access.

### Option 5: Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Deploy
cd document_agent
fly launch
fly secrets set OPENAI_API_KEY=sk-... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
fly deploy
```

### Hosting Comparison

| Option | Ease | Cost | Bedrock auth | Best for |
|---|---|---|---|---|
| AWS EC2 | Medium | ~$20–50/mo | IAM role (best) | Full control |
| AWS App Runner | Medium | Pay per use | IAM role | Production |
| Railway | Very easy | ~$5–20/mo | Env vars | Quick deploy |
| Render | Easy | Free tier / $7+ | Env vars | Easy deploy |
| Fly.io | Easy | ~$3–20/mo | Env vars | Lightweight |

---

## LLM Routing

The agent uses two LLM families:

| Task Type | Model | Platform | Rationale |
|---|---|---|---|
| `analysis`, `planning`, `extraction` | GPT-4.1 | OpenAI | Fast, reliable structured JSON output |
| `synthesis`, `generation`, `writing` | Claude Sonnet 4 | AWS Bedrock | 200k context, superior long-form prose |
| `conversation_summarizer` | GPT-4.1 | OpenAI | Reliable compression |
| `image` | GPT-4 Vision | OpenAI | Vision capability |

JSON parsing uses a 4-attempt fallback chain: raw → trailing-comma fix → json5 → markdown block extraction.

---

## Supported File Types

| Format | Parser | Notes |
|---|---|---|
| PDF | pdfplumber + PyMuPDF | Text + tables; complex layouts use vision |
| PPTX | python-pptx | Slides + speaker notes |
| DOCX | python-docx | Paragraphs + tables |
| XLSX/XLS | openpyxl | All sheets → markdown tables |
| CSV/TSV | pandas | Auto-detected delimiter |
| PNG/JPG | GPT-4 Vision | Describes charts, text, data |
| MP3/WAV | OpenAI Whisper | Full transcription |
| MP4/MOV | ffmpeg + Whisper | Audio track extracted then transcribed |
| HTML | BeautifulSoup | Scripts/styles stripped |
| JSON | stdlib | Pretty-printed |
| XML | ElementTree | Text nodes extracted |
| ZIP/TAR | stdlib | Lists members + extracts text files |
| TXT/MD | Native read | As-is |

---

## Export Formats

| Format | Tool | Output |
|---|---|---|
| HTML report | `task_html_export` | Styled HTML file |
| Dashboard | `task_dashboard_display` | Interactive Chart.js HTML |
| PDF | `task_pdf_export` | PDF via weasyprint (falls back to HTML) |
| PowerPoint | `task_ppt_export` | .pptx via python-pptx |
| Word | `task_word_export` | .docx via python-docx |
| Plain text | `task_plain_text_display` | Clean text (inline, no download) |
| Markdown | `task_markdown_display` | Markdown (inline) |

---

## Extending the Agent

### Add a new export tool

1. Create `tools/tasks/my_export.py` with a `my_export(task_description, dependency_payload, **kwargs)` function
2. Register it in `tools/registry.py` under `EXPORT_TOOLS`
3. Add the mapping in `agents/nodes/task_executor_node.py`'s `DISPLAY_FORMAT_TOOL_MAP`
4. Update the planner prompt in `agents/prompts/planner_prompt.py`

### Add a new file parser

1. Create `file_handler/parser_logic/my_parser.py` with a `parse(file_path: str) -> str` function
2. Register the extension mapping in `file_handler/parser.py`'s `_get_parser()` function

### Use conditional graph edges (skip workers for display-only changes)

In `agents/graph.py`, replace `add_edge("context_planner", "worker_executor")` with `add_conditional_edges()` based on `context_plan.intent`. See [LangGraph docs](https://langchain-ai.github.io/langgraph/).

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'agents'`**
The Flask app must be run from the project root. Either run `python context_agent_UI/flask_app/app.py` from the root, or the app auto-adds the root to `sys.path`.

**`botocore.exceptions.NoCredentialsError`**
AWS credentials are not configured. See [Configuration](#configuration-env) for Bedrock setup options.

**`openai.AuthenticationError`**
Check `OPENAI_API_KEY` (or `test_apikey`) in your `.env` file.

**PDF parsing returns empty text**
Complex PDFs (scanned/image-based) are not handled by the default PDF parser. Install `pytesseract` and add OCR support in `file_handler/parser_logic/pdf_parser.py`.

**`weasyprint` PDF export fails**
weasyprint requires system libraries. Install them:
```bash
# Ubuntu/Debian
sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0 libcairo2
# macOS
brew install pango cairo
```
If unavailable, the PDF tool falls back to saving an HTML file.

**Workers return `=== NO RELEVANT INFORMATION ===`**
The file chunk didn't contain data relevant to the question. This is normal — the task executor will synthesise from other workers that did find relevant content.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.
