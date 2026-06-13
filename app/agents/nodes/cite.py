"""
Cite node — build Citation objects from included chunk metadata.

Responsibility: take `included_chunks` from state (the chunks whose text was
sent to the LLM) and return `citations`. Citations are ordered identically to
included_chunks, which the assembler has already sorted by score descending.

Each citation carries a short `snippet` — the first ~200 characters of the
chunk text, truncated at a word boundary. This lets the user verify an answer
traces to real document content without reopening the source file.

`_build_citations` and `_make_snippet` are exposed as public module-level
functions so they can be reused by QueryService (streaming path) and tested
directly in isolation.
"""

from collections.abc import Callable

from app.agents.state import RAGState
from app.core.models import Citation, RetrievedChunk

_SNIPPET_MAX_CHARS = 200


def _make_snippet(text: str) -> str:
    """
    Return the first ~200 characters of text, truncated at a word boundary.

    Strips leading/trailing whitespace from the source text before truncating.
    Appends '…' when truncation occurs.
    """
    text = text.strip()
    if len(text) <= _SNIPPET_MAX_CHARS:
        return text
    truncated = text[:_SNIPPET_MAX_CHARS]
    last_space = truncated.rfind(' ')
    if last_space > _SNIPPET_MAX_CHARS // 2:
        truncated = truncated[:last_space]
    return truncated + '…'


def _build_citations(included_chunks: list[RetrievedChunk]) -> list[Citation]:
    """
    Build Citation objects from the chunks included in the LLM context.

    Citations are returned in the same order as included_chunks. The assembler
    sorts chunks by score descending before filling the character budget, so
    citations are already ordered by relevance_score descending.
    """
    return [
        Citation(
            document_name=chunk.filename,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            relevance_score=round(chunk.score, 4),
            snippet=_make_snippet(chunk.text),
            text=chunk.text.strip(),
        )
        for chunk in included_chunks
    ]


def build_cite_node() -> Callable[[RAGState], dict]:
    """
    Build the cite node function.

    The cite node has no external dependencies — it transforms included_chunks
    from state into Citation objects using only data already present in state.
    """

    def cite(state: RAGState) -> dict:
        included_chunks = state.get("included_chunks", [])
        citations = _build_citations(included_chunks)
        return {"citations": citations}

    return cite
