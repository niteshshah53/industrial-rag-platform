"""
Prompt templates for the RAG pipeline.

All prompt strings live here — never inline in node or service code.
Centralising prompts enables iteration without touching logic files, and
makes A/B testing possible by swapping templates via configuration.

Design decisions:
  - RAG_SYSTEM_PROMPT instructs the model to answer from context only and
    to decline when context is insufficient. This minimises hallucination
    with small open-source models like llama3.2:3b.
  - The user template uses explicit XML-like tags ([CONTEXT], [QUESTION])
    rather than markdown headers because llama3.2:3b responds more
    reliably to explicit delimiters.
  - build_rag_prompt() is a pure function — no side effects, fully testable.
"""

RAG_SYSTEM_PROMPT: str = """You are a precise technical assistant for industrial documentation.

Your task is to answer questions using ONLY the information provided in the context below.

Rules:
- Answer based exclusively on the provided context. Do not use prior knowledge.
- If the context does not contain enough information to answer the question, respond with:
  "I cannot find sufficient information in the provided documents to answer this question."
- Be concise and factual. Do not pad the answer.
- Do not mention the word "context" or "document" in your answer — answer as if you know the information directly.
- If relevant, include specific values (temperatures, pressures, intervals) from the context."""

RAG_USER_TEMPLATE: str = """[CONTEXT]
{context}
[/CONTEXT]

[QUESTION]
{question}
[/QUESTION]

Answer:"""


def build_rag_prompt(question: str, context: str) -> str:
    """
    Fill the RAG user template with the question and assembled context.

    Args:
        question: The user's question.
        context: The assembled context string from the assembler.

    Returns:
        Formatted user message string ready to pass to the LLM.
    """
    return RAG_USER_TEMPLATE.format(context=context, question=question)
