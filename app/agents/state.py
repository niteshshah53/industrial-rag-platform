"""
RAGState TypedDict — the shared state passed between LangGraph nodes.

Design decisions:
  - total=False makes all fields optional. LangGraph nodes return partial
    dicts (only the keys they set), and the graph merges them into the
    accumulated state. Declaring all keys optional matches this pattern
    and avoids spurious type errors when a node only returns {"retrieved_chunks": ...}.
  - RetrievedChunk and Citation objects are stored as Python objects, not
    serialised, because this graph runs in-process (no distributed execution,
    no checkpoint persistence). This keeps state access zero-cost.
  - `error` is a string code rather than an exception object so it is easy
    to inspect in routing functions and serialise if a checkpoint backend
    is added later.
  - `start_time` (monotonic clock) is set by QueryService before invoke
    so that QueryService can compute latency_ms after invoke() returns,
    rather than computing it inside a node (which would miss graph overhead).
"""

from typing import TypedDict

from app.core.models import Citation, RetrievedChunk


class RAGState(TypedDict, total=False):
    """
    Shared state passed through all nodes in the RAG graph.

    Input fields — set by QueryService before graph.invoke():
        question:         The user's question string.
        top_k:            Maximum chunks to retrieve from Qdrant.
        score_threshold:  Minimum cosine similarity score for retrieval.
        document_id:      Optional document filter; None means all documents.
        request_id:       Correlation ID threaded through all log statements.
        start_time:       time.monotonic() at query start, for latency tracking.

    Retrieve node output:
        retrieved_chunks: All chunks returned by Qdrant above score_threshold.

    Assemble node output:
        context_string:   Formatted context block passed to the LLM prompt.
        included_chunks:  Subset of retrieved_chunks that fit within char budget.

    Generate node output:
        answer:           LLM-generated answer string (set on success).
        error:            Error code string set on node failure; None on success.
                          Currently only "service_unavailable" is emitted.

    Cite node output:
        citations:        Citation objects built from included_chunks metadata.
    """

    # ── Input ─────────────────────────────────────────────────────────────────
    question: str
    top_k: int
    score_threshold: float
    document_id: str | None
    # When set, retrieve across all listed document IDs (collection query).
    # Takes priority over document_id. Set by QueryService after resolving collection_id.
    document_ids: list[str] | None
    request_id: str
    start_time: float
    # "hybrid" uses BM25 + dense RRF; "dense" uses cosine similarity only.
    search_mode: str
    # Prior turns as list of {"role": "user"|"assistant", "content": "..."}.
    # Empty list when this is the first message in a session.
    conversation_history: list[dict]

    # ── Retrieve ──────────────────────────────────────────────────────────────
    retrieved_chunks: list[RetrievedChunk]

    # ── Assemble ──────────────────────────────────────────────────────────────
    context_string: str
    included_chunks: list[RetrievedChunk]

    # ── Generate ──────────────────────────────────────────────────────────────
    answer: str
    error: str | None

    # ── Cite ──────────────────────────────────────────────────────────────────
    citations: list[Citation]
