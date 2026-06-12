"""
RAG query pipeline orchestrator (Phase 2 — direct pipeline, no LangGraph).

This service implements the complete question-answering pipeline:
  1. Embed the question via Ollama
  2. Retrieve the top-k most relevant chunks from Qdrant
  3. Assemble a context string within the character budget
  4. Generate an answer via the Ollama LLM
  5. Build citation objects from the included chunk metadata

Phase 3 will migrate this to a LangGraph state machine. The external
interface (QueryRequest in, QueryResponse out) will not change.

Design decisions:
  - The entire sync pipeline (_query_sync) runs in a single run_in_executor
    call, keeping the asyncio event loop unblocked. Both the Ollama embedding
    client and the Ollama LLM client are synchronous.
  - "No relevant documents" is a valid 200 response, not an exception.
    The answer is set to a fixed string; citations are empty.
  - ServiceUnavailableError (Ollama/Qdrant unreachable) is re-raised to the
    FastAPI exception handler, which returns HTTP 503.
  - Citation objects are built from the included_chunks list returned by
    the assembler, not from the full retrieval_results, so that citations
    only reference content the LLM actually saw.
  - request_id is threaded through all log statements for correlation.
"""

import asyncio
import time
import uuid
from functools import partial

import ollama

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.models import Citation, QueryRequest, QueryResponse, RetrievedChunk
from app.core.prompts import RAG_SYSTEM_PROMPT, build_rag_prompt
from app.db.qdrant_repository import QdrantRepository
from app.rag.assembler import assemble_context
from app.rag.embedder import OllamaEmbedder
from app.rag.retriever import Retriever

logger = get_logger(__name__)

_NO_DOCUMENTS_ANSWER = "No relevant documents found."


class QueryService:
    """
    Orchestrates the RAG question-answering pipeline.

    Args:
        settings: Application settings (model names, thresholds, budgets).
        qdrant_repo: QdrantRepository instance for vector search.
    """

    def __init__(self, settings: Settings, qdrant_repo: QdrantRepository) -> None:
        self._settings = settings
        self._qdrant_repo = qdrant_repo

        embedder = OllamaEmbedder(
            base_url=settings.ollama_base_url,
            model=settings.embedding_model,
        )
        self._retriever = Retriever(embedder=embedder, qdrant_repo=qdrant_repo)
        self._llm_client = ollama.Client(host=settings.ollama_base_url)

    async def query(self, request: QueryRequest, request_id: str | None = None) -> QueryResponse:
        """
        Run the full RAG pipeline and return a grounded answer with citations.

        The synchronous pipeline runs in a thread pool executor to avoid
        blocking the asyncio event loop.

        Args:
            request: QueryRequest with question, top_k, score_threshold, document_id.
            request_id: Correlation ID for log tracing. Generated if not provided.

        Returns:
            QueryResponse with answer, citations, and pipeline metrics.
        """
        if request_id is None:
            request_id = str(uuid.uuid4())

        start_time = time.monotonic()
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,
            partial(self._query_sync, request, request_id, start_time),
        )
        return response

    def _query_sync(
        self,
        request: QueryRequest,
        request_id: str,
        start_time: float,
    ) -> QueryResponse:
        """
        Synchronous RAG pipeline — runs in a thread pool.

        Steps:
          1. Retrieve chunks (embed question + Qdrant search)
          2. If 0 chunks → return "no relevant documents" response
          3. Assemble context within character budget
          4. Generate answer via Ollama LLM
          5. Build Citation objects from included chunks
        """
        logger.info(
            "Query pipeline started",
            extra={"request_id": request_id, "question_length": len(request.question)},
        )

        # ── Step 1: Retrieve ──────────────────────────────────────────────────
        retrieved_chunks = self._retriever.retrieve(
            question=request.question,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
            document_id_filter=request.document_id,
        )

        logger.info(
            "Retrieval complete",
            extra={
                "request_id": request_id,
                "retrieved_count": len(retrieved_chunks),
                "score_threshold": request.score_threshold,
                "top_score": retrieved_chunks[0].score if retrieved_chunks else None,
            },
        )

        # ── Step 2: Early exit on empty retrieval ─────────────────────────────
        if not retrieved_chunks:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.info(
                "No chunks above threshold — returning no-documents response",
                extra={"request_id": request_id, "latency_ms": latency_ms},
            )
            return QueryResponse(
                answer=_NO_DOCUMENTS_ANSWER,
                citations=[],
                retrieval_count=0,
                context_chunks_used=0,
                latency_ms=latency_ms,
                request_id=request_id,
            )

        # ── Step 3: Assemble context ──────────────────────────────────────────
        context_string, included_chunks = assemble_context(
            chunks=retrieved_chunks,
            max_chars=self._settings.max_context_chars,
        )

        logger.debug(
            "Context assembled",
            extra={
                "request_id": request_id,
                "chunks_included": len(included_chunks),
                "context_chars": len(context_string),
            },
        )

        # ── Step 4: Generate answer ───────────────────────────────────────────
        answer = self._generate(
            question=request.question,
            context=context_string,
            request_id=request_id,
        )

        # ── Step 5: Build citations ───────────────────────────────────────────
        citations = _build_citations(included_chunks)

        latency_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "Query pipeline complete",
            extra={
                "request_id": request_id,
                "latency_ms": latency_ms,
                "citations_count": len(citations),
                "retrieval_count": len(retrieved_chunks),
                "context_chunks_used": len(included_chunks),
            },
        )

        return QueryResponse(
            answer=answer,
            citations=citations,
            retrieval_count=len(retrieved_chunks),
            context_chunks_used=len(included_chunks),
            latency_ms=latency_ms,
            request_id=request_id,
        )

    def _generate(self, question: str, context: str, request_id: str) -> str:
        """
        Call the Ollama LLM to generate a grounded answer.

        Args:
            question: The user's question.
            context: Assembled context string from the assembler.
            request_id: Correlation ID for log tracing.

        Returns:
            Generated answer string.

        Raises:
            ServiceUnavailableError: If Ollama is unreachable.
        """
        gen_start = time.monotonic()

        prompt = build_rag_prompt(question=question, context=context)

        response = self._llm_client.chat(
            model=self._settings.llm_model,
            messages=[
                {"role": "system", "content": RAG_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        answer = response.message.content.strip()
        gen_latency_ms = (time.monotonic() - gen_start) * 1000

        logger.info(
            "LLM generation complete",
            extra={
                "request_id": request_id,
                "model": self._settings.llm_model,
                "generation_latency_ms": round(gen_latency_ms, 1),
                "answer_length": len(answer),
            },
        )

        return answer


def _build_citations(included_chunks: list[RetrievedChunk]) -> list[Citation]:
    """
    Build Citation objects from the chunks included in the LLM context.

    Citations are sorted by relevance_score descending, matching the
    order in which chunks were included in the context.

    Args:
        included_chunks: Chunks whose text was included in the LLM context,
                         already sorted by score descending by the assembler.

    Returns:
        List of Citation objects in the same order.
    """
    return [
        Citation(
            document_name=chunk.filename,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            relevance_score=round(chunk.score, 4),
        )
        for chunk in included_chunks
    ]
