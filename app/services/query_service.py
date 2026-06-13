"""
RAG query pipeline orchestrator.

Two execution paths:

  query()        — blocking graph.invoke(), returns QueryResponse. Used by
                   POST /v1/chat/query for the full JSON response.

  stream_query() — async generator that yields SSE-formatted strings. Used by
                   POST /v1/chat/stream for real-time token streaming.

                   Retrieve + assemble run synchronously in a thread pool
                   (reusing the existing Retriever and assemble_context).
                   LLM generation calls Ollama's /api/chat endpoint directly
                   via httpx.AsyncClient so each token can be forwarded to the
                   client as soon as it arrives.

SSE event format (one JSON object per data: line, double-newline terminated):
  {"type": "token",  "content": "..."}
  {"type": "done",   "answer": "...", "citations": [...], "retrieval_count": N,
                     "context_chunks_used": N, "latency_ms": N, "request_id": "..."}
  {"type": "error",  "message": "..."}
"""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from functools import partial
from typing import TYPE_CHECKING, Any

import httpx
from langgraph.graph.state import CompiledStateGraph

from app.core.exceptions import ServiceUnavailableError

if TYPE_CHECKING:
    from app.agents.state import RAGState
    from app.db.qdrant_repository import QdrantRepository
    from app.rag.embedder import OllamaEmbedder
    from app.rag.sparse_embedder import SparseEmbedder

from app.agents.nodes.cite import _build_citations
from app.core.logging import get_logger
from app.core.models import QueryRequest, QueryResponse, RetrievedChunk
from app.core.prompts import RAG_SYSTEM_PROMPT, build_rag_prompt
from app.rag.assembler import assemble_context

logger = get_logger(__name__)

_NO_DOCUMENTS_ANSWER = "No relevant documents found."

# Ollama connectivity errors (same set as generate.py).
_CONNECTIVITY_ERRORS = (
    ConnectionRefusedError,
    ConnectionError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
)


def _sse(payload: dict[str, Any]) -> str:
    """Format a dict as a single SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


class QueryService:
    """
    Invokes the compiled RAG graph and converts its final state to a QueryResponse.

    Args:
        graph:            Compiled LangGraph StateGraph (built once at startup).
        embedder:         OllamaEmbedder for streaming path retrieval.
        qdrant_repo:      QdrantRepository for streaming path retrieval.
        ollama_base_url:  Base URL for the Ollama HTTP API.
        llm_model:        LLM model identifier (e.g. "llama3.2:3b").
        max_context_chars: Character budget for context assembly.
    """

    def __init__(
        self,
        graph: CompiledStateGraph,
        embedder: "OllamaEmbedder | None" = None,
        qdrant_repo: "QdrantRepository | None" = None,
        ollama_base_url: str = "http://localhost:11434",
        llm_model: str = "llama3.2:3b",
        max_context_chars: int = 8000,
        sparse_embedder: "SparseEmbedder | None" = None,
    ) -> None:
        self._graph = graph
        self._embedder = embedder
        self._qdrant_repo = qdrant_repo
        self._ollama_base_url = ollama_base_url
        self._llm_model = llm_model
        self._max_context_chars = max_context_chars
        self._sparse_embedder = sparse_embedder

    # ── Blocking path (existing) ───────────────────────────────────────────────

    async def query(self, request: QueryRequest, request_id: str | None = None) -> QueryResponse:
        """
        Run the RAG pipeline via the LangGraph graph and return a grounded answer.

        The synchronous graph.invoke() runs in a thread pool executor to avoid
        blocking the asyncio event loop.
        """
        if request_id is None:
            request_id = str(uuid.uuid4())

        start_time = time.monotonic()
        loop = asyncio.get_event_loop()

        return await loop.run_in_executor(
            None,
            partial(self._query_sync, request, request_id, start_time),
        )

    def _query_sync(
        self,
        request: QueryRequest,
        request_id: str,
        start_time: float,
    ) -> QueryResponse:
        """Synchronous pipeline via graph.invoke() — runs in a thread pool."""
        logger.info(
            "Query pipeline started",
            extra={"request_id": request_id, "question_length": len(request.question)},
        )

        initial_state: RAGState = {
            "question": request.question,
            "top_k": request.top_k,
            "score_threshold": request.score_threshold,
            "document_id": request.document_id,
            "request_id": request_id,
            "start_time": start_time,
            "search_mode": request.search_mode,
            "conversation_history": [t.model_dump() for t in request.conversation_history],
        }

        final_state: RAGState = self._graph.invoke(initial_state)

        latency_ms = (time.monotonic() - start_time) * 1000

        if final_state.get("error") == "service_unavailable":
            raise ServiceUnavailableError("ollama")

        if not final_state.get("retrieved_chunks"):
            logger.info(
                "No chunks above threshold — returning no-documents response",
                extra={"request_id": request_id, "latency_ms": round(latency_ms, 1)},
            )
            return QueryResponse(
                answer=_NO_DOCUMENTS_ANSWER,
                citations=[],
                retrieval_count=0,
                context_chunks_used=0,
                latency_ms=latency_ms,
                request_id=request_id,
            )

        retrieved_chunks = final_state["retrieved_chunks"]
        included_chunks = final_state.get("included_chunks", [])
        citations = final_state.get("citations", [])
        answer = final_state.get("answer", "")

        contexts = [chunk.text for chunk in included_chunks] if request.include_contexts else None

        logger.info(
            "Query pipeline complete",
            extra={
                "request_id": request_id,
                "latency_ms": round(latency_ms, 1),
                "retrieval_count": len(retrieved_chunks),
                "context_chunks_used": len(included_chunks),
                "citations_count": len(citations),
            },
        )

        return QueryResponse(
            answer=answer,
            citations=citations,
            retrieval_count=len(retrieved_chunks),
            context_chunks_used=len(included_chunks),
            latency_ms=latency_ms,
            request_id=request_id,
            contexts=contexts,
        )

    # ── Streaming path (Phase 7 Step 1) ───────────────────────────────────────

    async def stream_query(
        self,
        request: QueryRequest,
        request_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream the RAG response as SSE events.

        Retrieve + assemble run synchronously in a thread pool (reusing existing
        Retriever and assemble_context). Generation streams from Ollama's HTTP
        API so tokens reach the client as they are produced.

        Yields SSE-formatted strings (``data: {...}\\n\\n``).
        """
        if request_id is None:
            request_id = str(uuid.uuid4())

        if self._embedder is None or self._qdrant_repo is None:
            yield _sse({"type": "error", "message": "Streaming not available in test mode."})
            return

        start_time = time.monotonic()

        # ── Step 1: retrieve + assemble in thread pool ─────────────────────────
        try:
            loop = asyncio.get_event_loop()
            retrieved_chunks, included_chunks, context_string = await loop.run_in_executor(
                None,
                partial(self._retrieve_and_assemble, request, request_id, request.search_mode),
            )
        except Exception as exc:
            logger.warning(
                "stream_query: retrieval failed",
                extra={"request_id": request_id, "error": str(exc)},
            )
            yield _sse({"type": "error", "message": "Retrieval failed. Please try again."})
            return

        latency_retrieve_ms = (time.monotonic() - start_time) * 1000

        # ── Step 2: no documents path ──────────────────────────────────────────
        if not retrieved_chunks:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.info(
                "stream_query: no chunks above threshold",
                extra={"request_id": request_id, "latency_ms": round(latency_ms, 1)},
            )
            yield _sse({
                "type": "done",
                "answer": _NO_DOCUMENTS_ANSWER,
                "citations": [],
                "retrieval_count": 0,
                "context_chunks_used": 0,
                "latency_ms": round(latency_ms, 1),
                "request_id": request_id,
            })
            return

        # ── Step 3: stream generation from Ollama ─────────────────────────────
        prompt = build_rag_prompt(question=request.question, context=context_string)
        messages: list[dict] = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
        messages.extend(t.model_dump() for t in request.conversation_history)
        messages.append({"role": "user", "content": prompt})

        full_answer = ""

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                async with client.stream(
                    "POST",
                    f"{self._ollama_base_url}/api/chat",
                    json={"model": self._llm_model, "messages": messages, "stream": True},
                ) as response:
                    if response.status_code != 200:
                        yield _sse({"type": "error", "message": f"Ollama returned HTTP {response.status_code}."})
                        return

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_answer += token
                            yield _sse({"type": "token", "content": token})

                        if chunk.get("done"):
                            break

        except _CONNECTIVITY_ERRORS as exc:
            logger.warning(
                "stream_query: Ollama unreachable",
                extra={"request_id": request_id, "error": str(exc)},
            )
            yield _sse({"type": "error", "message": "Language model is unavailable. Please try again later."})
            return

        # ── Step 4: emit final done event with citations ───────────────────────
        citations = self._build_citations(included_chunks)
        latency_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "stream_query: complete",
            extra={
                "request_id": request_id,
                "latency_ms": round(latency_ms, 1),
                "retrieval_count": len(retrieved_chunks),
                "context_chunks_used": len(included_chunks),
                "answer_length": len(full_answer),
            },
        )

        yield _sse({
            "type": "done",
            "answer": full_answer.strip(),
            "citations": [c.model_dump() for c in citations],
            "retrieval_count": len(retrieved_chunks),
            "context_chunks_used": len(included_chunks),
            "latency_ms": round(latency_ms, 1),
            "request_id": request_id,
        })

    def _retrieve_and_assemble(
        self,
        request: QueryRequest,
        request_id: str,
        search_mode: str = "hybrid",
    ) -> tuple[list[RetrievedChunk], list[RetrievedChunk], str]:
        """
        Run retrieval and assembly synchronously (called from run_in_executor).

        Returns (retrieved_chunks, included_chunks, context_string).
        """
        from app.rag.retriever import Retriever

        retriever = Retriever(
            embedder=self._embedder,
            qdrant_repo=self._qdrant_repo,
            sparse_embedder=self._sparse_embedder,
        )
        retrieved_chunks = retriever.retrieve(
            question=request.question,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
            document_id_filter=request.document_id,
            search_mode=search_mode,
        )

        if not retrieved_chunks:
            return [], [], ""

        context_string, included_chunks = assemble_context(
            chunks=retrieved_chunks,
            max_chars=self._max_context_chars,
        )
        return retrieved_chunks, included_chunks, context_string

    @staticmethod
    def _build_citations(included_chunks: list[RetrievedChunk]):
        return _build_citations(included_chunks)
