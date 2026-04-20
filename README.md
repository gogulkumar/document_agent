# Document Agent

Document Agent is a research and execution workspace for people who need to turn messy source material into a usable outcome.

It is built for the gap between:
- a generic chat assistant that can answer questions,
- and a real document workflow that has to read files, keep memory, reason across evidence, and produce deliverables.

The product is not just "ask a PDF a question." It is a document-native system that can:
- ingest mixed file types,
- preserve local session memory,
- reason over uploaded material,
- create structured views like a mind map or information brain,
- and export polished outputs such as HTML, PDF, PowerPoint, and Word.

## Why This Matters

Most assistants are good at conversation, but weak at document work.

Common failure modes in simpler agents:
- they answer from a shallow summary instead of the real source material,
- they lose context across turns,
- they cannot separate planning, extraction, and synthesis,
- they are poor at producing stakeholder-ready outputs,
- they do not give a clear path from raw documents to a final artifact.

Document Agent exists to solve those problems.

It is useful when you need to:
- understand a large document set quickly,
- connect ideas across multiple files,
- keep local working memory over time,
- brainstorm from evidence instead of improvisation,
- convert analysis into something you can present or share.

## Why Use This Over Other Agents

Compared with a general-purpose chat agent:
- Document Agent is file-first, not prompt-first.
- It stores local chat and memory history.
- It separates lightweight question answering from heavier document workflows.
- It can generate structured feature views, not just text replies.
- It can export deliverables directly from the same workflow.

Compared with a single-step RAG tool:
- It uses staged reasoning instead of one retrieval pass.
- It has explicit planning and worker execution.
- It supports multiple output modes, not only answers.
- It is designed to operate like a research workbench, not only a search box.

Compared with a pure export tool:
- It can think, connect, summarize, and reshape the content before export.
- It keeps the analysis and the artifact in the same session.

## Core Capabilities

### 1. Conversational document analysis

Users can upload files and ask questions in natural language.

The system can work in multiple chat modes:
- `Auto` for the common path
- `Direct` for fast lightweight responses
- `Thinking` for more visible reasoning
- `ReAct` for fuller staged execution

### 2. Dedicated feature views

Some actions are not meant to behave like a normal chat reply.

Document Agent includes dedicated LLM-powered features such as:
- `Mind Map`
- `Information Brain`
- `Brainstorm`

These are feature actions, not just prompt shortcuts. They generate purpose-built views from the current session context and render directly in the preview workspace.

### 3. Local memory and history

The system keeps:
- saved chats,
- turn payloads,
- rolling memory summaries,
- local session artifacts.

This makes it useful as an ongoing workbench rather than a disposable chat.

### 4. Output generation

The same analysis can be turned into:
- HTML reports
- PDF documents
- PowerPoint decks
- Word documents

This is important because the final job is often not "answer the question." The final job is "produce something usable."

## The Main Agent Roles

Document Agent is organized as a set of cooperating agent roles rather than one monolithic model call.

### Query Augmentor

Purpose:
- interpret the user question,
- clarify intent,
- decide whether the request is lightweight or document-heavy,
- enrich the question before deeper execution.

Why it matters:
- better routing,
- better retrieval planning,
- fewer weak downstream steps.

### Direct Response Agent

Purpose:
- answer basic or lightweight requests quickly,
- stream responses directly when full planning is not needed.

Why it matters:
- lower latency for normal questions,
- less unnecessary pipeline overhead.

### Context Planner

Purpose:
- create the execution plan,
- decide which files and chunks matter,
- define workers and downstream tasks.

Why it matters:
- this is where the system stops behaving like a normal chatbot and starts behaving like an operator.

### Worker Extraction Agent

Purpose:
- process document chunks in parallel,
- pull out relevant evidence,
- return focused extraction results to the rest of the graph.

Why it matters:
- scales better across large files,
- reduces the chance that important evidence is missed.

### Task Executor Agent

Purpose:
- synthesize outputs from prior context,
- generate final structured deliverables,
- run export-oriented tasks.

Why it matters:
- turns analysis into outcomes instead of leaving the user with raw notes.

### Feature Generation Layer

Purpose:
- create dedicated non-chat feature outputs such as the mind map, information brain, and brainstorm board.

Why it matters:
- these are not ordinary answers,
- they deserve their own rendering path and UX,
- they help users see structure, not just prose.

## What the User Experience Is Supposed to Feel Like

The ideal experience is:
1. upload documents,
2. ask a question,
3. inspect the answer,
4. open a feature view like `Mind Map` or `Information Brain`,
5. export the result into a stakeholder-ready format.

That makes the app valuable for:
- research
- resume and profile analysis
- business reviews
- investor relations workflows
- strategy synthesis
- executive briefing preparation
- document-to-deck conversion

## Supported Working Model

The current repo is built around:
- a Flask UI,
- LangGraph orchestration,
- OpenAI-backed reasoning,
- optional Bedrock support for selected generation tasks,
- local persistence for chats, memory, uploads, and exports.

The design direction is OpenAI-first by default, with optional model routing where needed.

## Repository Highlights

Important areas of the codebase:
- `agents/`
  - graph logic, routing, node execution
- `context_agent_UI/flask_app/`
  - Flask routes, frontend, streaming UI
- `file_handler/`
  - upload saving, parsing, and snapshot handling
- `tools/tasks/`
  - export and generation tasks
- `chat_persistence.py`
  - local chat and history storage
- `conversation_summarizer.py`
  - rolling memory compression
- `runtime_paths.py`
  - stable local runtime directories

## Who This Is For

Document Agent is for users who need more than a chat window:
- analysts
- founders
- operators
- researchers
- consultants
- students working through long source material
- anyone who needs structured understanding from documents

## High-Level Differentiator

If another agent helps you talk, this agent helps you work.

It is meant to be the layer between raw documents and useful output:
- clearer than generic chat,
- more flexible than a fixed report generator,
- more durable than a one-off document Q&A tool.

## Current Direction

The product is evolving toward a document workspace with:
- dedicated feature actions,
- better preview and split-pane viewing,
- persistent local history,
- stronger export workflows,
- cleaner separation between chat and structured document views.

## In Short

Document Agent is needed because real document work is not one problem.

It is:
- reading,
- planning,
- extracting,
- connecting,
- remembering,
- presenting,
- and exporting.

This project brings those jobs into one agent workspace.
