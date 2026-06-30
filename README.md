# Document Agent

Document Agent is a local document-analysis workspace. It lets a user upload files, parse them into text snapshots, ask questions, run a staged LangGraph pipeline, generate structured HTML feature views, and export outputs.

The clearest mental model is:

```text
Uploaded files -> parsed snapshots -> session state -> agent pipeline -> answer or artifact
```

This project is not yet a fully reliable autonomous document worker. It is a working foundation with a Flask API, a Next.js UI, local persistence, multiple parsers, and an agent graph that needs tighter production hardening.

## What It Does

- Creates local chat sessions.
- Uploads and parses documents into text/Markdown snapshots.
- Stores session state, memory summaries, turn payloads, uploads, snapshots, and exports locally.
- Routes chat through a LangGraph-style pipeline.
- Supports chat modes: `auto`, `direct`, `thinking`, and `react`.
- Generates dedicated HTML feature views:
  - Mind Map
  - Information Brain
  - Brainstorm
- Exports generated content as HTML, PDF, PowerPoint, Word, Markdown, or plain text depending on task output.

## Current Architecture

```text
document_agent/
  context_agent_UI/flask_app/app.py   Flask API, upload, chat, sessions, export routes
  context_agent_UI/next_app/          Next.js frontend
  agents/graph.py                     LangGraph routing
  agents/nodes/                       Augmentor, planner, workers, task executor, direct response
  agents/LLM_CALLs/                   OpenAI/Bedrock model routing
  file_handler/                       Upload handling and file parsers
  tools/tasks/                        Display and export task implementations
  chat_persistence.py                 Local session persistence
  conversation_summarizer.py          Rolling memory summaries
  runtime_paths.py                    Runtime directory definitions
```

## Application Logic

### 1. Session

The UI creates or restores a `run_id`. The Flask app keeps an in-memory session cache and also persists session data to disk so a session can be restored after restart.

Each session tracks:

- conversation messages
- uploaded file metadata
- parsed snapshot paths
- metadata such as `run_id`, `message_id`, and chat mode

### 2. Upload and Parsing

`POST /api/upload` receives files, saves the raw bytes, parses each file, and stores parsed text snapshots. The parsed snapshot becomes the main source of document context for the agent pipeline.

Supported parser areas include:

- PDF
- DOCX and text documents
- PPTX
- XLSX and tabular files
- HTML/XML/JSON
- images
- audio/video hooks, depending on installed parser support
- archives

The practical quality of answers depends heavily on parser quality. If parsing produces weak or empty snapshots, the agent will behave poorly even if the LLM call succeeds.

### 3. Chat Pipeline

Chat requests go through `POST /api/chat` or `POST /api/chat/stream`.

The pipeline is:

```text
query_augmentor
  -> direct_response
```

or:

```text
query_augmentor
  -> context_planner
  -> worker_executor
  -> task_executor
```

Routing rules:

- `direct` and `thinking` use the direct response path.
- `auto` uses direct response when no uploaded files are available.
- `auto` and `react` use the planner/worker/task path when document context is available.
- If the planner returns no workers, the app skips directly to task execution.

### 4. Agent Roles

`query_augmentor`
: Normalizes the user request and decides intent.

`direct_response`
: Produces a simpler answer without running document workers.

`context_planner`
: Builds a plan that selects relevant files, workers, and downstream tasks.

`worker_executor`
: Runs extraction work against parsed document snapshots.

`task_executor`
: Synthesizes the final answer and invokes display/export tasks.

### 5. Feature Views

Feature endpoints are separate from normal chat:

```text
POST /api/features/mind-map
POST /api/features/information-brain
POST /api/features/brainstorm
```

They collect recent conversation context, memory summary, and excerpts from uploaded file snapshots, then ask the model to generate a complete self-contained HTML document. The result is saved as an export artifact and can be viewed or downloaded.

### 6. Persistence

The app stores local runtime data for:

- uploads
- parsed snapshots
- chat sessions
- turn payloads
- memory summaries
- exported artifacts
- event logs

This is useful for local development and demos. It is not a production multi-tenant storage design.

## Running Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm
- OpenAI API key for most agent behavior

Some export features, especially PDF generation through WeasyPrint, may require system libraries depending on your operating system.

### Backend

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python context_agent_UI/flask_app/app.py
```

Default backend:

```text
http://localhost:5001
```

### Frontend

```bash
cd context_agent_UI/next_app
npm install
npm run dev
```

Default frontend:

```text
http://localhost:3000
```

The Flask root route redirects to `NEXT_UI_URL`, defaulting to:

```text
http://127.0.0.1:3001
```

Set it if your Next.js app runs somewhere else:

```env
NEXT_UI_URL=http://localhost:3000
```

## Environment Variables

Minimum useful configuration:

```env
OPENAI_API_KEY=your_key
NEXT_UI_URL=http://localhost:3000
FLASK_PORT=5001
FLASK_DEBUG=false
```

Optional:

```env
USE_BEDROCK=false
AWS_REGION=us-east-1
LANGFUSE_HOST=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
TAVILY_API_KEY=
```

Model routing lives in `agents/LLM_CALLs/llm_handler.py`. By default, generation and writing tasks fall back to OpenAI unless `USE_BEDROCK=true`.

## API Surface

### Sessions

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/session/new` | Create a session and return `run_id` |
| `GET` | `/api/session/{run_id}` | Restore a session |
| `DELETE` | `/api/session/{run_id}` | Delete a saved session |
| `GET` | `/api/sessions` | List saved sessions |
| `GET` | `/api/session/{run_id}/summary` | Read memory summary |

### Files

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/upload` | Upload and parse files |
| `POST` | `/api/ingest` | Ingest an existing file path |
| `GET` | `/api/session/{run_id}/files` | List files for a session |

### Chat

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/chat` | Synchronous agent response |
| `POST` | `/api/chat/stream` | SSE streaming agent response |

### Features and Exports

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/features/{feature_kind}` | Generate a feature HTML artifact |
| `GET` | `/api/export/{filename}` | Download an artifact |
| `GET` | `/api/export/view/{filename}` | View an artifact inline |
| `GET` | `/health` | Health check |

## Production Readiness

This repo needs more work before it should be treated as production-ready.

Highest-priority gaps:

- A clearer single UI contract. The repo has Flask templates and a Next.js UI; the Next.js app should be the primary frontend or the older template path should be removed.
- Stronger parser validation and error reporting. Poor parse output is currently the fastest path to bad agent behavior.
- Durable storage. Local folders are fine for development, not multi-user production.
- Authentication and authorization.
- Tenant isolation for sessions, uploads, memory, and exports.
- Upload security: type validation, malware scanning, size policies, and path hardening.
- More deterministic planner and worker contracts.
- Regression tests for routing, parsing, chat modes, export generation, and session restore.
- Better observability around each agent stage and model call.

## Known Failure Modes

- The agent may answer from thin context if parsing fails or produces a weak snapshot.
- `auto` mode can feel inconsistent because it switches between direct and full pipeline paths.
- `react` currently follows the same full pipeline shape as `auto`; it is not a complete tool-using ReAct implementation.
- Feature views depend on recent conversation and file excerpts, not full retrieval over every uploaded byte.
- Local in-memory session state and disk persistence can diverge if multiple server processes are introduced.
- Export quality depends on the generated HTML/task output and installed system dependencies.

## Recommended Next Fixes

1. Make Next.js the only supported UI and remove or archive the old Flask template UI.
2. Add a parser diagnostics panel so users can see what text was actually extracted.
3. Make chat mode behavior explicit in the UI.
4. Add tests for `route_after_augmentor` and `route_after_planner`.
5. Define a stable `ContextPlan` and `TaskResult` contract with validation at every node boundary.
6. Replace local storage with a durable object store/database before multi-user deployment.

## Development Guidelines

- Keep the agent pipeline honest: do not claim retrieval quality that the parser and planner do not guarantee.
- Log and surface parser failures early.
- Treat generated HTML as untrusted unless it is sanitized or sandboxed.
- Keep feature generation separate from chat responses.
- Do not commit uploads, memory files, snapshots, exports, API keys, or local environment files.

## License

Proprietary. No license has been granted for external use, modification, or distribution.
