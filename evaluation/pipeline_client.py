"""
HTTP client for the Industrial RAG Platform query API.

Used by the evaluation pipeline to query the live system for each benchmark
question. Always requests include_contexts=True so RAGAS has the retrieved
chunk texts needed to compute Faithfulness and ContextRecall.

Design:
  - Thin wrapper — no business logic beyond request/response translation.
  - Raises clear exceptions on connection failure or API errors so the
    evaluation runner can distinguish between infra failures and bad scores.
  - Configurable base_url and score_threshold to support threshold sweep.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PipelineResponse:
    """Structured representation of a POST /v1/chat/query response."""

    question: str
    answer: str
    contexts: list[str]  # chunk texts; empty when no documents found
    citations: list[dict]
    retrieval_count: int
    context_chunks_used: int
    latency_ms: float
    request_id: str
    has_answer: bool = field(init=False)

    def __post_init__(self) -> None:
        self.has_answer = bool(self.answer) and self.answer != "No relevant documents found."


class PipelineClient:
    """
    HTTP client for querying the RAG pipeline during evaluation.

    Args:
        base_url:        API base URL (e.g. "http://localhost:8000").
        score_threshold: Retrieval score threshold to use for all queries.
        top_k:           Maximum chunks to retrieve per query.
        timeout:         Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        score_threshold: float = 0.6,
        top_k: int = 5,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._score_threshold = score_threshold
        self._top_k = top_k
        self._timeout = timeout

    def health_check(self) -> bool:
        """Return True if the API is reachable and healthy."""
        try:
            resp = httpx.get(f"{self._base_url}/v1/health/live", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def query(self, question: str) -> PipelineResponse:
        """
        Query the RAG pipeline and return a structured response.

        Always sends include_contexts=True so the evaluation pipeline
        has the retrieved chunk texts for RAGAS metric computation.

        Args:
            question: The question to ask the RAG system.

        Returns:
            PipelineResponse with answer, contexts, and metadata.

        Raises:
            httpx.ConnectError:  API is unreachable.
            httpx.HTTPStatusError: API returned a non-2xx response.
        """
        payload = {
            "question": question,
            "score_threshold": self._score_threshold,
            "top_k": self._top_k,
            "include_contexts": True,
        }

        logger.debug("Querying pipeline: %s", question[:80])

        response = httpx.post(
            f"{self._base_url}/v1/chat/query",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()

        return PipelineResponse(
            question=question,
            answer=data["answer"],
            contexts=data.get("contexts") or [],
            citations=data.get("citations", []),
            retrieval_count=data.get("retrieval_count", 0),
            context_chunks_used=data.get("context_chunks_used", 0),
            latency_ms=data.get("latency_ms", 0.0),
            request_id=data.get("request_id", ""),
        )

    def query_batch(self, questions: list[str], verbose: bool = True) -> list[PipelineResponse]:
        """
        Query the pipeline for each question in sequence.

        Args:
            questions: List of questions to query.
            verbose:   If True, print progress to stdout.

        Returns:
            List of PipelineResponse objects in the same order as questions.
        """
        responses = []
        for i, question in enumerate(questions, 1):
            if verbose:
                print(f"  [{i}/{len(questions)}] {question[:70]}...")
            resp = self.query(question)
            responses.append(resp)
            if verbose:
                status = "✓" if resp.has_answer else "○ (no documents)"
                print(f"         → {status} ({resp.latency_ms:.0f}ms)")
        return responses
