"""
Unit tests for LangGraph RAG graph nodes.

Each node is tested via its factory function with injected mocks.
No Docker services required — all external clients are mocked.

Test structure:
  TestRetrieveNode  — embedding call, parameter forwarding, result shape
  TestAssembleNode  — sorting, char budget, context format
  TestGenerateNode  — prompt construction, success path, error path
  TestCiteNode      — citation structure, ordering, empty input
"""

from unittest.mock import MagicMock

from app.agents.nodes.assemble import build_assemble_node
from app.agents.nodes.cite import build_cite_node
from app.agents.nodes.generate import build_generate_node
from app.agents.nodes.retrieve import build_retrieve_node
from app.core.models import RetrievedChunk
from app.core.prompts import RAG_SYSTEM_PROMPT

# ── Shared helpers ─────────────────────────────────────────────────────────────


def _make_chunk(
    chunk_id: str = "c-0",
    score: float = 0.85,
    text: str = "Default chunk text.",
    page_number: int = 1,
    document_id: str = "doc-001",
    filename: str = "manual.pdf",
    chunk_index: int = 0,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        score=score,
        document_id=document_id,
        filename=filename,
        page_number=page_number,
        chunk_index=chunk_index,
    )


def _base_state(**overrides) -> dict:
    """Return a minimal valid RAGState dict for node input."""
    state = {
        "question": "What is the maximum temperature?",
        "top_k": 5,
        "score_threshold": 0.6,
        "document_id": None,
        "request_id": "test-req-id",
        "start_time": 0.0,
    }
    state.update(overrides)
    return state


# ── TestRetrieveNode ───────────────────────────────────────────────────────────


class TestRetrieveNode:
    def _make_mocks(
        self,
        embed_vector: list[float] | None = None,
        search_results: list[RetrievedChunk] | None = None,
    ) -> tuple[MagicMock, MagicMock]:
        """Return (mock_embedder, mock_qdrant_repo)."""
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = embed_vector or [0.1] * 768

        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = search_results or []

        return mock_embedder, mock_qdrant

    def test_embeds_question_before_search(self):
        mock_embedder, mock_qdrant = self._make_mocks()
        node = build_retrieve_node(embedder=mock_embedder, qdrant_repo=mock_qdrant)

        node(_base_state(question="What is the max temperature?"))

        mock_embedder.embed_query.assert_called_once_with("What is the max temperature?")

    def test_passes_vector_to_qdrant(self):
        fake_vector = [0.42] * 768
        mock_embedder, mock_qdrant = self._make_mocks(embed_vector=fake_vector)
        node = build_retrieve_node(embedder=mock_embedder, qdrant_repo=mock_qdrant)

        node(_base_state())

        assert mock_qdrant.search.call_args.kwargs["vector"] == fake_vector

    def test_forwards_top_k(self):
        mock_embedder, mock_qdrant = self._make_mocks()
        node = build_retrieve_node(embedder=mock_embedder, qdrant_repo=mock_qdrant)

        node(_base_state(top_k=7))

        assert mock_qdrant.search.call_args.kwargs["top_k"] == 7

    def test_forwards_score_threshold(self):
        mock_embedder, mock_qdrant = self._make_mocks()
        node = build_retrieve_node(embedder=mock_embedder, qdrant_repo=mock_qdrant)

        node(_base_state(score_threshold=0.8))

        assert mock_qdrant.search.call_args.kwargs["score_threshold"] == 0.8

    def test_forwards_document_id_filter(self):
        mock_embedder, mock_qdrant = self._make_mocks()
        node = build_retrieve_node(embedder=mock_embedder, qdrant_repo=mock_qdrant)

        node(_base_state(document_id="doc-xyz"))

        assert mock_qdrant.search.call_args.kwargs["document_id_filter"] == "doc-xyz"

    def test_forwards_none_document_id_filter(self):
        mock_embedder, mock_qdrant = self._make_mocks()
        node = build_retrieve_node(embedder=mock_embedder, qdrant_repo=mock_qdrant)

        node(_base_state(document_id=None))

        assert mock_qdrant.search.call_args.kwargs["document_id_filter"] is None

    def test_returns_retrieved_chunks_in_state(self):
        chunks = [_make_chunk("c-0", score=0.9), _make_chunk("c-1", score=0.7)]
        mock_embedder, mock_qdrant = self._make_mocks(search_results=chunks)
        node = build_retrieve_node(embedder=mock_embedder, qdrant_repo=mock_qdrant)

        result = node(_base_state())

        assert "retrieved_chunks" in result
        assert len(result["retrieved_chunks"]) == 2

    def test_empty_search_returns_empty_list(self):
        mock_embedder, mock_qdrant = self._make_mocks(search_results=[])
        node = build_retrieve_node(embedder=mock_embedder, qdrant_repo=mock_qdrant)

        result = node(_base_state(score_threshold=0.99))

        assert result["retrieved_chunks"] == []

    def test_chunks_below_threshold_excluded_by_qdrant(self):
        """Qdrant filters by threshold server-side; the node returns whatever Qdrant returns."""
        # Qdrant would not return low-score chunks — simulate by returning only high ones.
        high_score_only = [_make_chunk("c-0", score=0.9)]
        mock_embedder, mock_qdrant = self._make_mocks(search_results=high_score_only)
        node = build_retrieve_node(embedder=mock_embedder, qdrant_repo=mock_qdrant)

        result = node(_base_state(score_threshold=0.8))

        assert len(result["retrieved_chunks"]) == 1
        assert result["retrieved_chunks"][0].score == 0.9


# ── TestAssembleNode ───────────────────────────────────────────────────────────


class TestAssembleNode:
    def test_returns_context_string_and_included_chunks(self):
        chunks = [_make_chunk("c-0", score=0.9, text="Hydraulic spec.")]
        node = build_assemble_node(max_context_chars=8192)

        result = node(_base_state(retrieved_chunks=chunks))

        assert "context_string" in result
        assert "included_chunks" in result

    def test_context_contains_chunk_text(self):
        chunks = [_make_chunk("c-0", score=0.9, text="Replace filter every 500 hours.")]
        node = build_assemble_node(max_context_chars=8192)

        result = node(_base_state(retrieved_chunks=chunks))

        assert "Replace filter every 500 hours." in result["context_string"]

    def test_sorts_chunks_by_score_descending(self):
        chunks = [
            _make_chunk("c-low", score=0.65, text="Low relevance."),
            _make_chunk("c-high", score=0.92, text="High relevance."),
            _make_chunk("c-mid", score=0.78, text="Mid relevance."),
        ]
        node = build_assemble_node(max_context_chars=8192)

        result = node(_base_state(retrieved_chunks=chunks))

        scores = [c.score for c in result["included_chunks"]]
        assert scores == sorted(scores, reverse=True)

    def test_highest_score_chunk_first_in_context(self):
        chunks = [
            _make_chunk("c-low", score=0.65, text="Low score text."),
            _make_chunk("c-high", score=0.92, text="High score text."),
        ]
        node = build_assemble_node(max_context_chars=8192)

        result = node(_base_state(retrieved_chunks=chunks))

        context = result["context_string"]
        assert context.index("High score text.") < context.index("Low score text.")

    def test_respects_character_budget(self):
        # Budget of 100 chars — only the highest-score chunk should fit.
        chunks = [
            _make_chunk("c-0", score=0.95, text="A" * 60),
            _make_chunk("c-1", score=0.80, text="B" * 60),
        ]
        node = build_assemble_node(max_context_chars=100)

        result = node(_base_state(retrieved_chunks=chunks))

        assert len(result["context_string"]) <= 100
        assert len(result["included_chunks"]) == 1
        assert result["included_chunks"][0].chunk_id == "c-0"

    def test_context_char_count_within_max_chars(self):
        chunks = [_make_chunk(f"c-{i}", score=0.9 - i * 0.05, text="word " * 40) for i in range(5)]
        node = build_assemble_node(max_context_chars=300)

        result = node(_base_state(retrieved_chunks=chunks))

        assert len(result["context_string"]) <= 300

    def test_empty_chunks_returns_empty_context(self):
        node = build_assemble_node(max_context_chars=8192)

        result = node(_base_state(retrieved_chunks=[]))

        assert result["context_string"] == ""
        assert result["included_chunks"] == []

    def test_all_chunks_included_when_within_budget(self):
        chunks = [_make_chunk(f"c-{i}", score=0.9 - i * 0.1, text="Short text.") for i in range(3)]
        node = build_assemble_node(max_context_chars=8192)

        result = node(_base_state(retrieved_chunks=chunks))

        assert len(result["included_chunks"]) == 3


# ── TestGenerateNode ───────────────────────────────────────────────────────────


class TestGenerateNode:
    def _make_llm_response(self, content: str) -> MagicMock:
        """Build a mock that mimics the ollama.Client.chat() response shape."""
        response = MagicMock()
        response.message.content = content
        return response

    def test_returns_answer_in_state(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = self._make_llm_response("The answer is 85°C.")
        node = build_generate_node(llm_client=mock_client, llm_model="llama3.2:3b")

        result = node(_base_state(context_string="[Source: manual.pdf, Page 1]\nTemp is 85°C."))

        assert result["answer"] == "The answer is 85°C."

    def test_answer_is_stripped(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = self._make_llm_response("  The answer.  \n")
        node = build_generate_node(llm_client=mock_client, llm_model="llama3.2:3b")

        result = node(_base_state(context_string="Some context."))

        assert result["answer"] == "The answer."

    def test_calls_llm_with_system_and_user_messages(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = self._make_llm_response("Answer.")
        node = build_generate_node(llm_client=mock_client, llm_model="llama3.2:3b")

        node(_base_state(context_string="Some context."))

        call_kwargs = mock_client.chat.call_args.kwargs
        messages = call_kwargs["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user"]

    def test_system_message_is_rag_prompt(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = self._make_llm_response("Answer.")
        node = build_generate_node(llm_client=mock_client, llm_model="llama3.2:3b")

        node(_base_state(context_string="context here"))

        messages = mock_client.chat.call_args.kwargs["messages"]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert system_msg["content"] == RAG_SYSTEM_PROMPT

    def test_user_prompt_contains_context(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = self._make_llm_response("Answer.")
        node = build_generate_node(llm_client=mock_client, llm_model="llama3.2:3b")
        context = "UNIQUE_CONTEXT_STRING_12345"

        node(_base_state(context_string=context))

        messages = mock_client.chat.call_args.kwargs["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert context in user_msg["content"]

    def test_user_prompt_contains_question(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = self._make_llm_response("Answer.")
        node = build_generate_node(llm_client=mock_client, llm_model="llama3.2:3b")
        question = "UNIQUE_QUESTION_STRING_99999"

        node(_base_state(question=question, context_string="some context"))

        messages = mock_client.chat.call_args.kwargs["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert question in user_msg["content"]

    def test_uses_configured_model_name(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = self._make_llm_response("Answer.")
        node = build_generate_node(llm_client=mock_client, llm_model="custom-model:7b")

        node(_base_state(context_string="context"))

        assert mock_client.chat.call_args.kwargs["model"] == "custom-model:7b"

    def test_connection_refused_sets_error_state(self):
        mock_client = MagicMock()
        mock_client.chat.side_effect = ConnectionRefusedError("Ollama not running")
        node = build_generate_node(llm_client=mock_client, llm_model="llama3.2:3b")

        result = node(_base_state(context_string="context"))

        assert result.get("error") == "service_unavailable"
        assert "answer" not in result

    def test_connection_error_sets_error_state(self):
        mock_client = MagicMock()
        mock_client.chat.side_effect = ConnectionError("Network unreachable")
        node = build_generate_node(llm_client=mock_client, llm_model="llama3.2:3b")

        result = node(_base_state(context_string="context"))

        assert result.get("error") == "service_unavailable"


# ── TestCiteNode ───────────────────────────────────────────────────────────────


class TestCiteNode:
    def test_returns_citations_in_state(self):
        chunks = [_make_chunk("c-0", score=0.85)]
        node = build_cite_node()

        result = node(_base_state(included_chunks=chunks))

        assert "citations" in result

    def test_one_citation_per_included_chunk(self):
        chunks = [_make_chunk(f"c-{i}") for i in range(4)]
        node = build_cite_node()

        result = node(_base_state(included_chunks=chunks))

        assert len(result["citations"]) == 4

    def test_empty_included_chunks_returns_empty_list(self):
        node = build_cite_node()

        result = node(_base_state(included_chunks=[]))

        assert result["citations"] == []

    def test_citation_count_equals_included_chunks(self):
        """Fundamental invariant: one citation per chunk that fit in context."""
        chunks = [_make_chunk(f"c-{i}", score=0.9 - i * 0.1) for i in range(3)]
        node = build_cite_node()

        result = node(_base_state(included_chunks=chunks))

        assert len(result["citations"]) == len(chunks)

    def test_citation_document_name_matches_filename(self):
        chunks = [_make_chunk("c-0", filename="hydraulic_manual.pdf")]
        node = build_cite_node()

        result = node(_base_state(included_chunks=chunks))

        assert result["citations"][0].document_name == "hydraulic_manual.pdf"

    def test_citation_page_number_matches_chunk(self):
        chunks = [_make_chunk("c-0", page_number=7)]
        node = build_cite_node()

        result = node(_base_state(included_chunks=chunks))

        assert result["citations"][0].page_number == 7

    def test_citation_score_rounded_to_4_decimal_places(self):
        chunks = [_make_chunk("c-0", score=0.8345678901)]
        node = build_cite_node()

        result = node(_base_state(included_chunks=chunks))

        assert result["citations"][0].relevance_score == 0.8346

    def test_citation_order_matches_chunk_order(self):
        """Citations preserve included_chunks order (already sorted by assembler)."""
        chunks = [
            _make_chunk("c-0", score=0.95, page_number=1),
            _make_chunk("c-1", score=0.82, page_number=3),
            _make_chunk("c-2", score=0.71, page_number=7),
        ]
        node = build_cite_node()

        result = node(_base_state(included_chunks=chunks))

        page_numbers = [c.page_number for c in result["citations"]]
        assert page_numbers == [1, 3, 7]

    def test_missing_included_chunks_defaults_to_empty(self):
        """Node should handle state that has no included_chunks key."""
        node = build_cite_node()
        state = _base_state()  # no included_chunks key

        result = node(state)

        assert result["citations"] == []
