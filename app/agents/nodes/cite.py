"""
Cite node — build Citation objects from included chunk metadata.

Responsibility: take `included_chunks` from state (the chunks whose text was
sent to the LLM) and return `citations`. Citations are ordered identically to
included_chunks, which the assembler has already sorted by score descending.

`_build_citations` is exposed as a public module-level function so it can be
tested directly in isolation (see tests/unit/test_citations.py).

Node signature (LangGraph convention):
    cite(state: RAGState) -> dict

Returns: {"citations": list[Citation]}.
"""

from collections.abc import Callable

from app.agents.state import RAGState
from app.core.models import Citation, RetrievedChunk


def build_cite_node() -> Callable[[RAGState], dict]:
    """
    Build the cite node function.

    The cite node has no external dependencies — it transforms included_chunks
    from state into Citation objects using only data already present in state.

    Returns:
        LangGraph node function: (state: RAGState) -> dict.
    """

    def cite(state: RAGState) -> dict:
        included_chunks = state.get("included_chunks", [])
        citations = _build_citations(included_chunks)
        return {"citations": citations}

    return cite


def _build_citations(included_chunks: list[RetrievedChunk]) -> list[Citation]:
    """
    Build Citation objects from the chunks included in the LLM context.

    Citations are returned in the same order as included_chunks. The assembler
    sorts chunks by score descending before filling the character budget, so
    citations are already ordered by relevance_score descending.

    Args:
        included_chunks: Chunks whose text was included in the LLM context,
                         already sorted by score descending.

    Returns:
        List of Citation objects in the same order as included_chunks.
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
