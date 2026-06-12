"""
Context assembly for the RAG pipeline.

The Assembler takes retrieved chunks and produces two outputs:
  1. A formatted context string to inject into the LLM prompt
  2. The subset of chunks actually included (for citation building and metrics)

Design decisions:
  - Character budget, not token budget: avoids tiktoken/OpenAI dependency.
    The budget is configured via max_context_chars (settings.max_context_chars).
    At ~4 chars/token, 8192 chars ≈ 2048 tokens, well within llama3.2:3b's
    context window.
  - Sort descending before budget enforcement: highest-score chunks are
    always included first. Lower-score chunks are dropped when budget is full.
  - Per-chunk source headers in the context string ([Source: filename, Page N])
    give the LLM anchoring information that improves citation accuracy.
  - Synchronous, pure function: no external calls, fully testable.

Usage:
    context_str, included_chunks = assemble_context(
        chunks=retrieved_chunks,
        max_chars=8192,
    )
"""

from app.core.logging import get_logger
from app.core.models import RetrievedChunk

logger = get_logger(__name__)

_CHUNK_SEPARATOR = "\n\n---\n\n"
_SOURCE_HEADER_TEMPLATE = "[Source: {filename}, Page {page_number}]\n"


def assemble_context(
    chunks: list[RetrievedChunk],
    max_chars: int,
) -> tuple[str, list[RetrievedChunk]]:
    """
    Sort retrieved chunks by score, apply char budget, and format as a context string.

    Args:
        chunks: Retrieved chunks from Qdrant, in any order.
        max_chars: Maximum total character count for the assembled context string.

    Returns:
        Tuple of (context_string, included_chunks):
          - context_string: Formatted string ready for LLM prompt injection.
          - included_chunks: The subset of chunks whose text is in context_string,
                             sorted by score descending. Used for citation building.

    Notes:
        - Empty chunks list returns ("", []).
        - If a single chunk's text exceeds max_chars, it is truncated at max_chars.
          This is a safeguard; it should not occur with properly configured
          chunk_size_chars settings.
    """
    if not chunks:
        return "", []

    # Sort highest-score first so we keep the most relevant chunks.
    sorted_chunks = sorted(chunks, key=lambda c: c.score, reverse=True)

    included: list[RetrievedChunk] = []
    parts: list[str] = []
    char_count = 0

    for chunk in sorted_chunks:
        header = _SOURCE_HEADER_TEMPLATE.format(
            filename=chunk.filename,
            page_number=chunk.page_number,
        )
        entry = header + chunk.text
        entry_len = len(entry)

        # Account for separator between entries
        separator_len = len(_CHUNK_SEPARATOR) if parts else 0
        total_needed = separator_len + entry_len

        if char_count + total_needed > max_chars:
            # Budget full — remaining chunks are dropped.
            break

        parts.append(entry)
        included.append(chunk)
        char_count += total_needed

    context_string = _CHUNK_SEPARATOR.join(parts)

    logger.debug(
        "Context assembled",
        extra={
            "total_retrieved": len(chunks),
            "chunks_included": len(included),
            "chunks_dropped": len(chunks) - len(included),
            "context_char_count": len(context_string),
            "max_chars": max_chars,
        },
    )

    return context_string, included
