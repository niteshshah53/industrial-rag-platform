"""
RAG query pipeline orchestrator (Phase 3 — LangGraph graph invocation).

This service invokes the compiled RAG LangGraph graph per request.
The graph executes four nodes (retrieve → assemble → generate → cite) with
conditional routing for empty retrieval and generation failures.

External interface (QueryRequest in, QueryResponse out) is identical to
Phase 2. The migration is purely internal — the graph replaces the direct
sequential function calls in _query_sync.

Design decisions:
  - graph.invoke() is synchronous; the entire call runs in run_in_executor
    to keep the asyncio event loop unblocked.
  - "No relevant documents" (empty retrieval) is a valid 200 response, not
    an exception. The graph routes to END without calling the LLM; QueryService
    detects the empty retrieved_chunks and returns the fixed response string.
  - ServiceUnavailableError is raised when the generate node sets
    state["error"] = "service_unavailable", causing the FastAPI exception
    handler to return HTTP 503.
  - latency_ms is measured by QueryService (wrapping the full graph.invoke()
    call) rather than inside a node, so it includes graph dispatch overhead.
"""

import asyncio
import time
import uuid
from functools import partial
from typing import TYPE_CHECKING

from langgraph.graph.state import CompiledStateGraph

from app.core.exceptions import ServiceUnavailableError

if TYPE_CHECKING:
    from app.agents.state import RAGState
from app.core.logging import get_logger
from app.core.models import QueryRequest, QueryResponse

logger = get_logger(__name__)

_NO_DOCUMENTS_ANSWER = "No relevant documents found."


class QueryService:
    """
    Invokes the compiled RAG graph and converts its final state to a QueryResponse.

    Args:
        graph: Compiled LangGraph StateGraph (built once at startup via lifespan).
    """

    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    async def query(self, request: QueryRequest, request_id: str | None = None) -> QueryResponse:
        """
        Run the RAG pipeline via the LangGraph graph and return a grounded answer.

        The synchronous graph.invoke() runs in a thread pool executor to avoid
        blocking the asyncio event loop.

        Args:
            request:    QueryRequest with question, top_k, score_threshold, document_id.
            request_id: Correlation ID for log tracing. Generated if not provided.

        Returns:
            QueryResponse with answer, citations, and pipeline metrics.
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
        """
        Synchronous pipeline via graph.invoke() — runs in a thread pool.

        Builds the initial state dict from the request, invokes the compiled
        graph, then interprets the final state to construct a QueryResponse.
        """
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
        }

        final_state: RAGState = self._graph.invoke(initial_state)

        latency_ms = (time.monotonic() - start_time) * 1000

        # ── Error path: generation failed (Ollama unreachable) ────────────────
        if final_state.get("error") == "service_unavailable":
            raise ServiceUnavailableError("ollama")

        # ── Early-exit path: no chunks above threshold ─────────────────────────
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

        # ── Happy path ────────────────────────────────────────────────────────
        retrieved_chunks = final_state["retrieved_chunks"]
        included_chunks = final_state.get("included_chunks", [])
        citations = final_state.get("citations", [])
        answer = final_state.get("answer", "")

        # Populate context texts when the caller requested them (evaluation use).
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
