"""
Prompt templates for the RAG pipeline.

All prompt strings live here — never inline in node or service code.
This makes prompts easy to iterate on without touching logic, and
enables future A/B testing by swapping templates via config.

Templates are added in Phase 2 when the RAG query pipeline is implemented.
"""

# ── Phase 2 (added during Phase 2 implementation) ─────────────────────────────
#
# RAG_SYSTEM_PROMPT: str = """..."""
#
# RAG_USER_TEMPLATE: str = """..."""
#
# def build_rag_prompt(question: str, context: str) -> str:
#     ...
