# Industrial Document Intelligence Platform

A production-ready Retrieval-Augmented Generation (RAG) platform for industrial documentation. Upload technical manuals, maintenance guides, and specifications — then ask questions and receive grounded, cited answers backed by your documents.

Built as a portfolio project demonstrating real-world AI Engineering practices: clean architecture, LangGraph agent workflows, RAGAS evaluation, and full Docker deployment.

---

## Features

- **Multi-format ingestion** — PDF, DOCX, and plain-text documents
- **Semantic search** — Qdrant vector store with cosine similarity retrieval
- **Grounded answers** — Ollama LLM generates responses strictly from retrieved context
- **Source citations** — every answer cites document name, page number, and relevance score
- **LangGraph agent** — deterministic 4-node graph (retrieve → assemble → generate → cite)
- **RAGAS evaluation** — automated Faithfulness, Answer Relevancy, and Context Recall scoring
- **Threshold calibration** — sweep script finds the optimal retrieval score threshold
- **REST API** — FastAPI with structured error responses, request IDs, and health probes
- **Background ingestion** — documents are processed asynchronously; upload returns immediately
- **Full Docker Compose stack** — one command brings up app + Qdrant + Ollama

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      FastAPI (port 8000)                  │
│  POST /v1/documents/upload   GET /v1/documents            │
│  POST /v1/chat/query         GET /v1/health/live          │
└──────────────┬───────────────────────┬────────────────────┘
               │                       │
     ┌─────────▼──────────┐   ┌───────▼────────────┐
     │  IngestionService   │   │   QueryService      │
     │  (background task)  │   │  (graph.invoke())   │
     └─────────┬──────────┘   └───────┬────────────┘
               │                       │
     ┌─────────▼──────────┐   ┌───────▼────────────────────────┐
     │  Extract → Chunk    │   │     LangGraph StateGraph        │
     │  Embed   → Upsert   │   │  retrieve → assemble →         │
     └─────────┬──────────┘   │  generate → cite               │
               │               └───────┬────────────────────────┘
     ┌─────────▼──────────────────────▼────────────────────────┐
     │                  Infrastructure                           │
     │   Qdrant (vectors)   SQLite (metadata)   Ollama (LLM)   │
     └──────────────────────────────────────────────────────────┘
```

### LangGraph RAG Graph

```
[retrieve] ──(empty)──→ END
    │
    │ (chunks found)
    ▼
[assemble]
    │
    ▼
[generate] ──(error)──→ END
    │
    │ (answer)
    ▼
 [cite]
    │
    ▼
  END
```

| Node | Type | Responsibility |
|------|------|----------------|
| `retrieve` | Deterministic | Embed question → search Qdrant |
| `assemble` | Deterministic | Sort by score, enforce character budget |
| `generate` | LLM | Call Ollama with assembled context |
| `cite` | Deterministic | Build Citation objects from included chunks |

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Docker + Compose)
- 4 GB RAM minimum (models: llama3.2:3b ~2 GB, nomic-embed-text ~270 MB)

### 1. Clone and configure

```bash
git clone <repo-url>
cd industrial-rag-platform
cp .env.example .env   # defaults work out of the box
```

### 2. Start the stack

```bash
docker compose up -d --build
```

This starts three containers:
- **app** — FastAPI application on `http://localhost:8000`
- **qdrant** — Vector database on `http://localhost:6333`
- **ollama** — LLM runtime on `http://localhost:11434` (downloads models on first run)

Check status:

```bash
docker compose ps
docker compose logs -f ollama   # watch model downloads (~2 GB on first run)
```

### 3. Wait for Ollama to be ready

First-run model downloads take 2–10 minutes depending on your connection. The `app` container waits for Ollama before starting.

```bash
# Check when models are ready
docker compose exec ollama ollama list
```

### 4. Upload a document

```bash
curl -X POST http://localhost:8000/v1/documents/upload \
  -F "file=@/path/to/your/manual.pdf"
```

The response contains a `document_id`. Ingestion runs in the background:

```bash
# Poll until status is READY
curl http://localhost:8000/v1/documents/<document_id>
```

### 5. Ask a question

```bash
curl -X POST http://localhost:8000/v1/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the recommended hydraulic oil change interval?",
    "top_k": 5,
    "score_threshold": 0.6
  }'
```

---

## Supported Document Formats

| Format | Detection | Notes |
|--------|-----------|-------|
| PDF | Magic bytes `%PDF-` | Requires a text layer (not scanned/OCR) |
| DOCX | ZIP magic + `.docx` extension | Body paragraphs only; tables excluded |
| TXT | `.txt` extension | UTF-8 or latin-1 encoding |

---

## API Reference

### Documents

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/documents/upload` | Upload a document (multipart/form-data) |
| `GET` | `/v1/documents` | List all documents |
| `GET` | `/v1/documents/{id}` | Get document status and metadata |
| `DELETE` | `/v1/documents/{id}` | Delete document and its vectors |

**Upload response (202 Accepted):**
```json
{
  "document_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "filename": "hydraulic_manual.pdf",
  "status": "pending",
  "message": "File accepted. Ingestion running in background."
}
```

**Document statuses:** `pending` → `processing` → `ready` | `failed`

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/chat/query` | Ask a question, receive a grounded answer |

**Request:**
```json
{
  "question": "What are the torque specifications for the main pump coupling?",
  "top_k": 5,
  "score_threshold": 0.6,
  "document_id": null,
  "include_contexts": false
}
```

**Response:**
```json
{
  "answer": "The main pump coupling requires 45 Nm torque...",
  "citations": [
    {
      "document_name": "hydraulic_manual.pdf",
      "page_number": 12,
      "chunk_index": 3,
      "relevance_score": 0.847
    }
  ],
  "retrieval_count": 5,
  "context_chunks_used": 3,
  "latency_ms": 1243.7,
  "request_id": "abc-123"
}
```

Set `include_contexts: true` to include the raw chunk texts in the response (used by the evaluation pipeline).

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/health/live` | Liveness probe (always 200 if app is up) |
| `GET` | `/v1/health/ready` | Readiness probe (checks Qdrant + Ollama) |
| `GET` | `/v1/metrics` | Document counts and ingestion stats |

---

## Evaluation Pipeline

The evaluation pipeline uses [RAGAS](https://docs.ragas.io/) to measure answer quality against a 23-question benchmark dataset.

### Target scores (from PRD)

| Metric | Target | Description |
|--------|--------|-------------|
| Faithfulness | ≥ 0.80 | Are all claims supported by retrieved context? |
| Answer Relevancy | ≥ 0.80 | Is the answer relevant to the question? |
| Context Recall | ≥ 0.75 | Does retrieved context contain the needed info? |

### Run evaluation

```bash
# Requires the stack running with a seeded document
python scripts/seed_demo_data.py          # upload benchmark document
python evaluation/run_ragas.py            # run full RAGAS evaluation
```

Results are saved to `evaluation/results/baseline.json`.

### Threshold calibration

```bash
python evaluation/threshold_sweep.py
# Sweeps score_threshold values 0.4, 0.5, 0.6, 0.7
# Recommends the threshold with the highest harmonic mean of all 3 metrics
```

Results are saved to `evaluation/results/threshold_sweep.json`.

---

## Development

### Local setup (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"          # installs app + dev dependencies

# Start Qdrant and Ollama separately, then:
uvicorn app.main:app --reload
```

### Running tests

```bash
pytest                           # unit tests only (no Docker needed)
pytest -m integration            # integration tests (requires Docker stack)
pytest --cov=app                 # with coverage report
```

### Code quality

```bash
ruff check .                     # lint
black --check .                  # format check
ruff check . --fix && black .    # auto-fix
```

---

## Configuration

All settings are read from environment variables (or `.env`). Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL` | `llama3.2:3b` | Ollama model for answer generation |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Ollama model for embeddings |
| `EMBEDDING_DIMENSIONS` | `768` | Vector dimensions (must match embedding model) |
| `QDRANT_HOST` | `localhost` | Qdrant hostname |
| `QDRANT_PORT` | `6333` | Qdrant REST port |
| `RELEVANCE_SCORE_THRESHOLD` | `0.6` | Default retrieval similarity threshold |
| `DEFAULT_TOP_K` | `5` | Default number of chunks to retrieve |
| `MAX_CONTEXT_CHARS` | `8192` | Maximum context window for LLM (~2 048 tokens) |
| `CHUNK_SIZE_CHARS` | `1024` | Target chunk size in characters |
| `CHUNK_OVERLAP_CHARS` | `128` | Overlap between consecutive chunks |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum upload file size |
| `INGESTION_CONCURRENCY` | `2` | Maximum parallel ingestion pipelines |
| `APP_ENV` | `development` | Environment (`development` / `production` / `test`) |
| `LOG_FORMAT` | `text` | Log format (`text` for dev, `json` for production) |

---

## Project Structure

```
industrial-rag-platform/
├── app/
│   ├── agents/               # LangGraph agent and graph definition
│   │   ├── rag_graph.py      # Graph builder (entry point)
│   │   ├── state.py          # RAGState TypedDict
│   │   └── nodes/            # One file per graph node
│   ├── api/v1/routers/       # FastAPI route handlers
│   ├── core/                 # Config, models, exceptions, logging, prompts
│   ├── db/                   # SQLite document registry + Qdrant repository
│   ├── rag/                  # Extractor, chunker, embedder, retriever
│   └── services/             # IngestionService, QueryService
├── evaluation/
│   ├── datasets/             # Benchmark Q&A pairs (industrial_qa.json)
│   ├── results/              # Evaluation output JSON files
│   ├── metrics.py            # RAGAS metric computation
│   ├── pipeline_client.py    # HTTP client for querying the live API
│   ├── run_ragas.py          # CLI: run full evaluation
│   └── threshold_sweep.py    # CLI: sweep score thresholds
├── scripts/
│   ├── init_collection.py    # Qdrant collection initialisation
│   ├── seed_demo_data.py     # Generate and upload benchmark document
│   └── pull_models.sh        # Ollama model download entrypoint
├── tests/
│   ├── unit/                 # Unit tests (no external services)
│   └── integration/          # Integration tests (require Docker)
├── docs/architecture/        # Architecture docs and diagrams
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Web framework | FastAPI 0.115+ |
| Agent framework | LangGraph 0.2+ |
| LLM runtime | Ollama (llama3.2:3b) |
| Embedding model | nomic-embed-text (768-dim) |
| Vector store | Qdrant 1.12+ |
| Document registry | SQLite via SQLModel |
| PDF extraction | pdfplumber |
| DOCX extraction | python-docx |
| Evaluation | RAGAS 0.2+ |
| Containerisation | Docker + Docker Compose |
| Python | 3.12 |

---

## Interview Notes

This project was built to demonstrate AI Engineering competencies relevant to production roles:

- **RAG system design** — end-to-end pipeline from document ingestion to grounded answer generation
- **LangGraph** — deterministic graph nodes with conditional routing and error-as-state pattern
- **Evaluation** — RAGAS metrics with threshold calibration; not just "does it work" but "how well"
- **Clean architecture** — strict layer separation; business logic never lives in route handlers
- **Production patterns** — background tasks, async concurrency control, structured logging, health probes
- **Testability** — 172+ unit tests requiring no external services; integration tests clearly marked
