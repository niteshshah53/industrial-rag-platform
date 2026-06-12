"""
RAGAS evaluation entry point.

Loads the benchmark dataset, queries the live RAG pipeline for each question,
runs RAGAS evaluation with Ollama as the LLM judge, prints a report, and saves
the results JSON.

Usage:
    python evaluation/run_ragas.py
    python evaluation/run_ragas.py --score-threshold 0.5
    python evaluation/run_ragas.py --base-url http://localhost:8000 --output evaluation/results/run_001.json

Run via Makefile:
    make eval

Prerequisites:
  - The RAG platform must be running (make dev)
  - Demo documents must be seeded (make demo)
  - Ollama must have llama3.2:3b and nomic-embed-text pulled (make pull-models)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.WARNING,  # Suppress RAGAS/LangChain verbose output
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

DATASET_PATH = Path(__file__).parent / "datasets" / "industrial_qa.json"
DEFAULT_OUTPUT = Path(__file__).parent / "results" / "baseline.json"


# ── Helpers ───────────────────────────────────────────────────────────────────


def load_dataset(path: Path) -> tuple[list[str], list[str], list[bool]]:
    """
    Load the benchmark dataset.

    Returns:
        Tuple of (questions, ground_truths, in_scope_flags).
    """
    data = json.loads(path.read_text())
    samples = data["samples"]
    questions = [s["question"] for s in samples]
    ground_truths = [s["ground_truth"] for s in samples]
    in_scope_flags = [s["in_scope"] for s in samples]
    return questions, ground_truths, in_scope_flags


def check_prerequisites(base_url: str, ollama_url: str) -> bool:
    """Check that the API and Ollama are reachable."""
    import httpx

    ok = True

    try:
        r = httpx.get(f"{base_url}/v1/health/live", timeout=5.0)
        if r.status_code == 200:
            print(f"  ✓ RAG API reachable at {base_url}")
        else:
            print(f"  ✗ RAG API returned HTTP {r.status_code}")
            ok = False
    except Exception as e:
        print(f"  ✗ RAG API unreachable at {base_url}: {e}")
        ok = False

    try:
        r = httpx.get(f"{ollama_url}/api/tags", timeout=5.0)
        if r.status_code == 200:
            print(f"  ✓ Ollama reachable at {ollama_url}")
        else:
            print(f"  ✗ Ollama returned HTTP {r.status_code}")
            ok = False
    except Exception as e:
        print(f"  ✗ Ollama unreachable at {ollama_url}: {e}")
        ok = False

    return ok


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run RAGAS evaluation against the Industrial RAG Platform."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="RAG API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama base URL for RAGAS judge LLM (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.6,
        help="Retrieval score threshold for pipeline queries (default: 0.6)",
    )
    parser.add_argument(
        "--llm-model",
        default="llama3.2:3b",
        help="Ollama model to use as RAGAS judge LLM (default: llama3.2:3b)",
    )
    parser.add_argument(
        "--embedding-model",
        default="nomic-embed-text",
        help="Ollama model for RAGAS embedding metrics (default: nomic-embed-text)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--skip-ragas",
        action="store_true",
        help="Query the pipeline and save per-sample results, but skip RAGAS scoring.",
    )
    args = parser.parse_args()

    print()
    print("Industrial RAG Platform — RAGAS Evaluation")
    print("=" * 60)

    # ── Prerequisite checks ───────────────────────────────────────────────────
    print("\nChecking prerequisites...")
    if not check_prerequisites(args.base_url, args.ollama_url):
        print(
            "\nPrerequisite check failed. Start the platform with:\n"
            "  make dev\n"
            "  make demo  (seed demo documents)\n"
        )
        return 1

    # ── Load dataset ──────────────────────────────────────────────────────────
    print(f"\nLoading dataset from {DATASET_PATH}...")
    questions, ground_truths, in_scope_flags = load_dataset(DATASET_PATH)
    in_scope_truths = [t for t, f in zip(ground_truths, in_scope_flags, strict=True) if f]
    print(
        f"  {len(questions)} total samples "
        f"({sum(in_scope_flags)} in-scope, "
        f"{len(questions) - sum(in_scope_flags)} out-of-scope)"
    )

    # ── Query pipeline ────────────────────────────────────────────────────────
    from evaluation.pipeline_client import PipelineClient

    client = PipelineClient(
        base_url=args.base_url,
        score_threshold=args.score_threshold,
    )

    print(f"\nQuerying pipeline (threshold={args.score_threshold})...")
    all_responses = client.query_batch(questions, verbose=True)
    in_scope_responses = [r for r, f in zip(all_responses, in_scope_flags, strict=True) if f]

    # ── Out-of-scope accuracy ─────────────────────────────────────────────────
    from evaluation.metrics import compute_out_of_scope_accuracy

    oos_accuracy = compute_out_of_scope_accuracy(all_responses, in_scope_flags)
    print(f"\n  Out-of-scope rejection accuracy: {oos_accuracy:.0%}")

    # ── RAGAS scoring ─────────────────────────────────────────────────────────
    config = {
        "base_url": args.base_url,
        "score_threshold": args.score_threshold,
        "llm_model": args.llm_model,
        "embedding_model": args.embedding_model,
        "ollama_url": args.ollama_url,
        "dataset": str(DATASET_PATH),
    }

    if args.skip_ragas:
        print("\n--skip-ragas flag set; skipping RAGAS metric computation.")
        scores = {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_recall": None,
            "evaluated_samples": 0,
        }
    else:
        from evaluation.metrics import build_ragas_evaluator, run_evaluation

        print("\nInitialising RAGAS evaluator (Ollama judge)...")
        evaluator_llm, evaluator_embeddings = build_ragas_evaluator(
            llm_model=args.llm_model,
            embedding_model=args.embedding_model,
            ollama_base_url=args.ollama_url,
        )

        print("Running RAGAS evaluation...")
        scores = run_evaluation(
            pipeline_responses=in_scope_responses,
            ground_truths=in_scope_truths,
            evaluator_llm=evaluator_llm,
            evaluator_embeddings=evaluator_embeddings,
        )

    # ── Report + save ─────────────────────────────────────────────────────────
    from evaluation.metrics import format_report, save_results

    format_report(scores, config, out_of_scope_accuracy=oos_accuracy)
    save_results(
        scores=scores,
        config=config,
        pipeline_responses=all_responses,
        out_path=args.output,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
