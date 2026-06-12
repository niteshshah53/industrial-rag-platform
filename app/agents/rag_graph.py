"""
RAG graph builder.

Creates and compiles the 4-node LangGraph StateGraph for the RAG query pipeline:

    retrieve → assemble → generate → cite

Conditional edges:
    After retrieve:  empty retrieved_chunks → END (no documents path)
                     non-empty             → assemble
    After generate:  error set in state    → END (service unavailable path)
                     no error              → cite

The compiled graph is a singleton created once at startup via FastAPI lifespan
and stored on app.state.rag_graph. QueryService invokes it per request.

Usage:
    from app.agents.rag_graph import build_rag_graph

    graph = build_rag_graph(
        embedder=embedder,
        qdrant_repo=qdrant_repo,
        llm_client=llm_client,
        settings=settings,
    )
    final_state = graph.invoke(initial_state)
"""

import ollama
from langgraph.graph import END, StateGraph

from app.agents.nodes.assemble import build_assemble_node
from app.agents.nodes.cite import build_cite_node
from app.agents.nodes.generate import build_generate_node
from app.agents.nodes.retrieve import build_retrieve_node
from app.agents.state import RAGState
from app.core.config import Settings
from app.db.qdrant_repository import QdrantRepository
from app.rag.embedder import OllamaEmbedder

# ── Routing functions ─────────────────────────────────────────────────────────


def _route_after_retrieve(state: RAGState) -> str:
    """
    Route after the retrieve node.

    Returns "assemble" when chunks were found; END when retrieval returned
    an empty list. The END path causes QueryService to return a
    "No relevant documents found." response without calling the LLM.
    """
    if state.get("retrieved_chunks"):
        return "assemble"
    return END


def _route_after_generate(state: RAGState) -> str:
    """
    Route after the generate node.

    Returns END when the generate node set an error (Ollama unreachable);
    QueryService will convert this to ServiceUnavailableError → HTTP 503.
    Returns "cite" on success.
    """
    if state.get("error"):
        return END
    return "cite"


# ── Graph factory ─────────────────────────────────────────────────────────────


def build_rag_graph(
    embedder: OllamaEmbedder,
    qdrant_repo: QdrantRepository,
    llm_client: ollama.Client,
    settings: Settings,
):
    """
    Build and compile the RAG LangGraph StateGraph.

    Nodes are constructed via their factory functions so each node captures
    its dependencies in a closure. This is the only place where dependencies
    are wired together — nodes themselves have no module-level imports of
    clients or settings.

    Args:
        embedder:    OllamaEmbedder for question embedding (retrieve node).
        qdrant_repo: QdrantRepository for vector search (retrieve node).
        llm_client:  Synchronous Ollama client for LLM generation (generate node).
        settings:    Application settings; provides llm_model and max_context_chars.

    Returns:
        Compiled LangGraph StateGraph ready for .invoke().
    """
    retrieve = build_retrieve_node(embedder=embedder, qdrant_repo=qdrant_repo)
    assemble = build_assemble_node(max_context_chars=settings.max_context_chars)
    generate = build_generate_node(llm_client=llm_client, llm_model=settings.llm_model)
    cite = build_cite_node()

    graph = StateGraph(RAGState)

    graph.add_node("retrieve", retrieve)
    graph.add_node("assemble", assemble)
    graph.add_node("generate", generate)
    graph.add_node("cite", cite)

    graph.set_entry_point("retrieve")

    graph.add_conditional_edges(
        "retrieve",
        _route_after_retrieve,
        {"assemble": "assemble", END: END},
    )
    graph.add_edge("assemble", "generate")
    graph.add_conditional_edges(
        "generate",
        _route_after_generate,
        {"cite": "cite", END: END},
    )
    graph.add_edge("cite", END)

    return graph.compile()
