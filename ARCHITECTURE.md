# Architecture Document
# Industrial Document Intelligence Platform

---

## Status

**Planning phase.** No implementation code exists yet. This document captures the full target architecture, design decisions, and known limitations to be applied during implementation.

**Review history:**
- v1 — 2026-06-12: Initial architecture from diagram analysis
- v2 — 2026-06-12: Staff-level critical review; corrected design flaws, added observability, API standards, security, and developer experience sections

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Layer Architecture](#2-layer-architecture)
3. [Data Flows](#3-data-flows)
4. [LangGraph Agent Design](#4-langgraph-agent-design)
5. [Folder Structure](#5-folder-structure)
6. [Data Models](#6-data-models)
7. [API Contract](#7-api-contract)
8. [Configuration Strategy](#8-configuration-strategy)
9. [Docker Compose Topology](#9-docker-compose-topology)
10. [Gap Analysis — What the Initial Diagrams Left Out](#10-gap-analysis)
11. [Scalability Concerns](#11-scalability-concerns)
12. [AI Engineering Concerns](#12-ai-engineering-concerns)
13. [LangGraph Concerns](#13-langgraph-concerns)
14. [RAG Concerns](#14-rag-concerns)
15. [Observability and Structured Logging](#15-observability-and-structured-logging)
16. [API Design Standards](#16-api-design-standards)
17. [Security Considerations](#17-security-considerations)
18. [Developer Experience](#18-developer-experience)
19. [Deferred to Future Phases](#19-deferred-to-future-phases)

---

## 1. System Overview

The platform accepts technical PDF documents, converts them into dense vector representations, and answers natural-language questions with grounded, cited responses.

The system is designed as a local-first deployment using entirely open-source components:

- **FastAPI** handles all HTTP traffic.
- **Ollama** serves both the LLM and the embedding model locally.
- **Qdrant** stores and retrieves vector embeddings.
- **LangGraph** orchestrates the multi-step reasoning workflow for query answering.
- **RAGAS** evaluates pipeline quality offline.

```
Client
  │
  ▼
FastAPI (API Layer)
  │
  ▼
Service Layer
  │
  ├──► IngestionService  ─── RAG Layer ──────────► Ollama (embed)
  │                               │
  │                               └──────────────► Qdrant (store)
  │
  └──► QueryService ──► LangGraph Graph
                              │
                              ├──[retrieve] ──────► Ollama (embed)
                              │                └──► Qdrant (search)
                              ├──[assemble]         (deterministic)
                              ├──[generate] ──────► Ollama (LLM)
                              └──[cite]             (deterministic)
```

**Why four nodes instead of three:** Context assembly and token budget enforcement are deterministic operations that do not require LLM reasoning. Merging them into the `generate` node makes it responsible for both assembly logic and generation logic, violating single responsibility and making the LLM call harder to test in isolation. The four-node design is documented in Section 4.

---

## 2. Layer Architecture

The system follows Clean Architecture. Dependencies flow strictly inward. Business logic never lives in API routers.

### Layer Descriptions

| Layer | Responsibility | Key Modules |
|---|---|---|
| **API Layer** | HTTP routing, request/response serialization, input validation | `routers/documents.py`, `routers/chat.py`, `routers/system.py` |
| **Service Layer** | Orchestrates use cases, owns transaction boundaries | `services/ingestion_service.py`, `services/query_service.py` |
| **Agent Layer** | LangGraph graph definition, node implementations, state machine | `agents/rag_graph.py`, `agents/state.py`, `agents/nodes/` |
| **RAG Layer** | Chunking, embedding, context string assembly | `rag/chunker.py`, `rag/embedder.py`, `rag/retriever.py`, `rag/assembler.py` |
| **Database Layer** | Qdrant client wrapper, collection management, CRUD | `db/qdrant_repository.py`, `db/document_repository.py` |
| **Core Layer** | Settings, logging, exceptions, shared domain models, prompt templates | `core/config.py`, `core/logging.py`, `core/exceptions.py`, `core/models.py`, `core/prompts.py` |

### Dependency Rule

```
API → Service → Agent → RAG → Database → Core
         │                └──────────────────┘
         │                  (RAG calls Database directly)
         │
         └── Ingestion path: Service → RAG → Database
             Query path:     Service → Agent → RAG + Database
```

**Important clarification:** Ingestion does not pass through the Agent Layer. The Agent Layer is used only for query answering. This asymmetry is intentional — ingestion is a deterministic pipeline with no reasoning required. Forcing ingestion through LangGraph would add unnecessary complexity.

External services (Ollama, Qdrant) are accessed only through the Database Layer and RAG Layer. No higher layer imports a client directly.

### Responsibility Boundary: RAG Layer vs. Agent `cite` Node

This boundary is a common source of confusion and must be enforced consistently:

- `rag/assembler.py` — builds the **context string** passed to the LLM prompt. It selects which chunks to include, enforces the token budget, and formats them as a single string. It does not produce `Citation` objects.
- `agents/nodes/cite.py` — builds the **`Citation` response objects** from chunk metadata. It operates on the same retrieved chunks but produces the structured data returned to the API caller.

These are different operations on the same input data. Keeping them separate ensures the LLM prompt context and the API citation response can evolve independently.

---

## 3. Data Flows

### 3.1 Ingestion Flow (per document)

Ingestion is triggered as a FastAPI `BackgroundTask`. The HTTP response returns `202 Accepted` immediately. The client polls `GET /v1/documents/{id}` for status updates.

**CPU-bound work note:** PDF text extraction (pdfplumber) is CPU-bound. It must run via `asyncio.run_in_executor(thread_pool)` to avoid blocking the async event loop for concurrent API requests.

```
POST /v1/documents/upload
  │
  ▼  (immediate response: 202 + document_id)
  │
  └──► BackgroundTask: IngestionService.process(document_id)
          │
          ▼
      [1] Validate
          • MIME type check via magic bytes (first 5 bytes match b'%PDF-')
          • File size check (≤ MAX_UPLOAD_SIZE_MB)
          • Duplicate detection via SHA-256 content hash
            → if hash already in registry: return existing document_id, skip processing
          │
          ▼
      [2] Persist raw file
          • Save to ./uploads/{document_id}.pdf
          • Write DocumentRecord{status=PROCESSING} to DocumentRepository
          │
          ▼
      [3] Extract text  [run_in_executor — CPU-bound]
          • PDF → pages → raw text via pdfplumber
          • Clean: normalize whitespace, strip form feeds
          • Detect failure modes:
            → Password-protected PDF → status=FAILED, error="password_protected"
            → Zero text extracted   → status=FAILED, error="no_text_layer"
          │
          ▼
      [4] Chunk  [run_in_executor — CPU-bound]
          • Strategy: RecursiveCharacterTextSplitter
          • chunk_size: 1024 characters  (≈ 256 tokens; configurable)
          • chunk_overlap: 128 characters (configurable)
          • IMPORTANT: chunk_size is in CHARACTERS, not tokens.
            LangChain's RecursiveCharacterTextSplitter counts characters by default.
            Approximate conversion: 4 characters ≈ 1 token.
          • Deterministic chunk_id: sha256(document_id + ":" + str(chunk_index))[:16]
            This ensures re-ingestion upserts correctly rather than duplicating vectors.
          • Metadata attached per chunk: document_id, filename, page_number, chunk_index
          │
          ▼
      [5] Embed (batched)
          • Batch size: 32 chunks per Ollama call (EMBEDDING_BATCH_SIZE, configurable)
          • Model: nomic-embed-text → 768 dimensions
          • Concurrency: sequential batches for MVP; async batches in Phase 5
          • On Ollama timeout: retry once, then mark document FAILED
          │
          ▼
      [6] Store
          • Upsert vectors + payloads to Qdrant collection
          • Upsert key: chunk_id (deterministic, enables idempotent re-ingestion)
          • On Qdrant failure: log error, mark document FAILED, do NOT leave partial state
            → Cleanup: delete any vectors already inserted for this document_id
          • Update DocumentRecord{status=READY, chunk_count=N}
          │
          ▼
      Status visible at GET /v1/documents/{document_id}
```

### 3.2 Query Flow (per question — latency critical)

```
POST /v1/chat/query
  │
  ▼
[1] Validate question
    • Non-empty string
    • Max length: 1000 characters (configurable)
    • Basic prompt injection screening (see Section 17)
  │
  ▼
[2] Inject request_id into context
    • Generate UUID for this query (or accept X-Request-ID header)
    • Thread through all log statements for correlation
  │
  ▼
[3] Invoke LangGraph RAG graph
    │
    ├──[Node: retrieve]  (deterministic)
    │   • Embed question via Ollama nomic-embed-text
    │   • Vector search in Qdrant:
    │     - top_k from request (default: 5, configurable)
    │     - distance metric: Cosine (must match collection configuration)
    │     - optional document_id filter (if request specifies a document scope)
    │   • Filter by score_threshold (default: 0.6; treat as hyperparameter, not constant)
    │   • If 0 chunks pass threshold → conditional edge to END
    │     Return: { answer: "No relevant documents found.", citations: [] }
    │   • Log: retrieved_count, filtered_count, top_score, min_score, request_id
    │
    ├──[Node: assemble]  (deterministic)
    │   • Sort chunks by score descending
    │   • Count characters (not tokens) per chunk using len(text)
    │   • Convert budget: MAX_CONTEXT_TOKENS × 4 characters (4 chars ≈ 1 token)
    │   • Truncate chunks from lowest score end until budget satisfied
    │   • Format context string from templates in core/prompts.py
    │   • Log: chunks_included, chunks_dropped, context_char_count
    │
    ├──[Node: generate]  (LLM-powered)
    │   • Fill RAG prompt template with question + assembled context
    │   • Call Ollama llama3.2:3b
    │   • On Ollama failure: set state.error, route to END with error response
    │   • Log: generation_latency_ms, request_id
    │
    └──[Node: cite]  (deterministic)
        • Build Citation objects from retrieved_chunks metadata
        • Sort citations by relevance_score descending
        • Attach to final response
  │
  ▼
Response: {
  answer: str,
  citations: list[Citation],
  retrieval_count: int,
  context_chunks_used: int,
  latency_ms: float,
  request_id: str
}
```

---

## 4. LangGraph Agent Design

### 4.1 Graph State

The LangGraph state is a `TypedDict` passed between nodes. All nodes read from and write to this state.

**Design decision — no parallel score list:** An earlier design had `retrieval_scores: list[float]` as a separate field alongside `retrieved_chunks`. This creates a data coherence risk: if any node reorders or filters `retrieved_chunks` without maintaining the parallel list, scores become meaningless. Scores are stored inside `RetrievedChunk.score`. There is no parallel list.

```python
class RAGState(TypedDict):
    # Inputs
    question: str
    top_k: int
    score_threshold: float
    document_id_filter: str | None   # Optional: restrict search to one document
    request_id: str

    # Retrieval outputs (score is on each chunk object — no parallel list)
    retrieved_chunks: list[RetrievedChunk]

    # Assembly outputs
    assembled_context: str
    context_char_count: int
    chunks_included: int

    # Generation outputs
    raw_answer: str

    # Citation outputs
    citations: list[Citation]
    final_answer: str

    # Control
    error: str | None
```

### 4.2 Nodes

| Node | Type | Responsibility | External calls |
|---|---|---|---|
| `retrieve` | Deterministic | Embed question, vector search, threshold filter, document filter | Ollama (embed), Qdrant (search) |
| `assemble` | Deterministic | Sort by score, enforce char budget, format context string | None |
| `generate` | LLM-powered | Fill prompt template, call LLM, return raw answer | Ollama (LLM) |
| `cite` | Deterministic | Build Citation objects from chunk metadata | None |

**Why 4 nodes, not 3:** The original design merged assembly and generation into a single `generate` node. This is wrong for two reasons. First, assembly is deterministic — it can be unit tested without any LLM mock. Second, merging assembly into the LLM node makes it impossible to inspect what context the LLM received when debugging poor answer quality. Separating `assemble` and `generate` gives full observability into both the input and output of the LLM call.

### 4.3 Graph Edges

```
START → retrieve ──(0 chunks)──────────────────────► END
            │
            └──(≥1 chunk)──► assemble → generate ──(error)─► END
                                             │
                                             └──(ok)──► cite → END
```

Conditional edges:
- After `retrieve`: if `len(retrieved_chunks) == 0` → END with "no relevant documents" response
- After `generate`: if `state["error"] is not None` → END with error response

### 4.4 Design Principles Applied

- No LLM calls inside `retrieve`, `assemble`, or `cite` nodes.
- The compiled graph is a singleton, created once at application startup via FastAPI lifespan and reused across all requests.
- Graph state is treated as immutable between nodes — each node returns a partial state update dict, never mutates the input.
- Every node accepts its external clients as injected arguments. No node imports a client at module level. This is the only pattern that makes the graph unit-testable without network access.

---

## 5. Folder Structure

```
industrial-rag-platform/
├── app/
│   ├── main.py                         # FastAPI app factory, lifespan handler
│   ├── api/
│   │   ├── v1/
│   │   │   ├── routers/
│   │   │   │   ├── documents.py        # /v1/documents endpoints
│   │   │   │   ├── chat.py             # /v1/chat/query endpoint
│   │   │   │   └── system.py           # /v1/health/live, /v1/health/ready, /v1/metrics
│   │   │   └── __init__.py
│   │   └── dependencies.py             # FastAPI DI providers (clients, services, graph)
│   ├── services/
│   │   ├── ingestion_service.py
│   │   └── query_service.py
│   ├── agents/
│   │   ├── rag_graph.py                # Graph builder and compiled graph accessor
│   │   ├── state.py                    # RAGState TypedDict
│   │   └── nodes/
│   │       ├── retrieve.py
│   │       ├── assemble.py
│   │       ├── generate.py
│   │       └── cite.py
│   ├── rag/
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   ├── retriever.py
│   │   └── assembler.py
│   ├── db/
│   │   ├── qdrant_client.py            # Client factory (singleton via DI)
│   │   ├── qdrant_repository.py        # Vector CRUD
│   │   └── document_repository.py      # Document metadata CRUD
│   └── core/
│       ├── config.py                   # Pydantic BaseSettings
│       ├── logging.py                  # Structured JSON logging setup
│       ├── exceptions.py               # Custom exception hierarchy
│       ├── models.py                   # Shared Pydantic domain models
│       └── prompts.py                  # All prompt templates as constants
├── evaluation/
│   ├── datasets/
│   │   └── industrial_qa.json          # Benchmark Q&A in RAGAS format
│   ├── run_ragas.py                    # Evaluation entry point
│   └── metrics.py                      # Metric reporting utilities
├── tests/
│   ├── unit/
│   │   ├── test_chunker.py
│   │   ├── test_embedder.py
│   │   ├── test_assembler.py
│   │   └── test_nodes.py               # LangGraph node tests (mocked clients)
│   ├── integration/
│   │   ├── test_ingestion.py           # Tests against live Qdrant + Ollama
│   │   └── test_query.py
│   └── conftest.py
├── scripts/
│   ├── pull_models.sh                  # ollama pull llama3.2:3b && ollama pull nomic-embed-text
│   ├── seed_demo_data.py               # Upload sample industrial PDFs for demo
│   └── init_collection.py             # Create Qdrant collection with correct params
├── docs/
│   └── architecture/                   # Architecture diagrams (SVG sources)
├── uploads/                            # Raw uploaded files (gitignored)
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
├── .env.example
└── README.md
```

---

## 6. Data Models

### 6.1 Domain Models (`core/models.py`)

```python
# Document lifecycle status
class DocumentStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"

# Document registry entry
class DocumentRecord(BaseModel):
    document_id: str          # UUID
    filename: str
    file_hash: str            # SHA-256 for duplicate detection
    status: DocumentStatus
    chunk_count: int          # 0 until READY
    upload_timestamp: datetime
    file_size_bytes: int
    error_message: str | None  # Populated on FAILED status

# Chunk produced by the chunker
class DocumentChunk(BaseModel):
    chunk_id: str             # Deterministic: sha256(document_id + ":" + chunk_index)[:16]
    document_id: str
    text: str
    page_number: int
    chunk_index: int
    char_count: int           # len(text); used for context budget

# Qdrant payload schema (stored alongside each vector)
class ChunkPayload(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page_number: int
    chunk_index: int
    text: str

# Retrieval result (score from Qdrant, rest from payload)
class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    score: float              # Cosine similarity score [0, 1]
    document_id: str
    filename: str
    page_number: int
    chunk_index: int

# Citation in API response
class Citation(BaseModel):
    document_name: str
    page_number: int
    chunk_index: int
    relevance_score: float
```

### 6.2 API Request/Response Models

```python
# POST /v1/documents/upload response
class UploadResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    message: str

    model_config = ConfigDict(
        json_schema_extra={"example": {
            "document_id": "a3f2...",
            "status": "PENDING",
            "message": "Document accepted for processing."
        }}
    )

# GET /v1/documents response
class DocumentListResponse(BaseModel):
    documents: list[DocumentRecord]
    total: int
    page: int
    page_size: int

# POST /v1/chat/query request
class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    score_threshold: float = 0.6   # Hyperparameter — tune against eval dataset
    document_id: str | None = None  # Optional: restrict search to one document

    model_config = ConfigDict(
        json_schema_extra={"example": {
            "question": "What is the recommended torque for bolt assembly?",
            "top_k": 5,
            "score_threshold": 0.6
        }}
    )

# POST /v1/chat/query response
class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieval_count: int
    context_chunks_used: int
    latency_ms: float
    request_id: str
```

---

## 7. API Contract

All routes are prefixed with `/v1`. This enables non-breaking API evolution in future.

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/documents/upload` | Upload PDF, trigger async ingestion; returns 202 |
| `GET` | `/v1/documents` | List documents with status; supports `?page=` and `?page_size=` |
| `GET` | `/v1/documents/{document_id}` | Get document details, status, and error message if failed |
| `DELETE` | `/v1/documents/{document_id}` | Delete document, its vectors from Qdrant, and its raw file |
| `POST` | `/v1/chat/query` | Ask a question; optionally scope to a single document |
| `GET` | `/v1/health/live` | Liveness probe: is the process alive? Returns 200 always |
| `GET` | `/v1/health/ready` | Readiness probe: are all dependencies reachable and initialised? |
| `GET` | `/v1/metrics` | Runtime counters (documents ingested, queries answered, avg latency) |

**FastAPI auto-generates OpenAPI docs at `/docs`.** All Pydantic request/response models must include `json_schema_extra` examples so the Swagger UI shows realistic values.

---

## 8. Configuration Strategy

All model names, service URLs, chunking parameters, and retrieval settings are driven by environment variables. Nothing is hardcoded.

**Implementation:** Pydantic `BaseSettings` in `core/config.py`. `.env` file in development; environment variables injected in Docker Compose.

```
# Service URLs
OLLAMA_BASE_URL=http://ollama:11434
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_GRPC_PORT=6334

# Models
LLM_MODEL=llama3.2:3b
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768

# Qdrant collection
QDRANT_COLLECTION_NAME=documents
QDRANT_DISTANCE_METRIC=Cosine      # Must match nomic-embed-text training

# Chunking (character-based)
CHUNK_SIZE_CHARS=1024               # NOT tokens — RecursiveCharacterTextSplitter counts chars
CHUNK_OVERLAP_CHARS=128

# Retrieval
DEFAULT_TOP_K=5
RELEVANCE_SCORE_THRESHOLD=0.6       # Hyperparameter — tune via evaluation pipeline
MAX_CONTEXT_CHARS=8192              # ≈ 2048 tokens at 4 chars/token

# Embedding
EMBEDDING_BATCH_SIZE=32

# Ingestion
MAX_UPLOAD_SIZE_MB=50
UPLOAD_DIR=./uploads
INGESTION_CONCURRENCY=2             # Max simultaneous background ingestion jobs

# Application
APP_ENV=development
LOG_LEVEL=INFO
LOG_FORMAT=json                     # json in production, text in development
```

---

## 9. Docker Compose Topology

Three services are required for a complete local deployment.

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│   app       │────►│   ollama     │     │   qdrant       │
│  FastAPI    │     │  :11434      │     │  REST: :6333   │
│  :8000      │     │              │     │  gRPC: :6334   │
└─────────────┘     └──────────────┘     └────────────────┘
      │                                          ▲
      └──────────────────────────────────────────┘

Volumes:
  qdrant_data   → /qdrant/storage   (vector index persistence)
  ollama_data   → /root/.ollama     (downloaded model weights)
  uploads       → /app/uploads      (raw uploaded PDFs)
```

**Service startup order:**
1. `qdrant` starts first (no dependencies)
2. `ollama` starts and runs model pull entrypoint (`scripts/pull_models.sh`)
3. `app` starts only after both `qdrant` and `ollama` healthchecks pass

**Qdrant API:** The Python client uses the gRPC port (6334) by default for better performance. REST (6333) is available for manual inspection via curl or the Qdrant Web UI.

**Ollama model pull:** On first run, `scripts/pull_models.sh` is executed as part of the Ollama container entrypoint. It pulls `llama3.2:3b` and `nomic-embed-text`. Subsequent starts skip this if the models already exist in the volume.

**Collection initialization:** On `app` startup, `scripts/init_collection.py` checks whether the Qdrant collection exists with the correct parameters:
- If not exists → create with `vector_size=EMBEDDING_DIMENSIONS`, `distance=Cosine`
- If exists with wrong dimensions → raise startup error (operator must resolve manually)
- If exists with correct parameters → proceed

---

## 10. Gap Analysis

The following gaps existed in the initial architecture diagrams. All have been resolved in this document.

### 10.1 Missing: Core/Config Layer

**Problem:** No configuration layer. Model names, URLs, and parameters would be scattered as constants.

**Resolution:** Pydantic `BaseSettings` in `core/config.py`. All modules import from there. Documented in Section 8.

---

### 10.2 Missing: Raw File Storage

**Problem:** Ingestion flow showed no raw file persistence path.

**Resolution:** Raw files saved to `./uploads/{document_id}.pdf` immediately after validation. File path stored in `DocumentRecord`. Enables re-processing without re-upload.

---

### 10.3 Missing: Async Ingestion + Event Loop Safety

**Problem (v1):** Ingestion was marked as a `BackgroundTask` but no mention of the event loop blocking risk.

**Resolution:** CPU-bound steps (pdfplumber extraction, chunking) run via `asyncio.run_in_executor(thread_pool)`. The async event loop is never blocked by CPU work. A concurrency semaphore (`INGESTION_CONCURRENCY`) caps simultaneous background jobs.

---

### 10.4 Missing: Thread-Safe Document Registry

**Problem (v1):** A module-level Python dict was proposed for MVP. Python dicts are not thread-safe under concurrent BackgroundTask writes.

**Resolution:** Use **SQLite via SQLModel** for the document registry in MVP. SQLite requires minimal infrastructure overhead (no extra Docker service), is persistent across restarts, is safe for concurrent writes, and is a realistic upgrade path to PostgreSQL. The `DocumentRepository` class abstracts the storage backend.

**Why not a plain dict:** Two simultaneous uploads → two BackgroundTasks writing to the same dict → race condition. SQLite's write serialization prevents this at no real cost for a portfolio project.

---

### 10.5 Missing: LangGraph State Schema

**Problem:** Agent layer described as "3 nodes" with no state definition.

**Resolution:** `RAGState` TypedDict fully defined in Section 4.1. Four named nodes. Conditional edges documented. Parallel score list eliminated.

---

### 10.6 Missing: Character vs. Token Budget Precision

**Problem (v1):** The document specified "chunk_size: 512 tokens" but LangChain's `RecursiveCharacterTextSplitter` counts characters by default. Using `chunk_size=512` would yield chunks of ~128 tokens — far too small. Additionally, `tiktoken` (an OpenAI library) was proposed for token counting in a project that uses no OpenAI services.

**Resolution:**
- Chunk size is specified in **characters**: `CHUNK_SIZE_CHARS=1024` (≈ 256 tokens)
- Context budget uses a conservative character approximation: 4 chars ≈ 1 token
- No `tiktoken` dependency. This avoids a confusing OpenAI dependency in an open-source stack.
- The approximation is documented and acknowledged in config comments.

---

### 10.7 Missing: Relevance Score Threshold as Hyperparameter

**Problem (v1):** `score_threshold=0.6` was presented as a fixed constant.

**Resolution:** `score_threshold` is a configurable parameter and an explicit hyperparameter. The correct value depends on the embedding model, the document domain, and the query distribution. It must be tuned using the RAGAS evaluation pipeline (Phase 4). The default of `0.6` is a reasonable starting point for cosine similarity with nomic-embed-text, not a guaranteed optimal value.

---

### 10.8 Missing: Deterministic Chunk IDs

**Problem:** If chunk IDs are random UUIDs, re-ingesting the same document creates duplicate vectors in Qdrant instead of updating existing ones.

**Resolution:** Chunk IDs are deterministic: `sha256(document_id + ":" + str(chunk_index))[:16]`. Re-ingestion of the same document upserts correctly. The `document_id` itself is derived from the file SHA-256 hash (see Section 3.1 duplicate detection), making the entire ID chain deterministic from content.

---

### 10.9 Missing: Qdrant Distance Metric Specification

**Problem:** The architecture never specified which Qdrant distance metric to use. Qdrant supports Cosine, Dot, and Euclidean. Using the wrong metric produces silently incorrect rankings.

**Resolution:** Use `Cosine` distance. nomic-embed-text was trained with InfoNCE contrastive loss, which optimizes for cosine similarity between embeddings. The collection is created with `distance=Distance.COSINE`. This is hardened by the `QDRANT_DISTANCE_METRIC` config variable.

---

### 10.10 Missing: Partial Ingestion Cleanup

**Problem:** If embedding succeeds for N chunks but Qdrant storage fails on chunk N+1, the document is marked FAILED but N vectors remain in Qdrant. On retry, those N vectors are duplicated.

**Resolution:** On any storage failure during ingestion:
1. Mark document status as `FAILED`
2. Delete all vectors with `document_id == this_document_id` from Qdrant
3. Log the cleanup action

Because chunk_ids are deterministic, a retry after cleanup produces the same chunk_ids and upserts cleanly.

---

### 10.11 Missing: Health Probe Separation

**Problem (v1):** A single `/health` endpoint checked external connectivity. In Kubernetes, a liveness probe that fails because Qdrant is temporarily unreachable causes the pod to restart — which then also can't reach Qdrant — creating a restart loop.

**Resolution:** Two endpoints:
- `GET /v1/health/live` — liveness probe. Returns 200 always if the process is running. Never checks external services.
- `GET /v1/health/ready` — readiness probe. Checks Ollama reachability, Qdrant reachability, and Qdrant collection existence. Returns 200 if ready, 503 if degraded. Removes the pod from load balancer rotation when degraded.

---

### 10.12 Missing: Document-Level Query Scoping

**Problem:** The query flow had no way to restrict retrieval to a specific document.

**Resolution:** `QueryRequest.document_id` is an optional filter passed to the Qdrant search as a payload filter. This uses Qdrant's native filtering capability with no performance penalty when an index is defined on the `document_id` payload field.

---

### 10.13 Missing: RAGAS Dataset Schema

**Problem (v1):** The evaluation layer mentioned "a JSON file of Q&A triples" without specifying the RAGAS-required schema.

**Resolution:** The benchmark dataset at `evaluation/datasets/industrial_qa.json` must conform to the RAGAS evaluation schema:

```json
[
  {
    "question": "What is the maximum operating temperature?",
    "answer": "",
    "contexts": [],
    "ground_truth": "The maximum operating temperature is 85°C as specified in section 4.2."
  }
]
```

- `question` — the query sent to the RAG pipeline
- `answer` — filled in at evaluation time by running the question through the live pipeline
- `contexts` — filled in at evaluation time with the retrieved chunks
- `ground_truth` — the human-verified correct answer; used for faithfulness and recall scoring

---

### 10.14 Missing: API Versioning

**Problem:** All routes lacked a version prefix.

**Resolution:** All routes prefixed with `/v1`. FastAPI router includes: `router = APIRouter(prefix="/v1")`. Future breaking changes deploy under `/v2` without removing `/v1`.

---

### 10.15 Missing: Pagination on Collection Endpoints

**Problem:** `GET /documents` had no pagination. With 1000 documents, this returns an unbounded response.

**Resolution:** `GET /v1/documents` accepts `?page=1&page_size=20`. Response includes `total`, `page`, `page_size`. Default page_size is 20, maximum is 100.

---

## 11. Scalability Concerns

Known limitations of the MVP architecture with documented upgrade paths.

| Concern | Current (MVP) | Production Upgrade |
|---|---|---|
| Ollama handles both embedding and generation | Single instance; large ingestion blocks queries | Separate Ollama instances for embed vs. LLM, or switch to vLLM |
| Ingestion concurrency | Semaphore-capped BackgroundTasks (default: 2 parallel jobs) | Celery + Redis task queue |
| Document registry | SQLite | PostgreSQL with SQLAlchemy async |
| Single Qdrant collection | All documents in one collection | Per-user or per-project collections with tenant isolation |
| Local file storage | `./uploads/` on container filesystem | MinIO or S3-compatible object storage |
| No rate limiting | All requests processed | API rate limiter via `slowapi` middleware |
| Context assembly | Character approximation for token budget | Exact token counting via model-specific tokenizer |
| No connection pooling | New Qdrant client per request | Singleton client with connection pool via DI |

---

## 12. AI Engineering Concerns

### 12.1 Chunking Strategy

**Decision:** `RecursiveCharacterTextSplitter` with `chunk_size=1024 chars` and `chunk_overlap=128 chars`.

**Rationale:**
- Recursive splitting respects paragraph → sentence → word boundaries in order
- 1024 characters ≈ 256 tokens, well within nomic-embed-text's 8192-token input limit
- 128-character overlap ≈ 32 tokens, sufficient to preserve cross-boundary context
- Character-based counting is exact and has no tokenizer dependency

**Known limitation:** This is positional chunking, not semantic chunking. A paragraph that spans a section boundary gets split mid-thought. Semantic chunking (split at topic changes using a fast model) would improve retrieval quality. Deferred to Phase 5.

### 12.2 Embedding Model and Collection Contract

**Risk:** nomic-embed-text produces 768-dimensional vectors. Creating the Qdrant collection with any other dimension causes all inserts to fail.

**Mitigation:**
- `EMBEDDING_DIMENSIONS=768` in config
- Collection created with `vector_size=settings.EMBEDDING_DIMENSIONS`
- Startup check verifies collection dimension matches config
- `QDRANT_DISTANCE_METRIC=Cosine` locked to match nomic-embed-text's training objective

### 12.3 LLM Context Management

**Risk:** llama3.2:3b is a small model. Generation quality degrades with excessive context.

**Mitigation:**
- Cap context at `MAX_CONTEXT_CHARS=8192` (≈ 2048 tokens)
- Sort chunks by score descending; truncate from the bottom
- Log `context_char_count` and `chunks_included` per query for observability

### 12.4 Score Threshold Calibration

**Important:** `score_threshold=0.6` is a starting value, not a validated constant. The correct value depends on:
- The embedding model (nomic-embed-text scores have a specific distribution)
- The document domain (industrial documents have denser technical vocabulary than general text)
- The query distribution (short queries tend to score lower than full-sentence questions)

**Action required in Phase 4:** Run the RAGAS evaluation pipeline with multiple threshold values (0.4, 0.5, 0.6, 0.7) and select the value that maximizes context recall without sacrificing faithfulness.

### 12.5 Prompt Template Management

**Risk:** Hardcoded prompt strings inside node logic are untestable and fragile.

**Mitigation:** All prompt templates centralized in `core/prompts.py` as module-level constants. Node logic calls formatting functions, never builds strings directly. This also enables prompt versioning — A/B testing different prompts by changing a config value.

---

## 13. LangGraph Concerns

### 13.1 Graph Compilation and Lifecycle

The compiled graph is a singleton. It is created once during application startup via FastAPI lifespan and stored on `app.state`. All requests share the same compiled graph. This avoids re-compiling the graph on every request (which is expensive and unnecessary).

```python
# Pseudocode — in main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rag_graph = build_rag_graph(
        qdrant_repo=get_qdrant_repository(),
        embedder=get_embedder(),
        ollama_client=get_ollama_client(),
    )
    yield
    # Teardown: close clients
```

### 13.2 Node Testability by Design

Each node is a pure function: `(state, clients) → state_update`. External clients are passed in, never imported at module level. This is the only pattern that allows unit tests to mock Qdrant and Ollama with zero network access.

### 13.3 Graph Error Propagation

Error handling strategy:
- Each node catches its own exceptions
- Exceptions are stored in `state["error"]` as a string
- A conditional edge after `generate` checks `state["error"]` and routes to END
- The final response always has a defined shape — never raises an unhandled exception to the API caller

### 13.4 Graph Observability

LangGraph provides `graph.get_graph().draw_mermaid()` for visualizing the compiled graph. This should be used in development to verify the graph topology matches the design and is included as a documentation artifact.

### 13.5 Future: Conversation Memory

The graph is stateless (one question, one answer). LangGraph supports multi-turn conversation via `MemorySaver` (in-process) or `SqliteSaver` (persistent). This is intentionally deferred to Phase 5.

---

## 14. RAG Concerns

### 14.1 No Reranking (Known Gap)

Vector similarity does not equal semantic relevance for question answering. A chunk about "bolt torque specifications" may score lower than a chunk about "bolt materials" when the question is about torque.

**MVP decision:** Accept this. Vector search quality is sufficient for a working pipeline and a portfolio demonstration.

**Phase 5 upgrade:** Add a cross-encoder reranker (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) after the vector search step. Evaluate whether it improves the RAGAS context recall score before committing to the added latency.

### 14.2 No Query Rewriting (Known Gap)

Short, ambiguous, or domain-specific questions retrieve poorly against general-purpose embedding models.

**MVP decision:** Skip.

**Phase 5 upgrade:** Add an optional `rewrite` node in LangGraph before `retrieve`. Use the LLM to expand the question into a richer retrieval query. Measure the RAGAS improvement against the added latency cost.

### 14.3 Hybrid Search (Known Gap)

Pure dense vector search misses exact keyword matches — model numbers, part codes, regulatory identifiers, exact quoted text. Industrial documents contain heavy keyword content.

**MVP decision:** Skip. Qdrant natively supports hybrid search via sparse vectors (SPLADE or BM25).

**Phase 5 upgrade:** Enable Qdrant sparse vectors. Blend dense + sparse scores via Reciprocal Rank Fusion (RRF). Expected to significantly improve retrieval on industrial documents with high keyword density.

### 14.4 Citation Accuracy Dependency

Citations are built from chunk metadata. Citation accuracy depends entirely on the chunker correctly attaching `page_number` per chunk. A bug in the chunker that loses page metadata would produce citations with wrong page numbers.

**Mitigation:** Validate at ingestion time that every chunk has a non-null `page_number` before it is passed to the embedder. Fail loudly rather than store incomplete metadata.

---

## 15. Observability and Structured Logging

### 15.1 Structured Log Format

All log output is JSON-formatted in production (`LOG_FORMAT=json`). Text format in local development for readability.

Every log entry includes these standard fields:

```json
{
  "timestamp": "2026-06-12T14:32:01.234Z",
  "level": "INFO",
  "service": "industrial-rag",
  "module": "agents.nodes.retrieve",
  "request_id": "a3f2b1c0...",
  "message": "Retrieval complete",
  "retrieved_count": 8,
  "filtered_count": 5,
  "top_score": 0.812,
  "min_score": 0.643,
  "duration_ms": 142
}
```

### 15.2 Request Correlation

Every request gets a UUID `request_id`, either generated at the API layer or accepted via an `X-Request-ID` header. The `request_id` is:
- Attached to every log statement within that request's execution
- Returned in the query response body
- Available for cross-layer debugging without distributed tracing infrastructure

### 15.3 Per-Query Retrieval Logging

Every query logs the following retrieval statistics at INFO level:
- `retrieved_count` — chunks returned by Qdrant before filtering
- `filtered_count` — chunks remaining after threshold filter
- `chunks_included` — chunks that fit in the context budget
- `chunks_dropped` — chunks filtered by score or budget
- `top_score`, `min_score` — for threshold calibration analysis
- `context_char_count` — actual context size sent to LLM

These fields enable offline analysis of retrieval quality without instrumenting the evaluation pipeline separately.

### 15.4 Ingestion Event Logging

Each ingestion pipeline step logs its outcome and duration:
- Validation result (accepted / rejected + reason)
- Extraction: page count, char count, failure mode if any
- Chunking: chunk count, avg chunk size
- Embedding: batch count, total duration
- Storage: vectors upserted, any errors

### 15.5 Health and Metrics Endpoints

**`GET /v1/health/live`**
- Returns 200 always if the process is running
- No external checks
- Used as Kubernetes liveness probe

**`GET /v1/health/ready`**
- Checks: Ollama `/api/tags` reachable, Qdrant collection exists and accessible
- Returns 200 if all checks pass, 503 with failing service names if any fail
- Used as Kubernetes readiness probe

**`GET /v1/metrics`**
- Returns in-process counters:
  ```json
  {
    "documents_total": 42,
    "documents_ready": 39,
    "documents_failed": 3,
    "queries_total": 187,
    "queries_avg_latency_ms": 1840,
    "queries_p95_latency_ms": 3200
  }
  ```

---

## 16. API Design Standards

### 16.1 Versioning

All routes use `/v1` prefix. The FastAPI router is instantiated as:
```python
router = APIRouter(prefix="/v1", tags=["documents"])
```

This allows `/v2` routes to coexist with `/v1` during a migration period.

### 16.2 OpenAPI Documentation

FastAPI generates OpenAPI docs at `/docs` automatically. All Pydantic models must include:
- `model_config = ConfigDict(json_schema_extra={"example": {...}})` with realistic values
- Field-level `description` strings on all non-obvious fields

Interviewers and recruiters will navigate to `/docs` as the first inspection of the API. The Swagger UI should be immediately usable without reading the README.

### 16.3 Error Response Standard

All errors return a consistent shape:

```json
{
  "detail": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Document a3f2b1c0 does not exist.",
    "request_id": "a3f2b1c0..."
  }
}
```

Error codes are defined as an enum in `core/exceptions.py`. Never return raw exception messages to the caller.

### 16.4 HTTP Status Code Convention

| Situation | Status |
|---|---|
| Successful creation / accepted | 201 / 202 |
| Successful retrieval | 200 |
| Validation error | 422 (FastAPI default) |
| Not found | 404 |
| Duplicate document | 409 |
| Service unavailable (Ollama/Qdrant down) | 503 |
| Internal error | 500 |

---

## 17. Security Considerations

This is a local-only portfolio deployment with no public network exposure. The following considerations are documented for completeness and to demonstrate production awareness.

### 17.1 File Type Validation (Magic Bytes)

Extension-based file type checking is trivially bypassed by renaming a file. The validation step checks the first 5 bytes of the uploaded file against the PDF magic bytes (`b'%PDF-'`). Files that do not match are rejected with 422.

### 17.2 File Size Enforcement

Enforced at the FastAPI level via `MAX_UPLOAD_SIZE_MB` before the file is read into memory. Large files are rejected before any processing occurs.

### 17.3 Path Traversal Prevention

Raw files are saved as `./uploads/{document_id}.pdf` where `document_id` is a UUID generated by the server. User-supplied filenames are never used as filesystem paths. The original filename is stored only in the database record.

### 17.4 Prompt Injection Awareness

The `question` field in `QueryRequest` is user-controlled text that is inserted into an LLM prompt. Malicious inputs (e.g., "Ignore previous instructions and...") can manipulate the LLM output.

**MVP stance:** This is acknowledged and documented. No active guardrails are implemented in MVP.

**Phase 5 upgrade:** Add an input validation step that screens for common prompt injection patterns before the question reaches the LangGraph graph. Consider a guardrails library (e.g., `llm-guard`) for systematic protection.

### 17.5 Secrets Management

- No secrets are hardcoded
- `.env` is gitignored
- `.env.example` contains only placeholder values
- Docker Compose injects environment variables at runtime

---

## 18. Developer Experience

A portfolio project is evaluated both by what it does and by how easy it is to run. These elements are visible to any interviewer who clones the repo.

### 18.1 Makefile Targets

```makefile
make dev          # Start all Docker services in development mode
make build        # Build the app Docker image
make test         # Run full test suite
make test-unit    # Run unit tests only (no Docker required)
make lint         # Run ruff + black check
make format       # Run black formatter
make eval         # Run RAGAS evaluation pipeline
make demo         # Seed demo data and run example queries
make logs         # Tail app container logs
make clean        # Stop containers and remove volumes
```

### 18.2 Five-Minute Setup

The project must be runnable with three commands:

```bash
cp .env.example .env
make dev          # starts qdrant, ollama, pulls models, starts app
# navigate to http://localhost:8000/docs
```

The `make dev` target handles model pulling automatically. No manual Ollama setup required.

### 18.3 Demo Data

`scripts/seed_demo_data.py` uploads a set of sample industrial PDFs (e.g., publicly available equipment manuals, safety datasheets, engineering specifications). These enable a recruiter or interviewer to immediately query the system without needing to source their own documents.

`make demo` runs `seed_demo_data.py` and then executes 5 example queries, printing the answers and citations to the terminal.

### 18.4 Performance Benchmarking

`scripts/benchmark.py` runs a fixed set of 10 queries 3 times each and reports:
- p50 latency
- p95 latency
- average retrieval count
- average context chunks used

This verifies the PRD SLA of `< 5 seconds average response time` and provides a concrete number for the README.

### 18.5 README Structure

The README must include:
1. One-paragraph project description (for recruiters reading quickly)
2. Architecture diagram (the component SVG from `docs/architecture/`)
3. Five-minute quickstart
4. Example query and response (with real citations)
5. Technology stack table
6. Evaluation results table (RAGAS metrics against the benchmark dataset)
7. Architecture decisions section (explains why LangGraph, why 4 nodes, why Qdrant over alternatives)
8. Known limitations and upgrade paths

---

## 19. Deferred to Future Phases

Features explicitly out of scope for MVP and Phases 1–3. Documented here to record design intent and prevent premature implementation.

| Feature | Phase | Rationale for deferral |
|---|---|---|
| DOCX support | 5 | Requires separate extraction library (python-docx); add only after PDF pipeline is proven |
| TXT support | 5 | Trivial to add once PDF pipeline works; not portfolio-differentiating |
| Semantic chunking | 5 | Adds a second LLM pass at ingestion time; evaluate benefit vs. cost against RAGAS metrics |
| Reranking (cross-encoder) | 5 | Adds 200–500ms latency; justify with measured RAGAS improvement before adding |
| Query rewriting / HyDE | 5 | Requires extra LLM call per query; evaluate against RAGAS context recall improvement |
| Hybrid search (BM25 + dense) | 5 | High value for industrial keyword-dense documents; requires Qdrant sparse vector support |
| Multi-turn conversation | 5 | LangGraph checkpointing; changes state model significantly |
| Celery task queue | 5 | Replaces BackgroundTasks; needed only when concurrent ingestion load exceeds 2 jobs |
| PostgreSQL metadata store | 5 | Replaces SQLite; needed only when write throughput or query complexity exceeds SQLite limits |
| Object storage (MinIO/S3) | 5 | Replaces local filesystem; needed for multi-instance deployments |
| Authentication / API keys | 5 | Not required for local portfolio demo |
| Streaming responses | 5 | Ollama supports token streaming; changes API response model significantly |
| Prompt injection guardrails | 5 | `llm-guard` or similar; MVP acknowledges risk without active mitigation |
| LangGraph verification node | 3 | Fourth node that checks answer against retrieved context; add after basic 4-node graph works |
| RAGAS evaluation pipeline | 4 | Offline; does not block Phases 1–3; requires real query/answer pairs to be meaningful |

---

*Last updated: 2026-06-12*
*Architecture versions: v2 (staff review — design flaws corrected, observability, API standards, security, and developer experience added)*
*Reviewed against: PRD.md, CLAUDE.md, component architecture diagram, ingestion and query data flow diagram*
