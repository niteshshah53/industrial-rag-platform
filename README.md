# Industrial Document Intelligence Platform

> Upload technical documents. Ask questions in natural language. Get grounded answers with source citations — powered entirely by open-source models running locally.

A production-grade **Retrieval-Augmented Generation (RAG)** platform built for industrial documentation. Designed and implemented from scratch as a portfolio project targeting AI Engineer roles, demonstrating end-to-end AI system design: document ingestion, vector search, LangGraph agent orchestration, streaming REST API, React web interface, and RAGAS evaluation.

---

## What It Does

1. **Upload** technical documents (PDF, DOCX, TXT) via a ChatGPT-style web interface or REST API
2. **Process** documents automatically — extract text, chunk, embed, store in Qdrant
3. **Chat** using natural language; the LLM only answers from retrieved context, never invents facts
4. **Stream** answers token-by-token with a live typing indicator; stop mid-stream with one click
5. **Cite** every answer — document name, page number, relevance percentage, and passage preview
6. **Group** documents into collections and query across multiple documents at once
7. **Evaluate** pipeline quality with RAGAS (Faithfulness, Answer Relevancy, Context Recall)

---

## Key Features

### AI / Backend
- **LangGraph RAG agent** — 4-node stateful graph: retrieve → assemble → generate → cite
- **Hybrid search** — BM25 sparse + dense vector search (Qdrant + fastembed), combined via Reciprocal Rank Fusion
- **Streaming responses** — SSE endpoint streams tokens as they are generated; first token in < 1s
- **Conversation memory** — last 6 turns of history injected into every LLM call for follow-up questions
- **Multi-document collections** — group documents, run a single query across all members
- **Source citations** — every answer cites document name, page number, and a passage snippet
- **RAGAS evaluation** — reproducible offline benchmark on a 23-question industrial Q&A dataset

### Frontend / UX
- **ChatGPT-style interface** — left sidebar with session history, centered chat window, inline citations
- **Message actions** — hover to Copy, Edit, Regenerate, 👍/👎, or Delete any message
- **Stop generation** — AbortController cancels the stream; partial response is saved
- **Paste file upload** — paste a PDF directly into the chat area to trigger upload
- **Pin and Archive** — pin sessions to keep them at the top; archive to hide without deleting
- **Keyboard shortcuts** — Cmd+K (search), Cmd+Shift+O (new chat), Cmd+Shift+C (copy last answer), Escape (stop)
- **Dark mode** — system-aware theme with manual override

---

## Benchmark Results

Evaluated on a 23-question hydraulic systems benchmark dataset:

| Metric | Result |
|--------|--------|
| In-scope answer rate | **20 / 20 (100%)** |
| Out-of-scope rejection | **3 / 3 (100%)** |
| Faithfulness | ≥ 0.80 target — grounded answers, no hallucination |
| Answer Relevancy | ≥ 0.80 target — on-topic responses |
| Context Recall | ≥ 0.75 target — retrieval quality |

The system correctly answered every domain question and rejected all out-of-scope questions (e.g. "What is the capital of France?") without hallucinating.

---

## Quick Start

**Requirements:** Docker Desktop with at least 4 GB RAM free.

### 1. Clone and configure

```bash
git clone <repo-url>
cd industrial-rag-platform
cp .env.example .env
```

### 2. Start all services

```bash
docker compose up -d --build
```

This starts four containers:

| Container | Purpose | Port |
|-----------|---------|------|
| `app` | FastAPI backend | 8000 |
| `frontend` | React UI (nginx) | 3000 |
| `qdrant` | Vector database | 6333 |
| `ollama` | Local LLM runtime | 11434 |

> **First run:** Ollama downloads `llama3.2:3b` (~2.3 GB) and `nomic-embed-text` (~270 MB) in the background. This takes 5–10 minutes. The UI is usable once both models are ready.

### 3. Verify readiness

```bash
curl http://localhost:8000/v1/health/ready
# {"status":"ready","services":{"ollama":true,"qdrant":true}}
```

### 4. Open the web interface

Go to **http://localhost:3000**

---

## Using the Web Interface

### Upload a document

Click the **+** button in the chat input bar, or paste a PDF file directly into the text area.

The document appears in the sidebar with a **Pending** badge, then transitions automatically: Pending → Processing → **Ready**. Ingestion takes 30–60 seconds for a typical 10-page PDF.

You can manage all documents in detail via the **Documents** panel (Files icon in the sidebar footer).

### Ask a question

1. Click a **Ready** document in the sidebar to select it
2. Type a question and press **Enter** (or **Shift+Enter** for a newline)
3. The answer streams in token-by-token; a **⏹ Stop** button appears during generation
4. Citations appear below the answer — click to expand a source and read the exact passage

### Multi-document collections

1. Click the **Collections** button (folder icon) in the sidebar footer
2. Create a collection, then add documents to it via the checklist
3. Select the collection in the sidebar — all queries now search across every member document

### Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl/Cmd + K` | Focus conversation search |
| `Ctrl/Cmd + Shift + O` | New chat |
| `Ctrl/Cmd + Shift + C` | Copy last assistant answer |
| `Ctrl/Cmd + Shift + R` | Regenerate last response |
| `Ctrl/Cmd + B` | Toggle sidebar (mobile) |
| `Escape` | Stop generation / close panel |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│              React Frontend (port 3000)                   │
│   nginx reverse proxy → strips /api → FastAPI            │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                FastAPI (port 8000)                        │
│   POST /v1/chat/stream     POST /v1/documents/upload      │
│   POST /v1/collections     GET  /v1/health/ready          │
└──────────────┬──────────────────────┬─────────────────────┘
               │                      │
     ┌─────────▼──────────┐  ┌────────▼────────────┐
     │  IngestionService  │  │    QueryService      │
     │  background task   │  │   graph.invoke()     │
     └─────────┬──────────┘  └────────┬────────────┘
               │                      │
     ┌─────────▼──────────┐  ┌────────▼──────────────────────┐
     │  Extract → Chunk   │  │     LangGraph StateGraph       │
     │  Embed   → Upsert  │  │  [retrieve] → [assemble] →    │
     └─────────┬──────────┘  │  [generate] → [cite]          │
               │              └────────┬──────────────────────┘
     ┌─────────▼────────────────────── ▼────────────────────┐
     │               Infrastructure                          │
     │  Qdrant (vectors)  SQLite (metadata)  Ollama (LLM)   │
     └───────────────────────────────────────────────────────┘
```

### LangGraph Agent Graph

```
[retrieve] ──── no chunks ────→ END   ("No relevant documents found")
    │
    │ chunks found
    ▼
[assemble]  ← sort by score, enforce 8 192-char context budget
    │
    ▼
[generate]  ← Ollama LLM call with RAG prompt + conversation history
    │
    ▼
 [cite]  ← build Citation objects from included chunks
    │
    ▼
  END
```

The full graph diagram with all conditional edges is in [`docs/architecture/rag_graph.md`](docs/architecture/rag_graph.md).

---

## REST API

Interactive docs at `http://localhost:8000/docs`.

### Documents

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/documents/upload` | Upload a document (returns 202, background processing) |
| `GET` | `/v1/documents` | List all documents with status |
| `GET` | `/v1/documents/{id}` | Get document metadata and status |
| `DELETE` | `/v1/documents/{id}` | Delete document and its vectors |

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/chat/stream` | Streaming SSE endpoint (primary) |
| `POST` | `/v1/chat/query` | Blocking JSON endpoint |

**Stream request:**
```json
{
  "question": "What are the torque specs for the pump coupling?",
  "document_id": "abc123",
  "top_k": 5,
  "score_threshold": 0.3,
  "search_mode": "hybrid",
  "conversation_history": [
    {"role": "user", "content": "What pump type is used?"},
    {"role": "assistant", "content": "The system uses a centrifugal pump..."}
  ]
}
```

**Stream events:**
```
data: {"type":"token","content":"The "}
data: {"type":"token","content":"coupling torque is "}
data: {"type":"done","answer":"...","citations":[...],"latency_ms":3200}
```

### Collections

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/collections` | Create a named collection |
| `GET` | `/v1/collections` | List all collections |
| `DELETE` | `/v1/collections/{id}` | Delete a collection |
| `POST` | `/v1/collections/{id}/documents/{doc_id}` | Add document to collection |
| `DELETE` | `/v1/collections/{id}/documents/{doc_id}` | Remove document from collection |

Query a collection (searches all member documents):
```json
{"question": "Compare pressure ratings across all manuals", "collection_id": "col-xyz"}
```

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/health/live` | Liveness probe |
| `GET` | `/v1/health/ready` | Readiness probe (checks Qdrant + Ollama) |
| `GET` | `/v1/metrics` | Query counters and latency stats |

---

## Evaluation Pipeline

```bash
# Seed the demo document first
docker compose exec app python scripts/seed_demo_data.py

# Pipeline-only check (fast — no LLM judge)
docker compose exec app python -m evaluation.run_ragas --skip-ragas

# Full RAGAS scoring
docker compose exec app python -m evaluation.run_ragas

# Threshold calibration sweep (0.3 – 0.7)
docker compose exec app python -m evaluation.threshold_sweep
```

Results are saved to `evaluation/results/baseline.json`. The benchmark dataset of 23 industrial Q&A pairs is in `evaluation/datasets/industrial_qa.json`.

---

## Testing

```bash
# 234 unit tests — no Docker required
.venv/Scripts/pytest tests/unit/

# Integration tests — requires running stack
.venv/Scripts/pytest -m integration
```

---

## Troubleshooting

### Models not downloading

```bash
docker compose logs ollama --tail=30
# Pull manually if needed:
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
```

### Document stuck in Processing

```bash
docker compose logs app --tail=30
```

Common causes: Ollama model not yet downloaded, or insufficient RAM (needs ~4 GB free).

### Reset everything (stale vectors / corrupt state)

```bash
curl -X DELETE http://localhost:6333/collections/documents
docker compose exec app python -c "import os; os.remove('/app/uploads/documents.db')"
docker compose restart app
```

---

## Project Structure

```
industrial-rag-platform/
├── app/
│   ├── agents/                  # LangGraph graph + 4 node implementations
│   │   ├── rag_graph.py         # build_rag_graph() — compiled at startup
│   │   ├── state.py             # RAGState TypedDict
│   │   └── nodes/               # retrieve, assemble, generate, cite
│   ├── api/v1/routers/          # FastAPI route handlers (chat, documents, collections, system)
│   ├── core/                    # Config, models, exceptions, prompts, logging
│   ├── db/                      # QdrantRepository + SQLite document registry
│   ├── rag/                     # Extractor, chunker, embedder, retriever, assembler
│   └── services/                # IngestionService + QueryService
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Root layout + global keyboard shortcuts
│   │   ├── api/client.ts        # Typed API client (SSE + REST)
│   │   ├── hooks/               # useChat, useDocuments, useCollections, useTheme
│   │   └── components/          # ChatWindow, MessageBubble, CitationCard, Sidebar, …
│   ├── nginx.conf               # SPA routing + /api proxy
│   └── Dockerfile               # Node build → nginx serve
├── evaluation/
│   ├── datasets/                # 23-question industrial benchmark
│   ├── results/                 # baseline.json (committed)
│   └── run_ragas.py             # Evaluation CLI
├── tests/
│   ├── unit/                    # 234 tests, zero external dependencies
│   └── integration/             # End-to-end tests (require running stack)
├── scripts/
│   ├── seed_demo_data.py        # Generates + uploads demo hydraulic manual
│   └── pull_models.sh           # Ollama model entrypoint
├── docs/architecture/
│   └── rag_graph.md             # Mermaid diagram of the LangGraph graph
├── docker-compose.yml
├── Dockerfile                   # Multi-stage: builder + slim runtime
└── pyproject.toml
```

---

## Tech Stack

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Backend framework** | FastAPI 0.115 | REST API, SSE streaming, dependency injection, OpenAPI docs |
| **Agent orchestration** | LangGraph 0.2 | 4-node stateful RAG graph with typed state and conditional edges |
| **LLM runtime** | Ollama | Serves LLM and embedding model locally — no API keys, no cloud |
| **Language model** | llama3.2:3b | Answer generation and reasoning |
| **Embedding model** | nomic-embed-text (768-dim) | Dense vector embeddings for semantic search |
| **Vector database** | Qdrant | Cosine similarity search, payload filtering, sparse vector support |
| **Sparse search** | fastembed BM25 | Keyword matching for hybrid retrieval (combined via RRF) |
| **Document registry** | SQLite + SQLModel | Document metadata, status tracking, collection membership |
| **PDF parsing** | pdfplumber | Page-aware text extraction with layout preservation |
| **DOCX parsing** | python-docx | Word document text extraction |
| **Evaluation** | RAGAS | Faithfulness, Answer Relevancy, Context Recall metrics |
| **Frontend framework** | React 18 | Component-based ChatGPT-style UI |
| **Language** | TypeScript 5 | Type-safe frontend with compile-time API contract validation |
| **Build tool** | Vite 5 | Fast frontend bundler with HMR |
| **Styling** | Tailwind CSS 3 | Utility-first responsive design, dark mode |
| **Server state** | TanStack Query v5 | Document polling, cache invalidation, loading states |
| **Icons** | Lucide React | Consistent icon set |
| **Reverse proxy** | nginx (alpine) | Serves SPA + proxies `/api/*` to FastAPI — eliminates CORS |
| **Containerisation** | Docker + Compose | Multi-service orchestration, health-check ordering |
| **Backend language** | Python 3.12 | Type hints throughout, async-first |
| **Testing** | Pytest | 234 unit and integration tests |
| **Linting** | Ruff + Black | Zero-violation lint gate on every change |
