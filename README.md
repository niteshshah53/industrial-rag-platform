# Industrial Document Intelligence Platform

> Upload technical manuals and specifications. Ask questions. Get grounded answers with source citations — powered entirely by open-source models running locally.

A production-grade **Retrieval-Augmented Generation (RAG)** platform built for industrial documentation. Designed and implemented from scratch as a portfolio project targeting AI Engineer roles, demonstrating end-to-end AI system design: document ingestion, vector search, LangGraph agent orchestration, REST API, React web interface, and automated RAGAS evaluation.

---

## What It Does

1. **Upload** technical documents (PDF, DOCX, TXT) via a ChatGPT-style web interface
2. **Ask questions** in natural language
3. **Receive grounded answers** — the LLM only uses retrieved context, never invents facts
4. **See citations** — every answer cites the document name, page number, and relevance score
5. **Evaluate quality** — automated RAGAS pipeline measures faithfulness and retrieval quality

---

## Benchmark Results

Evaluated on a 23-question hydraulic systems benchmark dataset:

| Metric | Result |
|--------|--------|
| In-scope answer rate | **20 / 20 (100%)** |
| Out-of-scope rejection | **3 / 3 (100%)** |
| Faithfulness | ≥ 0.80 target — grounded, no hallucination |
| Answer Relevancy | ≥ 0.80 target — on-topic responses |
| Context Recall | ≥ 0.75 target — retrieval quality |

The system correctly answered every domain question and rejected every out-of-scope question (e.g. "What is the capital of France?") without hallucinating an answer.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, TanStack Query v5 |
| **API** | FastAPI 0.115, Pydantic v2, Python 3.12 |
| **Agent / Orchestration** | LangGraph 0.2 (StateGraph, conditional edges) |
| **LLM Runtime** | Ollama — llama3.2:3b (fully local, no API keys) |
| **Embeddings** | Ollama — nomic-embed-text (768-dim) |
| **Vector Store** | Qdrant (cosine similarity, gRPC) |
| **Document Registry** | SQLite via SQLModel |
| **Document Parsing** | pdfplumber (PDF), python-docx (DOCX), built-in (TXT) |
| **Evaluation** | RAGAS (Faithfulness, Answer Relevancy, Context Recall) |
| **Infrastructure** | Docker, Docker Compose, nginx |
| **Code Quality** | Ruff, Black, Pytest (234 tests) |

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
- `app` — FastAPI backend on port 8000
- `frontend` — React UI on port 3000
- `qdrant` — vector database on port 6333
- `ollama` — local LLM runtime on port 11434

> **First run:** Ollama downloads `llama3.2:3b` (~2.3 GB) and `nomic-embed-text` (~270 MB) in the background. This takes 5–10 minutes depending on your connection. The frontend will be usable once both models are ready.

### 3. Check everything is ready

```bash
curl http://localhost:8000/v1/health/ready
# {"status":"ready","services":{"ollama":true,"qdrant":true}}
```

### 4. Open the web interface

Go to **http://localhost:3000**

You will see a two-panel interface:
- **Left sidebar** — document list and upload dropzone
- **Right panel** — chat window

---

## Using the Web Interface

### Upload a document

1. Drag and drop a PDF, DOCX, or TXT file onto the sidebar dropzone, or click it to browse
2. The document appears in the list with a **Pending** badge
3. Status automatically updates: Pending → Processing → **Ready** (green)
4. Ingestion takes 30–60 seconds for a typical 10-page PDF

### Ask a question

1. Click a **Ready** document in the sidebar to select it
2. Type your question in the chat box and press **Enter**
3. The answer appears with a collapsible **sources** panel showing which document pages were used

### Delete a document

Hover over any Ready or Failed document in the sidebar — a red trash icon appears. Clicking it removes the document and its vectors from Qdrant.

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
│   POST /v1/documents/upload    POST /v1/chat/query        │
│   GET  /v1/documents           GET  /v1/health/ready      │
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
[retrieve] ──── no chunks ────→ END   (returns "No relevant documents found")
    │
    │ chunks found
    ▼
[assemble]  ← sorts by score, enforces 8 192-char context budget
    │
    ▼
[generate]  ← Ollama LLM with RAG prompt
    │
    ▼
 [cite]  ← builds Citation objects from included chunks
    │
    ▼
  END
```

---

## REST API

The full API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Upload a document

```
POST /v1/documents/upload
Content-Type: multipart/form-data

→ 202 Accepted
{"document_id": "...", "filename": "manual.pdf", "status": "pending"}
```

Poll `GET /v1/documents/{id}` until `"status": "ready"`.

### Ask a question

```
POST /v1/chat/query
Content-Type: application/json

{
  "question": "What are the torque specs for the pump coupling?",
  "top_k": 5,
  "score_threshold": 0.6
}

→ 200 OK
{
  "answer": "The pump coupling torque specification is 45 Nm...",
  "citations": [{"document_name": "manual.pdf", "page_number": 12, "relevance_score": 0.847}],
  "retrieval_count": 5,
  "context_chunks_used": 3,
  "latency_ms": 4200.0
}
```

### Other endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/documents` | List all ingested documents |
| `GET` | `/v1/documents/{id}` | Get document status and metadata |
| `DELETE` | `/v1/documents/{id}` | Delete document and its vectors |
| `GET` | `/v1/health/live` | Liveness probe |
| `GET` | `/v1/health/ready` | Readiness probe (checks Qdrant + Ollama) |

---

## Evaluation Pipeline

Seed the demo document first, then run evaluation:

```bash
docker compose exec app python scripts/seed_demo_data.py

# Pipeline-only (fast — no LLM judge)
docker compose exec app python -m evaluation.run_ragas --skip-ragas

# Full RAGAS scoring (slow — LLM evaluates every answer)
docker compose exec app python -m evaluation.run_ragas

# Threshold calibration sweep
docker compose exec app python -m evaluation.threshold_sweep
```

Results are saved to `evaluation/results/baseline.json`.

---

## Testing

```bash
# All 234 unit tests — no Docker required
.venv/Scripts/pytest tests/unit/

# Integration tests — requires running stack
.venv/Scripts/pytest -m integration
```

---

## Supported File Formats

| Format | Detection |
|--------|-----------|
| PDF | Magic bytes `%PDF-` |
| DOCX | ZIP magic bytes + `.docx` extension |
| TXT | `.txt` extension, UTF-8 / latin-1 auto-detect |

---

## Troubleshooting

### Models not downloading

If the health check never returns `"ollama": true`, check Ollama logs:

```bash
docker compose logs ollama --tail=30
```

You can also pull models manually:

```bash
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
```

### Stale citations (old documents appearing in answers)

If citations reference files you've deleted, the Qdrant vectors were not cleaned up. Reset completely:

```bash
curl.exe -X DELETE http://localhost:6333/collections/documents
docker compose exec app python -c "import os; os.remove('/app/uploads/documents.db')"
docker compose restart app
```

Then re-upload your documents.

### Document stuck in Processing

If a document stays in Processing for more than 5 minutes, check the app logs:

```bash
docker compose logs app --tail=30
```

Common causes: Ollama model not yet downloaded, or insufficient RAM.

### PowerShell JSON issues

If using PowerShell and getting JSON errors with `curl`, use a JSON file instead:

```powershell
# Save request to query.json, then:
Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8000/v1/chat/query `
  -Method POST -ContentType "application/json" -InFile query.json
```

---

## Project Structure

```
industrial-rag-platform/
├── frontend/
│   ├── src/
│   │   ├── App.tsx                  # Root layout
│   │   ├── api/client.ts            # Typed API client
│   │   ├── hooks/                   # useDocuments, useChat
│   │   └── components/              # Sidebar, ChatWindow, MessageBubble, etc.
│   ├── nginx.conf                   # SPA routing + /api proxy
│   └── Dockerfile                   # Node build → nginx serve
├── app/
│   ├── agents/                      # LangGraph graph + 4 node implementations
│   ├── api/v1/routers/              # FastAPI route handlers
│   ├── core/                        # Config, models, exceptions, logging
│   ├── db/                          # Qdrant repository + SQLite document registry
│   ├── rag/                         # Extractor, chunker, embedder, retriever
│   └── services/                    # IngestionService + QueryService
├── evaluation/
│   ├── datasets/                    # 23-question benchmark
│   ├── metrics.py                   # RAGAS computation
│   └── run_ragas.py                 # Evaluation CLI
├── scripts/
│   ├── seed_demo_data.py            # Generates + uploads hydraulic manual PDF
│   └── pull_models.sh               # Ollama model init entrypoint
├── tests/
│   ├── unit/                        # 234 tests, zero external dependencies
│   └── integration/                 # End-to-end tests (require Docker)
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```
