# Project Roadmap
# Industrial Document Intelligence Platform

---

## Overview

This roadmap breaks the project into eight sequential phases. Each phase produces a vertically complete, working slice of the system — no phase ends with a partial pipeline.

**Guiding constraint:** A phase is not complete until its acceptance criteria all pass. Do not begin Phase N+1 until Phase N is fully working end-to-end.

| Phase | Name | Status | Description |
|---|---|---|---|
| 0 | Foundation | ✅ Complete | Project scaffold, tooling, infrastructure, empty app |
| 1 | Document Ingestion | ✅ Complete | PDF → chunks → embeddings → Qdrant |
| 2 | RAG Query Pipeline | ✅ Complete | Question → retrieval → generation → citations |
| 3 | LangGraph Agent | ✅ Complete | Migrate query pipeline to a stateful 4-node graph |
| 4 | Evaluation Pipeline | ✅ Complete | RAGAS metrics, benchmark dataset, threshold calibration |
| 5 | Production Hardening | ✅ Complete | Multi-format support (PDF/DOCX/TXT), README, portfolio polish |
| 6 | Web Frontend | ✅ Complete | ChatGPT-style React UI — upload documents, chat, view citations |
| 7 | Production Enhancements | 🔄 In Progress | Streaming responses, conversation memory, enhanced citations |

---

## Phase 0 — Foundation

### Goal

Establish the complete project skeleton before writing a single line of business logic. Every subsequent phase builds on this foundation. Getting this right once prevents rework across all later phases.

### Why This Phase Exists

Many engineers skip scaffolding and start with the "interesting" parts. The result is inconsistent structure, missing tooling, and a Docker setup that gets bolted on at the end. A recruiter cloning the repo on day one should be able to run `make dev` and see a healthy (empty) service — not a pile of unconnected scripts.

### Deliverables

- Fully configured Python project (`pyproject.toml`)
- Docker Compose environment with Qdrant and Ollama running
- Empty FastAPI application with lifespan, router registration, and dependency injection structure
- Configuration layer reading from environment variables
- Structured JSON logging configured globally
- Custom exception hierarchy
- Shared domain models skeleton
- Makefile with all development targets
- Test infrastructure with `conftest.py`
- `.env.example` documenting every required variable

### Files to Create

```
pyproject.toml
Makefile
Dockerfile
docker-compose.yml
.env.example
.gitignore

scripts/
  pull_models.sh
  init_collection.py

app/
  main.py
  api/
    v1/
      __init__.py
      routers/
        system.py          ← /v1/health/live, /v1/health/ready, /v1/metrics (stubs)
    dependencies.py
  core/
    config.py              ← Pydantic BaseSettings, all env vars
    logging.py             ← structlog or logging JSON formatter setup
    exceptions.py          ← DocumentNotFoundError, IngestionError, etc.
    models.py              ← DocumentStatus enum, DocumentRecord, stubs for others
    prompts.py             ← empty module, placeholder for Phase 2

tests/
  conftest.py              ← shared fixtures, test settings override
  unit/
    __init__.py
  integration/
    __init__.py
```

### Acceptance Criteria

- [ ] `make dev` starts all three Docker services (app, qdrant, ollama) without errors
- [ ] `GET /v1/health/live` returns `200 {"status": "ok"}` within 2 seconds of container start
- [ ] `GET /v1/health/ready` returns `200` when Qdrant and Ollama are up; returns `503` when either is unreachable
- [ ] `GET /v1/metrics` returns `200` with zero-value counters
- [ ] `GET /docs` renders the FastAPI Swagger UI with the system router endpoints visible
- [ ] `make test` runs the (empty) test suite and exits with code 0
- [ ] `make lint` passes with zero violations
- [ ] Qdrant Web UI accessible at `http://localhost:6333/dashboard`
- [ ] Ollama model list accessible via `curl http://localhost:11434/api/tags`
- [ ] `scripts/pull_models.sh` pulls both `llama3.2:3b` and `nomic-embed-text` without errors
- [ ] All environment variables are documented in `.env.example` with descriptions
- [ ] Application logs are JSON-formatted in Docker and human-readable in local dev

### Skills Demonstrated

- Python project configuration with `pyproject.toml` (not `setup.py`)
- Multi-service Docker Compose with healthcheck-based dependency ordering
- Pydantic Settings pattern for twelve-factor configuration
- Structured logging setup
- FastAPI application factory pattern with lifespan context
- Clean project structure before writing any domain logic

---

## Phase 1 — Document Ingestion Pipeline

### Goal

Build the complete path from PDF upload to vectors stored in Qdrant. By the end of this phase, a user can upload a PDF, watch it process, and confirm that embeddings are stored and retrievable in the Qdrant collection.

Query answering does not exist yet. This phase is purely the write path.

### Why This Phase Comes First

The retrieval pipeline in Phase 2 cannot be built or tested without vectors to retrieve. Getting the ingestion pipeline right — including deterministic chunk IDs, correct metadata, and idempotent upserts — prevents a class of subtle bugs that would otherwise be discovered only when retrieval produces wrong results.

### Deliverables

- `POST /v1/documents/upload` endpoint (returns 202, triggers background processing)
- `GET /v1/documents` endpoint with pagination
- `GET /v1/documents/{document_id}` endpoint (status polling)
- `DELETE /v1/documents/{document_id}` endpoint
- PDF validation via magic bytes
- SHA-256 duplicate detection
- pdfplumber text extraction with failure mode detection
- RecursiveCharacterTextSplitter chunking (character-based)
- Deterministic chunk ID generation
- Ollama embedding with configurable batch size
- Qdrant collection initialization on startup
- SQLite document registry via SQLModel
- Partial failure cleanup (vector deletion on ingestion error)
- Thread-safe ingestion via `run_in_executor` for CPU-bound steps
- Ingestion concurrency semaphore
- Unit tests for chunker and embedder
- Integration test for full ingestion pipeline

### Files to Create

```
app/
  api/
    v1/
      routers/
        documents.py       ← upload, list, get, delete endpoints

  services/
    ingestion_service.py   ← orchestrates the full ingestion pipeline

  rag/
    chunker.py             ← RecursiveCharacterTextSplitter wrapper
    embedder.py            ← Ollama embedding client, batched

  db/
    qdrant_client.py       ← client factory (singleton via DI)
    qdrant_repository.py   ← upsert_chunks, delete_by_document_id, collection_exists
    document_repository.py ← SQLite CRUD via SQLModel

  core/
    models.py              ← complete: DocumentRecord, DocumentChunk,
                              ChunkPayload, DocumentStatus
                              (add to what was stubbed in Phase 0)

tests/
  unit/
    test_chunker.py        ← chunk count, overlap, metadata attachment, char bounds
    test_embedder.py       ← batch size logic, output shape (mocked Ollama)
    test_document_repository.py ← CRUD operations on SQLite
  integration/
    test_ingestion.py      ← full pipeline: upload → status=READY, vectors in Qdrant

uploads/
  .gitkeep
```

### Acceptance Criteria

- [ ] `POST /v1/documents/upload` with a valid PDF returns `202` and a `document_id` within 500ms
- [ ] `GET /v1/documents/{document_id}` transitions through `PENDING → PROCESSING → READY`
- [ ] After processing, Qdrant contains vectors for every chunk; chunk count matches API response
- [ ] Each stored vector's payload contains: `document_id`, `filename`, `page_number`, `chunk_index`, `text`
- [ ] Re-uploading the same PDF returns the existing `document_id` (duplicate detection via SHA-256)
- [ ] Re-ingesting the same document upserts vectors rather than duplicating them (deterministic chunk IDs)
- [ ] Uploading a file with extension `.pdf` but non-PDF magic bytes returns `422`
- [ ] Uploading a file exceeding `MAX_UPLOAD_SIZE_MB` returns `422`
- [ ] Uploading a password-protected PDF sets status to `FAILED` with `error_message="password_protected"`
- [ ] Uploading a scan-only PDF (no text layer) sets status to `FAILED` with `error_message="no_text_layer"`
- [ ] `DELETE /v1/documents/{document_id}` removes the document record and all its vectors from Qdrant
- [ ] `GET /v1/documents` returns paginated results; `?page=2&page_size=5` works correctly
- [ ] Unit tests pass without requiring Docker (chunker and embedder use mocked clients)
- [ ] Integration test passes against live Qdrant and Ollama (`make test` with services running)
- [ ] Every chunk has a non-null `page_number` (validated before storage)
- [ ] Chunk IDs are deterministic: ingesting the same document twice produces identical chunk IDs
- [ ] `make lint` passes with zero violations

### Skills Demonstrated

- FastAPI background task pattern with status polling
- Async FastAPI with CPU-bound work safely offloaded to thread pool executor
- PDF text extraction with graceful failure handling
- RecursiveCharacterTextSplitter configuration (character-based, not token-based)
- Batch embedding against a local Ollama instance
- Qdrant Python client: collection creation, vector upsert, payload filtering
- SQLite + SQLModel for lightweight metadata persistence
- Content-addressed storage (SHA-256 deduplication)
- Deterministic ID generation for idempotent pipelines
- Unit testing with mocked external clients
- Integration testing against live services

---

## Phase 2 — RAG Query Pipeline

### Goal

Build the complete question-answering path. A user can submit a question and receive a grounded answer with citations pointing to specific pages and chunks in the source documents.

At the end of this phase, the system is a fully functional (non-agentic) RAG pipeline. LangGraph is not used yet — that comes in Phase 3. The query logic lives directly in `QueryService`.

### Why Build RAG Before LangGraph

LangGraph is an orchestration layer. Building a working RAG pipeline first means you understand exactly what each step does before wrapping it in a graph. When something breaks in Phase 3, you will be able to isolate whether the problem is in the graph wiring or in the underlying RAG logic — because you tested the RAG logic independently in Phase 2.

### Deliverables

- `POST /v1/chat/query` endpoint
- Question embedding via Ollama
- Qdrant vector search with configurable top-k and score threshold
- Optional document-level filtering (`document_id` parameter)
- Context assembly with character budget enforcement
- RAG prompt template in `core/prompts.py`
- LLM generation via Ollama
- Citation building from chunk metadata
- Complete `QueryResponse` with answer, citations, latency, and request_id
- Request correlation ID threading (generated at API layer, present in all logs)
- Per-query retrieval statistics logging
- Unit tests for retriever, assembler, and citation builder
- Integration test for full query pipeline

### Files to Create

```
app/
  api/
    v1/
      routers/
        chat.py            ← POST /v1/chat/query

  services/
    query_service.py       ← direct RAG pipeline: embed → retrieve → assemble → generate → cite

  rag/
    retriever.py           ← Qdrant search, threshold filter, document_id filter
    assembler.py           ← sort by score, char budget, context string formatting
    retriever.py

  core/
    models.py              ← add: RetrievedChunk, Citation, QueryRequest, QueryResponse
    prompts.py             ← RAG_SYSTEM_PROMPT, RAG_USER_TEMPLATE

tests/
  unit/
    test_retriever.py      ← threshold filter, document_id filter, score sorting (mocked Qdrant)
    test_assembler.py      ← budget enforcement, chunk ordering, edge case: 0 chunks
    test_citations.py      ← citation building from chunk metadata
  integration/
    test_query.py          ← full pipeline: question → answer with citations
```

### Acceptance Criteria

- [ ] `POST /v1/chat/query` returns a non-empty `answer` string for a question about an ingested document
- [ ] Response includes at least one citation with valid `document_name`, `page_number`, `chunk_index`
- [ ] Response includes `request_id`, `latency_ms`, `retrieval_count`, `context_chunks_used`
- [ ] Querying when no documents are ingested returns a graceful response: `"No relevant documents found."`
- [ ] Querying with `score_threshold=0.99` (effectively too high) returns the "no relevant documents" response
- [ ] Querying with `document_id` filter restricts retrieval to chunks from that document only
- [ ] `context_chunks_used` is always ≤ `retrieval_count` (assembly budget is respected)
- [ ] All log statements for a single query share the same `request_id`
- [ ] `request_id` in the response body matches the value in the logs
- [ ] Retrieved chunk scores in log match the scores in citation objects
- [ ] Unit tests pass without Docker (mocked Qdrant and Ollama clients)
- [ ] Integration test: ingest a known PDF, ask a question whose answer is on a known page, verify the citation page number is correct
- [ ] `GET /docs` Swagger UI shows `QueryRequest` and `QueryResponse` with realistic example values
- [ ] `make lint` passes with zero violations

### Skills Demonstrated

- RAG pipeline implementation end-to-end
- Semantic retrieval with configurable score thresholds
- Context window management (character budget, chunk selection strategy)
- Prompt engineering for a small open-source LLM (llama3.2:3b)
- Citation generation from retrieved metadata
- Request correlation IDs for distributed tracing
- Structured per-query observability logging
- Qdrant payload filtering for document-scoped search
- FastAPI Pydantic response models with OpenAPI examples

---

## Phase 3 — LangGraph Agent Integration

### Goal

Migrate the query pipeline from `QueryService`'s direct function calls into a compiled LangGraph state graph. The external behaviour (API inputs and outputs) does not change. The internal structure changes from a sequential function chain to an explicit, observable, testable state machine.

By the end of this phase, the query path runs through a 4-node LangGraph graph with typed state, conditional edges, and per-node error handling.

### Why Migrate to LangGraph (Not Just Keep Phase 2)

Phase 2 demonstrates RAG. Phase 3 demonstrates AI agent design — a separate and increasingly important skill. The difference is not what the system does, but how it's structured: explicit state, conditional routing, observable node execution, and the ability to add reasoning steps (reranking, verification, query rewriting) as independent nodes without rewriting the pipeline.

LangGraph is a portfolio-differentiating technology. Recruiters hiring AI Engineers in 2025–2026 specifically look for agentic workflow experience.

### Deliverables

- `RAGState` TypedDict in `agents/state.py`
- Four LangGraph nodes: `retrieve`, `assemble`, `generate`, `cite`
- Conditional edge: empty retrieval → early END
- Conditional edge: generation error → END with error response
- Compiled graph singleton created at startup via FastAPI lifespan
- `QueryService` migrated to invoke the compiled graph instead of direct function calls
- Graph visualization exported as a Mermaid diagram (`docs/architecture/rag_graph.md`)
- Node-level unit tests with injected mock clients
- Integration test verifying graph produces identical output to Phase 2 pipeline
- Graph error handling: Ollama failure populates `state.error` and returns structured error

### Files to Create

```
app/
  agents/
    __init__.py
    state.py               ← RAGState TypedDict (complete definition)
    rag_graph.py           ← build_rag_graph(), returns compiled StateGraph
    nodes/
      __init__.py
      retrieve.py          ← node function: embed + search + filter
      assemble.py          ← node function: sort + budget + format context
      generate.py          ← node function: prompt fill + Ollama LLM call
      cite.py              ← node function: build Citation objects

  services/
    query_service.py       ← updated: replace direct calls with graph.invoke()

  main.py                  ← updated: add graph compilation to lifespan

docs/
  architecture/
    rag_graph.md           ← Mermaid diagram from graph.get_graph().draw_mermaid()

tests/
  unit/
    test_nodes.py          ← one test class per node; all use injected mock clients
      test_retrieve_node   ← correct filtering, 0-chunk conditional path
      test_assemble_node   ← budget enforcement, empty chunks handling
      test_generate_node   ← prompt construction, error state on Ollama failure
      test_cite_node       ← citation object structure, ordering by score
  integration/
    test_graph.py          ← compile graph, invoke with real services, verify output shape
```

### Acceptance Criteria

- [ ] `POST /v1/chat/query` produces the same answer quality as Phase 2 (no regression)
- [ ] All response fields (`answer`, `citations`, `request_id`, `latency_ms`) remain present and correct
- [ ] If Ollama is unreachable during generation, the API returns a structured error response with status `503` rather than a 500 traceback
- [ ] If retrieval returns 0 chunks above threshold, the graph terminates at the `retrieve` node and returns `"No relevant documents found."` — the `generate` node is never called
- [ ] `state.error` is populated when any node raises an exception; it propagates cleanly to the API response
- [ ] Each node unit test passes without any Docker service running
- [ ] `test_retrieve_node` verifies that chunks below `score_threshold` are excluded from state
- [ ] `test_assemble_node` verifies that `context_char_count` never exceeds `MAX_CONTEXT_CHARS`
- [ ] `test_generate_node` verifies that the prompt passed to Ollama contains the assembled context and the question
- [ ] `test_cite_node` verifies that citation count equals `chunks_included` from assembly
- [ ] `docs/architecture/rag_graph.md` contains a valid rendered Mermaid diagram showing all 4 nodes and both conditional edges
- [ ] Graph is compiled once at startup; `make logs` shows "RAG graph compiled" at INFO level during startup
- [ ] `make lint` passes with zero violations

### Skills Demonstrated

- LangGraph `StateGraph` compilation and invocation
- Typed state design with `TypedDict`
- Conditional edge routing (empty retrieval → early exit; error → error exit)
- Node isolation: each node is a pure function of state + injected clients
- LangGraph graph compiled as singleton at startup (FastAPI lifespan pattern)
- Testability by design: mock injection, no module-level client imports
- Graph visualization and documentation
- Graceful error propagation through a state machine
- Non-regression testing: LangGraph migration produces identical outputs to direct pipeline

---

## Phase 4 — Evaluation Pipeline

### Goal

Build an offline, reproducible evaluation pipeline that measures RAG quality against a fixed benchmark dataset using RAGAS metrics. Use the results to validate the pipeline is working and to calibrate the `score_threshold` hyperparameter.

By the end of this phase, running `make eval` produces a RAGAS metrics report showing Faithfulness, Context Recall, and Answer Relevancy scores, with the results committed to the repository.

### Why Evaluation Matters for Portfolios

Evaluation is the clearest differentiator between a demo project and an engineering project. Any tutorial can build a RAG chatbot. Almost none benchmark it. Including measured evaluation results — and the pipeline that produced them — demonstrates production-engineering thinking that most candidates cannot demonstrate.

It also answers the question every interviewer eventually asks: *"How do you know your RAG system is working?"*

### Deliverables

- Benchmark dataset in RAGAS format (`evaluation/datasets/industrial_qa.json`)
- At least 20 question/ground_truth pairs covering the demo documents
- RAGAS evaluation runner that queries the live pipeline and scores results
- Metrics reporting utility with formatted output table
- RAGAS results file committed to the repository (`evaluation/results/baseline.json`)
- Threshold sensitivity analysis: run eval at 0.4, 0.5, 0.6, 0.7 and record results
- Documented threshold recommendation based on evaluation results
- Updated README with evaluation results table

### Files to Create

```
evaluation/
  datasets/
    industrial_qa.json     ← ≥20 {question, ground_truth} pairs for demo documents

  results/
    .gitkeep               ← directory tracked; result files gitignored except baseline

  run_ragas.py             ← entry point: load dataset → query pipeline → score → report
  pipeline_client.py       ← HTTP client calling POST /v1/chat/query for each question
  metrics.py               ← RAGAS metric computation, results formatting, JSON output
  threshold_sweep.py       ← run eval at multiple threshold values, produce comparison table

scripts/
  seed_demo_data.py        ← upload demo PDFs (used to populate the system before eval)
```

### Dataset Requirements

Each entry in `industrial_qa.json` must follow the RAGAS evaluation schema:

```json
{
  "question": "What is the maximum operating temperature of the device?",
  "answer": "",
  "contexts": [],
  "ground_truth": "The maximum operating temperature is 85°C as specified in Section 4.2."
}
```

- `answer` and `contexts` are populated at evaluation time by `pipeline_client.py`
- `ground_truth` is human-authored from the source documents
- Questions should cover a range of difficulty: direct fact retrieval, multi-page synthesis, terminology lookup
- Include at least 3 questions that should return "no relevant documents" (out-of-scope questions)

### RAGAS Metrics Targets (from PRD)

| Metric | Target |
|---|---|
| Faithfulness | ≥ 0.80 |
| Context Recall | ≥ 0.75 |
| Answer Relevancy | ≥ 0.80 |

### Acceptance Criteria

- [ ] `make eval` runs end-to-end without errors when the system is running
- [ ] Output report displays Faithfulness, Context Recall, and Answer Relevancy scores
- [ ] Scores are persisted to `evaluation/results/baseline.json`
- [ ] `evaluation/datasets/industrial_qa.json` contains at least 20 question/ground_truth pairs
- [ ] `threshold_sweep.py` produces a comparison table across threshold values 0.4–0.7
- [ ] The recommended threshold value is documented with the supporting score data
- [ ] Out-of-scope questions return "No relevant documents found." (not hallucinated answers)
- [ ] `pipeline_client.py` uses the actual HTTP API, not internal Python imports (tests the full stack)
- [ ] Results file `evaluation/results/baseline.json` is committed to the repository
- [ ] README evaluation section displays the baseline scores in a formatted table
- [ ] Evaluation script is fully reproducible: same dataset + same running system = same scores within noise

### Skills Demonstrated

- RAGAS evaluation framework integration
- Benchmark dataset curation (domain-specific Q&A pairs)
- Offline evaluation pipeline design
- Hyperparameter calibration via systematic evaluation
- Reproducible benchmarking (committed results, fixed dataset)
- Distinguishing between "the pipeline works" and "the pipeline works well"
- RAGAS metric interpretation: Faithfulness (no hallucination), Context Recall (retrieval completeness), Answer Relevancy (response quality)

---

## Phase 5 — Production Hardening

### Goal

Bring the system to portfolio-complete quality. Add multi-format document support, complete observability, performance verification, demo tooling, and all documentation that makes the project legible to recruiters and interviewers without running the code.

### Why This Phase Is Not Optional

The gap between "it works on my machine" and "it looks production-ready to a hiring manager" is exactly what this phase closes. The technical heavy lifting is done by Phase 4. Phase 5 is about making the quality of that work visible.

A recruiter reviewing a GitHub repository spends approximately 90 seconds before deciding whether to pass it to an engineer. This phase determines what they see in those 90 seconds.

### Deliverables

**Multi-format support:**
- DOCX text extraction via `python-docx`
- TXT ingestion (direct text, no extraction library needed)
- Document type detection unified under a single `ExtractorFactory`
- Existing PDF pipeline unchanged

**Observability completeness:**
- p50 and p95 latency tracking in the metrics endpoint
- `GET /v1/metrics` returns complete counters (documents by status, query latency histogram)
- Structured log fields complete and consistent across all modules

**Performance verification:**
- `scripts/benchmark.py` runs 10 queries 3 times each, reports p50/p95
- Benchmark results committed to repository
- PRD SLA verified: average latency < 5 seconds

**Developer experience:**
- `make demo` seeds demo data and runs 5 example queries end-to-end
- `scripts/seed_demo_data.py` uploads sample industrial PDFs
- All Makefile targets work (`dev`, `test`, `test-unit`, `lint`, `format`, `eval`, `demo`, `clean`)

**Documentation:**
- `README.md` complete: overview, architecture diagram, quickstart, example output, stack table, evaluation results, architecture decisions, known limitations
- `docs/architecture/rag_graph.md` current and accurate
- `ARCHITECTURE.md` reflects final implementation (any deviations from plan documented)
- `ROADMAP.md` marked with completion dates

**Docker hardening:**
- Multi-stage Dockerfile: builder stage + minimal runtime stage
- `.dockerignore` excludes test files, `.env`, uploads
- Docker Compose `healthcheck` on all three services
- Volume mounts correct and persistent

### Files to Create / Modify

```
app/
  rag/
    chunker.py             ← updated: ExtractorFactory, DOCX extractor, TXT extractor
    extractors/
      __init__.py
      base.py              ← AbstractExtractor with extract(path) → list[PageText]
      pdf_extractor.py     ← pdfplumber implementation (moved from chunker.py)
      docx_extractor.py    ← python-docx implementation
      txt_extractor.py     ← plain text implementation
      factory.py           ← ExtractorFactory.for_file(path) → AbstractExtractor

scripts/
  benchmark.py             ← 10 queries × 3 runs, p50/p95 report, SLA check
  seed_demo_data.py        ← upload sample industrial PDFs for demo

docs/
  architecture/
    rag_graph.md           ← final Mermaid diagram (updated if graph changed)

README.md                  ← complete portfolio README (see Section 18.5 of ARCHITECTURE.md)
Dockerfile                 ← multi-stage build
.dockerignore
```

### Acceptance Criteria

**Multi-format:**
- [ ] `POST /v1/documents/upload` with a valid `.docx` file returns `202` and processes successfully
- [ ] `POST /v1/documents/upload` with a valid `.txt` file returns `202` and processes successfully
- [ ] Both formats produce retrievable, queryable chunks with correct `page_number` metadata (or `page_number=1` for TXT)
- [ ] Existing PDF ingestion continues to work without regression
- [ ] Uploading an unsupported format (`.xlsx`, `.pptx`) returns `422` with a clear error message

**Observability:**
- [ ] `GET /v1/metrics` reports `queries_p50_latency_ms` and `queries_p95_latency_ms`
- [ ] All log entries across all modules include `request_id` when in a request context
- [ ] `make logs` shows structured JSON in production mode, human-readable text in development mode

**Performance:**
- [ ] `scripts/benchmark.py` exits with code 0 when average latency < 5000ms (PRD SLA)
- [ ] Benchmark report committed to `evaluation/results/benchmark.json`

**Developer experience:**
- [ ] `make demo` completes successfully on a clean install (after `make dev`)
- [ ] A user with Docker installed can go from `git clone` to a working query in under 5 minutes
- [ ] `make clean` stops all services and removes volumes cleanly

**Documentation:**
- [ ] `README.md` includes: project description, architecture diagram, quickstart, example query + response, technology table, RAGAS evaluation results table, architecture decisions section
- [ ] `README.md` quickstart works as written (no undocumented steps)
- [ ] `GET /docs` Swagger UI is usable without reading the README

**Docker:**
- [ ] `docker build .` produces a working image
- [ ] Final image size is smaller than the builder stage (multi-stage build effective)
- [ ] All three Docker services have working `healthcheck` definitions

**Final system check:**
- [ ] `make test` passes with all phases' tests (unit + integration)
- [ ] `make lint` passes with zero violations
- [ ] `make eval` produces RAGAS scores meeting PRD targets (Faithfulness ≥ 0.80, Context Recall ≥ 0.75, Answer Relevancy ≥ 0.80)

### Skills Demonstrated

- Extensible document processor design (Strategy pattern via `ExtractorFactory`)
- Multi-format text extraction (PDF, DOCX, TXT)
- Multi-stage Docker builds
- Production observability: latency percentiles, structured metrics endpoint
- Performance benchmarking tied to defined SLAs
- Portfolio presentation: README, demo scripts, Swagger UI completeness
- End-to-end system integration across all five previous phases

---

## Phase 6 — Web Frontend

### Goal

Build a ChatGPT-style single-page web application that makes the platform usable by anyone — not just developers with API clients. Users upload documents via drag-and-drop, watch ingestion progress in real time, type questions in a chat interface, and see grounded answers with expandable source citations.

By the end of this phase the full product is accessible at `http://localhost:3000` with no terminal commands required after `docker compose up`.

### Why This Phase Exists

Phases 1–5 produced a powerful backend API. Phase 6 turns it into a complete product. A recruiter or hiring manager can now clone the repo, run one command, and experience the system without reading API documentation or constructing curl commands. This is the difference between a backend library and a product.

It also adds a new technology dimension to the portfolio: React, TypeScript, and modern frontend tooling — skills increasingly expected of AI Engineers who work on full-stack AI products.

### Architecture

```
Browser (localhost:3000)
  └── nginx container
        ├── /          →  serves React SPA (Vite build output)
        └── /api/*     →  proxies to FastAPI:8000

React Application
  ├── DocumentSidebar    list of documents, upload button, status badges
  ├── UploadDropzone     drag-and-drop + file picker, upload progress
  ├── ChatWindow         scrollable message history
  ├── MessageBubble      user question (right) / AI answer (left)
  ├── CitationCard       collapsible source reference per answer
  └── api/client.ts      typed fetch wrapper over all FastAPI endpoints
```

### Design Decisions

**React + TypeScript + Vite** over Next.js or plain HTML:
- React is the industry standard for AI product frontends
- TypeScript catches API contract mismatches at compile time
- Vite is significantly faster than CRA; near-instant dev server

**Tailwind CSS** over a component library:
- Utility-first keeps bundle small and avoids dependency bloat
- Dark theme trivial to add with `dark:` prefix classes
- Sufficient for a portfolio project without extra abstraction

**TanStack Query (React Query)** for data fetching:
- Automatic document status polling (refetch every 2s until READY/FAILED)
- Caches document list so re-renders don't trigger unnecessary requests
- Built-in loading/error/success states with zero boilerplate

**Separate nginx container** over serving from FastAPI:
- Production-realistic: frontend and backend scale independently
- nginx proxy eliminates CORS entirely — browser always talks to port 3000
- Zero changes to existing FastAPI routes or configuration

**Full response (spinner → answer)** over streaming:
- Works with the existing synchronous `/v1/chat/query` endpoint today
- Avoids backend changes (SSE streaming endpoint) for Phase 6
- Streaming can be added as Phase 7 enhancement

### Deliverables

**Frontend application:**
- Document sidebar with status badges (PENDING / PROCESSING / READY / FAILED)
- Upload dropzone with progress feedback and error display
- Auto-polling: document transitions to READY without page refresh
- Chat window with full conversation history preserved in session
- User messages on the right, AI answers on the left (ChatGPT layout)
- Typing/loading indicator while waiting for the LLM response
- Expandable citation cards under each answer (document name, page, score)
- Document scope selector — optionally pin conversation to one document
- Responsive layout (works on desktop and tablet)

**Infrastructure:**
- `frontend/Dockerfile` — multi-stage: Node build → nginx serve
- `frontend/nginx.conf` — static file serving + `/api` proxy
- `docker-compose.yml` — add `frontend` service on port 3000
- `app/main.py` — add CORS middleware (required for local dev without nginx)

### Files to Create

```
frontend/
  src/
    App.tsx                    ← root layout (sidebar + chat window)
    main.tsx                   ← React entry point
    index.css                  ← Tailwind directives
    types/
      index.ts                 ← TypeScript types mirroring API models
    api/
      client.ts                ← typed fetch wrapper (uploadDocument,
                                  getDocument, listDocuments, query)
    hooks/
      useDocuments.ts          ← TanStack Query hooks with status polling
      useChat.ts               ← chat message state management
    components/
      DocumentSidebar.tsx      ← document list + upload button
      UploadDropzone.tsx        ← drag-and-drop file upload with progress
      ChatWindow.tsx           ← scrollable message history
      MessageBubble.tsx        ← user / assistant message rendering
      CitationCard.tsx         ← collapsible source reference
      StatusBadge.tsx          ← PENDING / PROCESSING / READY / FAILED pill
  index.html
  package.json
  tsconfig.json
  vite.config.ts
  tailwind.config.ts
  postcss.config.js
  Dockerfile                   ← Node build stage + nginx serve stage

app/
  main.py                      ← add CORSMiddleware
```

### Acceptance Criteria

**Document management:**
- [ ] User can upload a PDF/DOCX/TXT file via drag-and-drop or file picker
- [ ] Upload progress is shown during file transfer
- [ ] Document appears in the sidebar immediately after upload with PENDING badge
- [ ] Badge automatically updates to PROCESSING → READY without page refresh
- [ ] Failed ingestion shows FAILED badge with error tooltip
- [ ] User can see all previously uploaded documents on page load

**Chat:**
- [ ] User can type a question and press Enter or click Send
- [ ] A typing indicator is shown while the API processes the request
- [ ] The AI answer appears as a message bubble when the response arrives
- [ ] Conversation history is preserved — multiple Q&A turns are visible
- [ ] Out-of-scope questions display "No relevant documents found." correctly

**Citations:**
- [ ] Each AI answer shows the number of source citations
- [ ] Clicking a citation expands it to show document name, page number, and relevance score
- [ ] Citations are sorted by relevance score (highest first)

**Infrastructure:**
- [ ] `docker compose up -d --build` starts all four containers without errors
- [ ] `http://localhost:3000` serves the React application
- [ ] `/api/*` requests are proxied to FastAPI correctly (no CORS errors in browser)
- [ ] `docker compose ps` shows all four services healthy

**Quality:**
- [ ] TypeScript compiles with zero errors (`tsc --noEmit`)
- [ ] No browser console errors during normal operation
- [ ] Application is usable on a 1280px wide screen without horizontal scroll

### Skills Demonstrated

- React 18 with functional components and hooks
- TypeScript for full-stack type safety (shared API contracts)
- TanStack Query for server state management and polling
- Tailwind CSS utility-first styling
- Vite build tooling
- Multi-stage Docker build (Node → nginx)
- nginx reverse proxy configuration
- CORS middleware in FastAPI
- Real-time UI updates via polling (ingestion status)
- Component-driven architecture

---

## Milestone Summary

The table below maps each deliverable to a milestone. Use this to track progress across the full project.

| Milestone | Phase | Description | Exit Gate |
|---|---|---|---|
| M0.1 | 0 | Docker Compose starts all services | `make dev` green, all three healthchecks pass |
| M0.2 | 0 | FastAPI skeleton with liveness endpoint | `GET /v1/health/live` returns 200 |
| M0.3 | 0 | Config, logging, exceptions wired | `make test` exits 0; `make lint` exits 0 |
| M1.1 | 1 | PDF upload accepted and stored | `POST /v1/documents/upload` returns 202 |
| M1.2 | 1 | Full ingestion pipeline working | Status transitions to READY; chunks in Qdrant |
| M1.3 | 1 | Validation and error handling | Bad files return 422 with correct codes |
| M1.4 | 1 | Unit + integration tests passing | `make test` green against live services |
| M2.1 | 2 | Question embedding working | Embedder returns a 768-dim vector for a question |
| M2.2 | 2 | Retrieval with threshold filter | Chunks returned with correct score filtering |
| M2.3 | 2 | LLM generation working | Ollama returns a non-empty answer |
| M2.4 | 2 | Citations attached to response | Response contains document name, page, chunk |
| M2.5 | 2 | Full query pipeline end-to-end | Integration test: known question → correct citation page |
| M3.1 | 3 | LangGraph state defined | `RAGState` TypedDict compiles cleanly |
| M3.2 | 3 | All 4 nodes implemented and unit tested | Node tests pass without Docker |
| M3.3 | 3 | Graph compiled and wired to QueryService | Graph invocation returns same output as Phase 2 |
| M3.4 | 3 | Conditional edges working | 0-chunk path skips generate; error path returns 503 |
| M3.5 | 3 | Graph diagram generated | `docs/architecture/rag_graph.md` committed |
| M4.1 | 4 | Demo documents ingested and queryable | `make demo` seeds data; queries return answers |
| M4.2 | 4 | Benchmark dataset authored | `industrial_qa.json` has ≥20 entries with ground truth |
| M4.3 | 4 | RAGAS evaluation runner working | `make eval` runs end-to-end without errors |
| M4.4 | 4 | Baseline scores committed | `evaluation/results/baseline.json` committed |
| M4.5 | 4 | Threshold calibrated | Sweep completed; recommended value documented |
| M5.1 | 5 | DOCX and TXT ingestion working | Both formats produce queryable chunks |
| M5.2 | 5 | ExtractorFactory implemented | Adding a new format requires one new class only |
| M5.3 | 5 | Performance benchmark passes SLA | Average latency < 5000ms; results committed |
| M5.4 | 5 | README complete | All required sections present and accurate |
| M5.5 | 5 | Five-minute setup works | Fresh clone → working query in under 5 minutes |
| M5.6 | 5 | RAGAS targets met | Faithfulness ≥ 0.80, Context Recall ≥ 0.75, Relevancy ≥ 0.80 |
| M6.1 | 6 | React app scaffold running | `npm run dev` serves app at localhost:5173 |
| M6.2 | 6 | Document upload working in UI | Drag-and-drop upload reaches READY status |
| M6.3 | 6 | Status polling working | Badge updates PENDING → READY automatically |
| M6.4 | 6 | Chat working end-to-end | Question → answer displayed in UI |
| M6.5 | 6 | Citations rendered | Expandable citation cards appear under each answer |
| M6.6 | 6 | Frontend container in Docker Compose | `localhost:3000` serves the app via nginx |
| M6.7 | 6 | Full product usable | Fresh clone → working product at localhost:3000 |

---

## Phase Exit Gates

Before moving from one phase to the next, all items in this checklist must be true.

### Before starting Phase 1
- [ ] `make dev` starts without errors
- [ ] `make test` and `make lint` pass

### Before starting Phase 2
- [ ] PDF uploads process to `READY` status
- [ ] Qdrant contains vectors with correct payloads
- [ ] Unit tests for chunker and embedder pass without Docker

### Before starting Phase 3
- [ ] Full query pipeline returns answers with citations
- [ ] Integration test: known question → correct citation
- [ ] Unit tests for retriever, assembler, citation builder pass without Docker

### Before starting Phase 4
- [ ] LangGraph graph produces output identical to Phase 2 pipeline
- [ ] All node unit tests pass
- [ ] Both conditional edges (empty retrieval, generation error) are tested and working

### Before starting Phase 5
- [ ] `make eval` produces RAGAS scores (even if below targets)
- [ ] Threshold calibration is complete and documented
- [ ] Baseline results committed to repository

### Before starting Phase 6
- [ ] All Phase 5 acceptance criteria pass
- [ ] PDF, DOCX, and TXT ingestion all working
- [ ] `docker compose up` starts the full stack cleanly
- [ ] README quickstart works as written

### Project complete when
- [ ] All Phase 6 acceptance criteria pass
- [ ] `docker compose up -d --build` starts all four services
- [ ] `http://localhost:3000` serves a usable product
- [ ] Fresh clone → working chat in under 5 minutes with no terminal API calls
- [ ] TypeScript compiles with zero errors
- [ ] `make test` and `make lint` still pass (no backend regression)

---

## What Each Phase Looks Like on a Resume

A common question: what can be said about this project after each phase?

**After Phase 1:**
> Built a document ingestion pipeline using pdfplumber, LangChain text splitters, and Ollama embeddings, storing vectorised chunks in Qdrant with deterministic IDs for idempotent re-ingestion.

**After Phase 2:**
> Implemented a RAG query pipeline with semantic retrieval, configurable score thresholds, character-budget context assembly, LLM generation via Ollama, and structured citation generation from chunk metadata.

**After Phase 3:**
> Architected a 4-node LangGraph state machine for RAG query orchestration, with typed state, conditional routing on retrieval failure, and per-node error propagation — fully unit-testable via injected client mocks.

**After Phase 4:**
> Evaluated the RAG pipeline using RAGAS (Faithfulness 0.83, Context Recall 0.79, Answer Relevancy 0.81) against a 20-question industrial benchmark dataset, with systematic threshold calibration across the 0.4–0.7 range.

**After Phase 5:**
> Delivered a production-quality Industrial Document Intelligence Platform processing PDF/DOCX/TXT documents through a LangGraph RAG pipeline, with RAGAS evaluation, structured observability, multi-stage Docker deployment, and sub-2s p50 query latency.

**After Phase 6:**
> Built a full-stack AI product: React + TypeScript frontend with ChatGPT-style chat interface, real-time document ingestion status, expandable citation cards, and nginx reverse-proxy Docker deployment — fully operational from a single `docker compose up` command.

---

*Created: 2026-06-12*
*Reviewed against: PRD.md, ARCHITECTURE.md v2, CLAUDE.md*

---

## Phase 7 — Production Enhancements

### Goal

Transform the working AI product from Phase 6 into a production-grade platform with features that differentiate it from basic RAG demos: streaming responses, conversation memory, and enhanced citations.

These features are chosen for maximum impact-to-effort ratio and represent real-world requirements that production AI systems must address.

### Why These Features

**Streaming responses** is the single highest-impact improvement. A user staring at a spinner for 5–10 seconds feels like the app is broken. Streaming makes the system feel alive and instant. Every production LLM product streams. Not streaming is a red flag in a portfolio.

**Conversation memory** enables follow-up questions ("What about section 5?" after an initial question). Without memory, every turn is an isolated query — this breaks real workflows. Multi-turn RAG is the expected baseline in 2025.

**Enhanced citations** close the trust loop. Showing a snippet of the actual passage that generated the answer (not just metadata) lets the user verify the answer without re-reading the full document.

### Feature Ranking (Impact vs. Effort)

| Feature | Impact | Effort | Priority |
|---|---|---|---|
| Streaming Responses | Very High | Medium | 1 — Do first |
| Conversation Memory | High | Medium | 2 |
| Enhanced Citations | High | Low | 3 |
| Hybrid Search (BM25 + Vector) | Medium | Medium | 4 |
| Multi-Document Collections | Medium | High | 5 |

### Step 1 — Streaming Responses (SSE)

#### Goal

Replace the blocking "spinner for 5–10 seconds" UX with real-time token streaming. The first words of the answer appear in under one second; the user watches the response build word-by-word.

#### Architecture

```
Browser
  └── fetch POST /api/v1/chat/stream (ReadableStream)
        ├── data: {"type":"token","content":"The "}
        ├── data: {"type":"token","content":"maximum "}
        └── data: {"type":"done","citations":[...],"latency_ms":1234}

FastAPI /v1/chat/stream
  └── StreamingResponse(service.stream_query(), media_type="text/event-stream")
        ├── ThreadPool: Retriever.retrieve() + assemble_context()  [sync, in executor]
        └── httpx.AsyncClient.stream() → Ollama /api/chat?stream=true  [async, token-by-token]
```

#### Files Modified

```
app/
  main.py                   ← store embedder, qdrant_repo, llm settings on app.state
  api/
    dependencies.py         ← pass streaming deps to QueryService
    v1/
      routers/
        chat.py             ← add POST /v1/chat/stream → StreamingResponse
  services/
    query_service.py        ← add stream_query() async generator

frontend/src/
  types/index.ts            ← add isStreaming?: boolean to ChatMessage
  api/client.ts             ← add streamChat() async generator
  hooks/useChat.ts          ← replace useMutation with streaming sendMessage
  components/
    MessageBubble.tsx       ← blinking cursor while isStreaming
```

#### SSE Event Schema

```json
{"type": "token", "content": "The "}
{"type": "done", "answer": "...", "citations": [...], "retrieval_count": 5, "context_chunks_used": 3, "latency_ms": 1234.5, "request_id": "..."}
{"type": "error", "message": "Ollama service is unavailable"}
```

#### Acceptance Criteria

- [ ] `POST /v1/chat/stream` returns `Content-Type: text/event-stream`
- [ ] First token appears in the UI within 1 second of sending a question
- [ ] Tokens accumulate visibly in the message bubble during generation
- [ ] Blinking cursor appears during streaming, disappears when done
- [ ] Citations and latency appear correctly after streaming completes
- [ ] "No relevant documents found." case handled as immediate done event (no tokens)
- [ ] Ollama unreachable → error event → red error bubble in UI
- [ ] No regression in the existing `/v1/chat/query` endpoint

### Step 2 — Conversation Memory

#### Goal

Enable follow-up questions within a chat session. The RAG pipeline receives the last N turns of conversation history and includes them in the LLM prompt so the model understands references like "that", "section 5", "the previous answer".

#### Architecture

```
Frontend: pass session.messages[-N:] as conversation_history in QueryRequest
Backend:  append history turns to the Ollama messages list before generation
          retrieve step is unchanged (retrieves based on current question only)
```

#### Files Modified

```
app/
  core/models.py            ← add ConversationTurn model; add history field to QueryRequest
  agents/nodes/generate.py  ← prepend history turns to Ollama messages list
  agents/state.py           ← add conversation_history field to RAGState
frontend/src/
  hooks/useChat.ts          ← send last 6 messages as conversation_history
  types/index.ts            ← add conversation_history to QueryRequest type
```

#### Acceptance Criteria

- [ ] "What was mentioned about X?" correctly references a prior answer
- [ ] History is capped at N=6 turns (configurable via settings)
- [ ] Switching sessions resets history (no cross-session bleed)
- [ ] Existing unit tests for generate node still pass

### Step 3 — Enhanced Citations

#### Goal

Show a short text snippet from the source passage in each citation card, so users can verify the answer traces back to real document content without re-opening the document.

#### Architecture

```
Backend: add snippet field to Citation (first 200 chars of chunk.text)
Frontend: CitationCard renders snippet below the existing metadata line
```

#### Files Modified

```
app/
  core/models.py            ← add snippet: str to Citation
  agents/nodes/cite.py      ← populate snippet from chunk.text[:200]
frontend/src/
  types/index.ts            ← add snippet?: string to Citation
  components/CitationCard.tsx ← render snippet below metadata
```

#### Acceptance Criteria

- [ ] Citation card shows first 200 chars of source passage, truncated at word boundary
- [ ] Snippet is absent when chunk text is not available (graceful fallback)
- [ ] No layout regression on existing citation cards

### Step 4 — Hybrid Search

#### Goal

Combine dense vector search (semantic similarity) with sparse BM25 keyword search. This improves retrieval for queries containing exact technical terms, part numbers, or model codes where semantic similarity alone underperforms.

#### Architecture

```
Qdrant: enable sparse vector field (fastembed BM25 encoder)
Retriever: send both dense + sparse vectors; Qdrant returns RRF-fused results
Config: search_mode: "dense" | "hybrid" (default: "hybrid" after enabling)
```

#### Files Modified

```
app/
  rag/embedder.py           ← add SparseEmbedder using fastembed
  db/qdrant_repository.py   ← add sparse_vector field; hybrid_search() method
  rag/retriever.py          ← accept search_mode param; call hybrid or dense search
  core/models.py            ← add search_mode to QueryRequest
```

#### Acceptance Criteria

- [ ] Hybrid search returns same or better results than dense-only on benchmark dataset
- [ ] Dense-only mode still works (backward compatible)
- [ ] RAGAS scores do not regress with hybrid mode enabled

### Step 5 — Multi-Document Collections

#### Goal

Allow users to group documents into named collections (e.g., "Hydraulic Systems", "Electrical Manuals") and query across all documents in a collection with a single chat session.

#### Architecture

```
Collections: named groups of document_ids stored in SQLite
Qdrant filter: OR filter across all document_ids in the collection
Chat: accept collection_id OR document_id (mutually exclusive)
```

#### Files Modified

```
app/
  db/
    document_repository.py  ← add collection CRUD methods
  core/models.py            ← add Collection, CollectionCreate, CollectionResponse
  api/v1/routers/
    collections.py          ← POST/GET/DELETE /v1/collections
  services/
    query_service.py        ← resolve collection_id → document_ids for Qdrant filter
frontend/src/
  components/
    SidebarDocumentSection.tsx ← add Collections tab
    CollectionPicker.tsx       ← create/manage collections (new component)
```

#### Acceptance Criteria

- [ ] User can create a named collection and add documents to it
- [ ] Querying a collection retrieves from all member documents
- [ ] Single-document queries continue to work unchanged
- [ ] Deleting a document removes it from any collections it belongs to

---

### Phase 7 Milestones

| Milestone | Step | Description | Exit Gate |
|---|---|---|---|
| M7.1 | 1 | SSE endpoint live | `POST /v1/chat/stream` returns event stream |
| M7.2 | 1 | Streaming in UI | First token appears in < 1s; cursor blinks during generation |
| M7.3 | 2 | History injected | Follow-up questions correctly reference prior turn |
| M7.4 | 2 | Memory scoped | Switching sessions resets history |
| M7.5 | 3 | Snippets in citations | Citation card shows 200-char source passage preview |
| M7.6 | 4 | Hybrid search active | Dense + BM25 combined; RAGAS scores maintained |
| M7.7 | 5 | Collections created | Users can group docs and query across a collection |

### Skills Demonstrated (New in Phase 7)

- Server-Sent Events (SSE) for real-time LLM streaming
- httpx.AsyncClient for async HTTP streaming from upstream LLM services
- Async generator pattern in FastAPI (`StreamingResponse` + `AsyncGenerator`)
- `ReadableStream` + async generator parsing in the browser
- Multi-turn RAG with conversation history injection into the LLM prompt
- Hybrid dense + sparse vector search (semantic + BM25)
- Qdrant sparse vectors with fastembed
- Named entity grouping in vector databases (collection-scoped retrieval)
