# Industrial Document Intelligence Platform

> Upload technical manuals and specifications. Ask questions. Get grounded answers with source citations — powered entirely by open-source models running locally.

A production-grade **Retrieval-Augmented Generation (RAG)** platform built for industrial documentation. Designed and implemented from scratch as a portfolio project targeting AI Engineer roles, demonstrating end-to-end AI system design: document ingestion, vector search, LangGraph agent orchestration, REST API, and automated RAGAS evaluation.

---

## Benchmark Results

Evaluated on a 23-question hydraulic systems benchmark dataset:

| Metric | Result | Target |
|--------|--------|--------|
| In-scope answer rate | **20 / 20 (100%)** | — |
| Out-of-scope rejection | **3 / 3 (100%)** | — |
| Faithfulness | ≥ 0.80 target | Grounded, no hallucination |
| Answer Relevancy | ≥ 0.80 target | On-topic responses |
| Context Recall | ≥ 0.75 target | Retrieval quality |

The system correctly answered every domain question and rejected every out-of-scope question (e.g. "What is the capital of France?") without hallucinating an answer.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **API** | FastAPI 0.115, Pydantic v2, Python 3.12 |
| **Agent / Orchestration** | LangGraph 0.2 (StateGraph, conditional edges) |
| **LLM Runtime** | Ollama — llama3.2:3b (fully local, no API keys) |
| **Embeddings** | Ollama — nomic-embed-text (768-dim) |
| **Vector Store** | Qdrant (cosine similarity, gRPC) |
| **Document Registry** | SQLite via SQLModel |
| **Document Parsing** | pdfplumber (PDF), python-docx (DOCX), built-in (TXT) |
| **Evaluation** | RAGAS (Faithfulness, Answer Relevancy, Context Recall) |
| **Infrastructure** | Docker, Docker Compose |
| **Code Quality** | Ruff, Black, Pytest (234 tests) |

---

## What It Does

Users can:

1. **Upload** technical documents (PDF, DOCX, TXT) via REST API
2. **Ask questions** in natural language
3. **Receive grounded answers** — the LLM only uses retrieved context, never invents facts
4. **See citations** — every answer cites document name, page number, and relevance score
5. **Evaluate quality** — automated RAGAS pipeline measures faithfulness and retrieval quality

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    FastAPI (port 8000)                    │
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

The query pipeline runs as a compiled LangGraph `StateGraph` — not a sequential function chain. This enables conditional routing, clean error propagation, and node-level testability.

```
[retrieve] ──── no chunks ────→ END   (returns "No relevant documents found")
    │
    │ chunks found
    ▼
[assemble]  ← sorts by score, enforces 8 192-char context budget
    │
    ▼
[generate]  ← Ollama LLM with RAG prompt
    │   │
    │   └── Ollama unreachable → sets error in state → END (HTTP 503)
    ▼
 [cite]  ← builds Citation objects from included chunks
    │
    ▼
  END
```

| Node | Type | What it does |
|------|------|--------------|
| `retrieve` | Deterministic | Embed question → cosine search in Qdrant |
| `assemble` | Deterministic | Sort chunks by score, trim to context budget |
| `generate` | LLM | Call Ollama; catches connectivity errors as state |
| `cite` | Deterministic | Build source citations from included chunks |

---

## Quick Start

**Requirements:** Docker Desktop, 4 GB RAM free

```bash
git clone <repo-url>
cd industrial-rag-platform
cp .env.example .env

docker compose up -d --build
# First run downloads ~2.3 GB of models — takes 5–10 minutes
```

Check everything is ready:
```bash
curl http://localhost:8000/v1/health/ready
# {"status":"ready","services":{"ollama":true,"qdrant":true}}
```

Seed the demo document and run the evaluation:
```bash
docker compose exec app python scripts/seed_demo_data.py
docker compose exec app python -m evaluation.run_ragas --skip-ragas
```

Upload your own document and ask a question:

**Bash:**
```bash
curl -X POST http://localhost:8000/v1/documents/upload -F "file=@manual.pdf"

curl -X POST http://localhost:8000/v1/chat/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the oil change interval?", "top_k": 5, "score_threshold": 0.6}'
```

**PowerShell:**
```powershell
# Upload
Invoke-WebRequest -Uri http://localhost:8000/v1/documents/upload -Method Post -Form @{file = Get-Item -Path "manual.pdf"}

# Query (save this as query.json first, then run):
Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8000/v1/chat/query -Method POST -ContentType "application/json" -InFile query.json | Select-Object -ExpandProperty Content | ConvertFrom-Json | Select-Object answer, citations, latency_ms
```

---

## API

### Upload a document
```
POST /v1/documents/upload
Content-Type: multipart/form-data

→ 202 Accepted
{"document_id": "...", "filename": "manual.pdf", "status": "pending"}
```
Ingestion runs in the background. Poll `GET /v1/documents/{id}` until `"status": "ready"`.

**Bash:**
```bash
curl -X POST http://localhost:8000/v1/documents/upload -F "file=@manual.pdf"
```

**PowerShell:**
```powershell
Invoke-WebRequest -Uri http://localhost:8000/v1/documents/upload -Method Post -Form @{file = Get-Item -Path "manual.pdf"}
```

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

**Bash:**
```bash
curl -X POST http://localhost:8000/v1/chat/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the torque specs?", "top_k": 5, "score_threshold": 0.6}'
```

**PowerShell:**
Create a `query.json` file with your request:
```json
{
  "question": "What are the torque specs for the pump coupling?",
  "top_k": 5,
  "score_threshold": 0.6
}
```

Then run:
```powershell
Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8000/v1/chat/query -Method POST -ContentType "application/json" -InFile query.json | Select-Object -ExpandProperty Content | ConvertFrom-Json | Select-Object answer, citations, latency_ms
```

This displays the answer, citations, and latency in a readable format.

### Other endpoints
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/documents` | List all ingested documents |
| `GET` | `/v1/documents/{id}` | Get document status and metadata |
| `DELETE` | `/v1/documents/{id}` | Delete document and its vectors |
| `GET` | `/v1/health/live` | Liveness probe |
| `GET` | `/v1/health/ready` | Readiness probe (checks Qdrant + Ollama) |
| `GET` | `/v1/metrics` | Document counts and ingestion stats |

---

## Supported Formats

| Format | Detection method |
|--------|-----------------|
| PDF | Magic bytes `%PDF-` (extension-independent) |
| DOCX | ZIP magic bytes + `.docx` extension |
| TXT | `.txt` extension, auto-detects UTF-8 / latin-1 |

---

## Evaluation Pipeline

```bash
# Pipeline-only (fast — no LLM judge)
docker compose exec app python -m evaluation.run_ragas --skip-ragas

# Full RAGAS scoring (slow — LLM evaluates every answer)
docker compose exec app python -m evaluation.run_ragas

# Threshold calibration sweep (finds optimal score_threshold)
docker compose exec app python -m evaluation.threshold_sweep
```

Results are saved to `evaluation/results/baseline.json` and `threshold_sweep.json`.

---

## Testing

```bash
# All 234 unit tests — no Docker required
.venv/Scripts/pytest tests/unit/

# Integration tests — requires running stack
.venv/Scripts/pytest -m integration
```

The test suite covers every layer independently: extractors, chunker, embedder, retriever, assembler, all LangGraph nodes, all API routes, and repository classes.

---

## Troubleshooting

### PowerShell JSON Encoding Issues

If you're using PowerShell and encounter `JSON decode error` or `Expecting property name enclosed in double quotes`, this is likely a quoting issue. 

**Solution:** Use PowerShell's native `Invoke-WebRequest` instead of `curl.exe`, or save your request body to a JSON file and pass it via `-InFile`:

```powershell
# Method 1: Use Invoke-WebRequest (recommended)
$body = @{
  question = "Your question here"
  top_k = 5
  score_threshold = 0.6
} | ConvertTo-Json

Invoke-WebRequest -Uri http://localhost:8000/v1/chat/query -Method POST -ContentType "application/json" -Body $body

# Method 2: Use a JSON file (simplest)
# Create query.json, then:
Invoke-WebRequest -Uri http://localhost:8000/v1/chat/query -Method POST -ContentType "application/json" -InFile query.json
```

For bash/Linux users, `curl` works as expected:
```bash
curl -X POST http://localhost:8000/v1/chat/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Your question", "top_k": 5, "score_threshold": 0.6}'
```

---

## Project Structure

```
industrial-rag-platform/
├── app/
│   ├── agents/            # LangGraph graph + 4 node implementations
│   ├── api/v1/routers/    # FastAPI route handlers (documents, chat, system)
│   ├── core/              # Config, Pydantic models, exceptions, logging
│   ├── db/                # Qdrant repository + SQLite document registry
│   ├── rag/               # Extractor, chunker, embedder, retriever
│   └── services/          # IngestionService + QueryService
├── evaluation/
│   ├── datasets/          # 23-question benchmark (industrial_qa.json)
│   ├── metrics.py         # RAGAS computation with Ollama judge
│   ├── pipeline_client.py # HTTP client for live API queries
│   ├── run_ragas.py       # CLI evaluation runner
│   └── threshold_sweep.py # Score threshold calibration
├── scripts/
│   ├── seed_demo_data.py  # Generates + uploads hydraulic manual PDF
│   └── pull_models.sh     # Ollama model init entrypoint
├── tests/
│   ├── unit/              # 234 tests, zero external dependencies
│   └── integration/       # End-to-end tests (require Docker)
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```
