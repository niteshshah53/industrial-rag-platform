"""
Generate node — fill the RAG prompt and call the Ollama LLM.

Responsibility: take `question` and `context_string` from state, build the
RAG prompt, call the Ollama LLM, and return `answer`.

Error handling:
  Network connectivity errors (Ollama unreachable) are caught and converted
  to {"error": "service_unavailable"} in state. This keeps error handling
  explicit and observable in the graph rather than propagating raw exceptions.
  The graph's conditional edge after this node routes to END when error is set,
  and QueryService converts the error code to ServiceUnavailableError → HTTP 503.

  Non-connectivity errors (model not found, malformed response, etc.) are
  re-raised and become unhandled 500 responses — these indicate configuration
  or deployment issues, not transient failures.

Node signature (LangGraph convention):
    generate(state: RAGState) -> dict

Returns: {"answer": str} on success, or {"error": "service_unavailable"} on
Ollama connectivity failure.
"""

import time
from collections.abc import Callable

import httpx
import ollama

from app.agents.state import RAGState
from app.core.logging import get_logger
from app.core.prompts import RAG_SYSTEM_PROMPT, build_rag_prompt

logger = get_logger(__name__)

# Exception types that indicate Ollama is unreachable (not misconfigured).
_CONNECTIVITY_ERRORS = (
    ConnectionRefusedError,
    ConnectionError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
)


def build_generate_node(
    llm_client: ollama.Client,
    llm_model: str,
) -> Callable[[RAGState], dict]:
    """
    Build the generate node with an injected Ollama client.

    Both the client and model name are captured at build time so the node
    function has no runtime imports. Tests inject a mock client to exercise
    both the happy path and the connectivity-failure path.

    Args:
        llm_client: Synchronous Ollama client (ollama.Client).
        llm_model:  Model identifier to pass to ollama.Client.chat(),
                    e.g. "llama3.2:3b".

    Returns:
        LangGraph node function: (state: RAGState) -> dict.
    """

    def generate(state: RAGState) -> dict:
        request_id = state.get("request_id", "")
        question = state["question"]
        context = state.get("context_string", "")

        prompt = build_rag_prompt(question=question, context=context)
        gen_start = time.monotonic()

        try:
            response = llm_client.chat(
                model=llm_model,
                messages=[
                    {"role": "system", "content": RAG_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            answer = response.message.content.strip()

        except _CONNECTIVITY_ERRORS as exc:
            logger.warning(
                "Generate node: Ollama unreachable",
                extra={"request_id": request_id, "error": str(exc)},
            )
            return {"error": "service_unavailable"}

        gen_latency_ms = (time.monotonic() - gen_start) * 1000

        logger.info(
            "Generate node: complete",
            extra={
                "request_id": request_id,
                "model": llm_model,
                "generation_latency_ms": round(gen_latency_ms, 1),
                "answer_length": len(answer),
            },
        )

        return {"answer": answer}

    return generate
