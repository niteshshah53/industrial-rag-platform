"""
RAGAS metric computation for the Industrial RAG Platform.

Sets up RAGAS with Ollama as the LLM judge (no OpenAI dependency).
Computes Faithfulness, AnswerRelevancy, and ContextRecall.

RAGAS metric definitions:
  Faithfulness:     Are all claims in the answer supported by the retrieved context?
                    Measures hallucination. Higher = less hallucination.
  AnswerRelevancy:  Is the answer relevant to the question asked?
                    Measures response quality. Higher = more on-topic.
  ContextRecall:    Does the retrieved context contain the information needed
                    to answer the question? Measures retrieval quality.

Target scores (from PRD):
  Faithfulness    >= 0.80
  ContextRecall   >= 0.75
  AnswerRelevancy >= 0.80
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# RAGAS metric targets from PRD
FAITHFULNESS_TARGET = 0.80
ANSWER_RELEVANCY_TARGET = 0.80
CONTEXT_RECALL_TARGET = 0.75


def build_ragas_evaluator(
    llm_model: str = "llama3.2:3b",
    embedding_model: str = "nomic-embed-text",
    ollama_base_url: str = "http://localhost:11434",
):
    """
    Build RAGAS LLM and embeddings wrappers backed by Ollama.

    Args:
        llm_model:       Ollama model for LLM evaluation (judge).
        embedding_model: Ollama model for embedding-based metrics.
        ollama_base_url: Ollama service URL.

    Returns:
        Tuple of (evaluator_llm, evaluator_embeddings) ready for evaluate().
    """
    from langchain_ollama import ChatOllama, OllamaEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper

    evaluator_llm = LangchainLLMWrapper(
        ChatOllama(
            model=llm_model,
            base_url=ollama_base_url,
            temperature=0,  # Deterministic for reproducibility
        )
    )
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        OllamaEmbeddings(
            model=embedding_model,
            base_url=ollama_base_url,
        )
    )
    return evaluator_llm, evaluator_embeddings


def build_evaluation_dataset(pipeline_responses, ground_truths: list[str]):
    """
    Convert pipeline responses and ground truth strings into a RAGAS EvaluationDataset.

    Only includes samples that have a non-empty answer and at least one
    retrieved context. This filters out "No relevant documents found."
    responses which would artificially lower Faithfulness and ContextRecall.

    Args:
        pipeline_responses: List of PipelineResponse from pipeline_client.
        ground_truths:       Corresponding ground truth strings.

    Returns:
        Tuple of (EvaluationDataset, included_count) where included_count is
        the number of samples actually included (after filtering).
    """
    from ragas import EvaluationDataset
    from ragas.dataset_schema import SingleTurnSample

    samples = []
    for resp, truth in zip(pipeline_responses, ground_truths, strict=True):
        if not resp.has_answer or not resp.contexts:
            logger.debug("Skipping sample (no answer or no contexts): %s", resp.question[:60])
            continue
        samples.append(
            SingleTurnSample(
                user_input=resp.question,
                response=resp.answer,
                retrieved_contexts=resp.contexts,
                reference=truth,
            )
        )

    return EvaluationDataset(samples=samples), len(samples)


def run_evaluation(
    pipeline_responses,
    ground_truths: list[str],
    evaluator_llm,
    evaluator_embeddings,
) -> dict:
    """
    Run RAGAS evaluation and return a scores dictionary.

    Args:
        pipeline_responses:  List of PipelineResponse objects.
        ground_truths:        Ground truth strings matching pipeline_responses.
        evaluator_llm:       RAGAS-wrapped Ollama LLM for metric computation.
        evaluator_embeddings: RAGAS-wrapped Ollama embeddings.

    Returns:
        Dict with keys: faithfulness, answer_relevancy, context_recall.
        Scores are floats in [0, 1]; None if computation failed.
    """
    from ragas import evaluate
    from ragas.metrics import AnswerRelevancy, ContextRecall, Faithfulness

    dataset, included = build_evaluation_dataset(pipeline_responses, ground_truths)

    if included == 0:
        logger.warning("No evaluable samples (all returned no relevant documents).")
        return {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_recall": None,
            "evaluated_samples": 0,
        }

    logger.info("Running RAGAS evaluation on %d samples...", included)

    result = evaluate(
        dataset=dataset,
        metrics=[Faithfulness(), AnswerRelevancy(), ContextRecall()],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
    )

    scores = result.to_pandas()
    return {
        "faithfulness": float(scores["faithfulness"].mean()),
        "answer_relevancy": float(scores["answer_relevancy"].mean()),
        "context_recall": float(scores["context_recall"].mean()),
        "evaluated_samples": included,
    }


def compute_out_of_scope_accuracy(pipeline_responses, in_scope_flags: list[bool]) -> float:
    """
    Compute the fraction of out-of-scope questions correctly rejected.

    A correct rejection means the answer is "No relevant documents found."

    Args:
        pipeline_responses: All pipeline responses (in-scope + out-of-scope).
        in_scope_flags:      Boolean flags matching pipeline_responses.

    Returns:
        Fraction [0, 1] of out-of-scope questions correctly rejected.
    """
    out_of_scope = [
        r for r, flag in zip(pipeline_responses, in_scope_flags, strict=True) if not flag
    ]
    if not out_of_scope:
        return 1.0
    correct = sum(1 for r in out_of_scope if not r.has_answer)
    return correct / len(out_of_scope)


def format_report(
    scores: dict,
    config: dict,
    out_of_scope_accuracy: float | None = None,
) -> None:
    """Print a formatted evaluation report to stdout."""

    def _score_line(name: str, score: float | None, target: float) -> str:
        if score is None:
            return f"  {name:<22} N/A      (target: {target:.2f})"
        status = "✓" if score >= target else "✗"
        return f"  {name:<22} {score:.4f}  (target: {target:.2f})  {status}"

    print()
    print("=" * 60)
    print("RAGAS Evaluation Results")
    print("=" * 60)
    print(f"  Config:  {config.get('score_threshold', '?')} score threshold")
    print(f"  Samples: {scores.get('evaluated_samples', '?')} evaluated")
    print()
    print("  Metric                 Score    Target")
    print("  " + "-" * 48)
    print(_score_line("Faithfulness", scores.get("faithfulness"), FAITHFULNESS_TARGET))
    print(_score_line("Answer Relevancy", scores.get("answer_relevancy"), ANSWER_RELEVANCY_TARGET))
    print(_score_line("Context Recall", scores.get("context_recall"), CONTEXT_RECALL_TARGET))
    if out_of_scope_accuracy is not None:
        print(f"\n  Out-of-scope rejection: {out_of_scope_accuracy:.0%}")
    print("=" * 60)
    print()


def save_results(
    scores: dict,
    config: dict,
    pipeline_responses,
    out_path: str | Path,
) -> None:
    """
    Save evaluation results to a JSON file.

    Args:
        scores:             RAGAS metric scores dict.
        config:             Evaluation configuration dict (model names, threshold, etc.).
        pipeline_responses: All pipeline responses for per-sample logging.
        out_path:           Path to write the JSON file.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    per_sample = [
        {
            "question": r.question,
            "answer": r.answer,
            "has_answer": r.has_answer,
            "retrieval_count": r.retrieval_count,
            "context_chunks_used": r.context_chunks_used,
            "latency_ms": round(r.latency_ms, 1),
        }
        for r in pipeline_responses
    ]

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "config": config,
        "scores": {
            "faithfulness": scores.get("faithfulness"),
            "answer_relevancy": scores.get("answer_relevancy"),
            "context_recall": scores.get("context_recall"),
            "evaluated_samples": scores.get("evaluated_samples"),
        },
        "targets": {
            "faithfulness": FAITHFULNESS_TARGET,
            "answer_relevancy": ANSWER_RELEVANCY_TARGET,
            "context_recall": CONTEXT_RECALL_TARGET,
        },
        "targets_met": {
            "faithfulness": (scores.get("faithfulness") or 0) >= FAITHFULNESS_TARGET,
            "answer_relevancy": (scores.get("answer_relevancy") or 0) >= ANSWER_RELEVANCY_TARGET,
            "context_recall": (scores.get("context_recall") or 0) >= CONTEXT_RECALL_TARGET,
        },
        "per_sample": per_sample,
    }

    out_path.write_text(json.dumps(payload, indent=2))
    print(f"Results saved to: {out_path}")
