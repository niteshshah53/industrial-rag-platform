"""
Assemble node — sort chunks by score and enforce the character budget.

Responsibility: take `retrieved_chunks` from state, sort by score descending,
greedily fill the context string up to `max_context_chars`, and return both
`context_string` (formatted for the LLM prompt) and `included_chunks` (the
subset whose text was actually included).

The character budget is captured at build time from settings so the node
function has no external dependencies at call time — it only reads from state.

Node signature (LangGraph convention):
    assemble(state: RAGState) -> dict

Returns: {"context_string": str, "included_chunks": list[RetrievedChunk]}.
"""

from collections.abc import Callable

from app.agents.state import RAGState
from app.core.logging import get_logger
from app.rag.assembler import assemble_context

logger = get_logger(__name__)


def build_assemble_node(max_context_chars: int) -> Callable[[RAGState], dict]:
    """
    Build the assemble node with a fixed character budget.

    Args:
        max_context_chars: Maximum number of characters in the assembled context.
                           Captured from settings.max_context_chars at graph
                           build time.

    Returns:
        LangGraph node function: (state: RAGState) -> dict.
    """

    def assemble(state: RAGState) -> dict:
        request_id = state.get("request_id", "")
        retrieved_chunks = state.get("retrieved_chunks", [])

        context_string, included_chunks = assemble_context(
            chunks=retrieved_chunks,
            max_chars=max_context_chars,
        )

        logger.debug(
            "Assemble node: complete",
            extra={
                "request_id": request_id,
                "chunks_included": len(included_chunks),
                "chunks_dropped": len(retrieved_chunks) - len(included_chunks),
                "context_chars": len(context_string),
                "budget_chars": max_context_chars,
            },
        )

        return {
            "context_string": context_string,
            "included_chunks": included_chunks,
        }

    return assemble
