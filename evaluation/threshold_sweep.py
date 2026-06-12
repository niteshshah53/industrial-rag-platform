"""
Threshold sensitivity analysis for the RAG pipeline.

Runs the full RAGAS evaluation at multiple score_threshold values (0.4, 0.5,
0.6, 0.7) and produces a comparison table. The threshold that maximises the
harmonic mean of all three RAGAS metrics is recommended.

Usage:
    python evaluation/threshold_sweep.py
    python evaluation/threshold_sweep.py --thresholds 0.3 0.4 0.5 0.6 0.7 0.8
    python evaluation/threshold_sweep.py --skip-ragas   (pipeline-only, no RAGAS scoring)

Outputs:
    evaluation/results/threshold_sweep.json — per-threshold scores
    Console comparison table with recommendation
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATASET_PATH = Path(__file__).parent / "datasets" / "industrial_qa.json"
SWEEP_OUTPUT = Path(__file__).parent / "results" / "threshold_sweep.json"

DEFAULT_THRESHOLDS = [0.4, 0.5, 0.6, 0.7]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _harmonic_mean(values: list[float]) -> float:
    """Compute the harmonic mean of a list of positive floats."""
    valid = [v for v in values if v and v > 0]
    if not valid:
        return 0.0
    return len(valid) / sum(1.0 / v for v in valid)


def _format_table(sweep_results: list[dict]) -> None:
    """Print a comparison table of all threshold runs."""
    print()
    print("=" * 75)
    print("Threshold Sensitivity Analysis")
    print("=" * 75)
    print(
        f"  {'Threshold':>10}  {'Faithfulness':>14}  "
        f"{'Ans.Relevancy':>14}  {'Ctx.Recall':>11}  {'HMean':>7}"
    )
    print("  " + "-" * 68)

    for r in sweep_results:
        thr = r["threshold"]
        s = r["scores"]
        faith = s.get("faithfulness")
        relev = s.get("answer_relevancy")
        recall = s.get("context_recall")
        hmean = r.get("harmonic_mean", 0.0)

        faith_str = f"{faith:.4f}" if faith is not None else "  N/A  "
        relev_str = f"{relev:.4f}" if relev is not None else "  N/A  "
        recall_str = f"{recall:.4f}" if recall is not None else "  N/A  "

        print(
            f"  {thr:>10.2f}  {faith_str:>14}  " f"{relev_str:>14}  {recall_str:>11}  {hmean:>7.4f}"
        )

    print("=" * 75)


def _recommend_threshold(sweep_results: list[dict]) -> float | None:
    """Return the threshold with the highest harmonic mean of all three metrics."""
    best = max(sweep_results, key=lambda r: r.get("harmonic_mean", 0.0))
    return best["threshold"] if best.get("harmonic_mean", 0.0) > 0 else None


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sweep score thresholds and compare RAGAS metrics."
    )
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=DEFAULT_THRESHOLDS,
        help=f"Threshold values to evaluate (default: {DEFAULT_THRESHOLDS})",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="RAG API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--llm-model",
        default="llama3.2:3b",
        help="Ollama judge LLM model (default: llama3.2:3b)",
    )
    parser.add_argument(
        "--embedding-model",
        default="nomic-embed-text",
        help="Ollama embedding model (default: nomic-embed-text)",
    )
    parser.add_argument(
        "--skip-ragas",
        action="store_true",
        help="Collect pipeline responses only; skip RAGAS scoring.",
    )
    parser.add_argument(
        "--output",
        default=str(SWEEP_OUTPUT),
        help=f"Output JSON path (default: {SWEEP_OUTPUT})",
    )
    args = parser.parse_args()

    print()
    print("Industrial RAG Platform — Threshold Sensitivity Analysis")
    print("=" * 60)
    print(f"Thresholds to sweep: {args.thresholds}")

    # Load dataset
    import json as _json

    data = _json.loads(DATASET_PATH.read_text())
    samples = data["samples"]
    questions = [s["question"] for s in samples]
    ground_truths = [s["ground_truth"] for s in samples]
    in_scope_flags = [s["in_scope"] for s in samples]

    in_scope_truths = [t for t, f in zip(ground_truths, in_scope_flags, strict=True) if f]

    # Build RAGAS evaluator once (shared across thresholds)
    evaluator_llm = evaluator_embeddings = None
    if not args.skip_ragas:
        from evaluation.metrics import build_ragas_evaluator

        print("\nInitialising RAGAS evaluator...")
        evaluator_llm, evaluator_embeddings = build_ragas_evaluator(
            llm_model=args.llm_model,
            embedding_model=args.embedding_model,
            ollama_base_url=args.ollama_url,
        )

    from evaluation.metrics import run_evaluation
    from evaluation.pipeline_client import PipelineClient

    sweep_results = []

    for threshold in args.thresholds:
        print(f"\n── Threshold {threshold:.2f} ─────────────────────────────────")

        client = PipelineClient(base_url=args.base_url, score_threshold=threshold)
        all_responses = client.query_batch(questions, verbose=True)
        in_scope_responses = [r for r, f in zip(all_responses, in_scope_flags, strict=True) if f]

        if args.skip_ragas or evaluator_llm is None:
            scores = {
                "faithfulness": None,
                "answer_relevancy": None,
                "context_recall": None,
                "evaluated_samples": 0,
            }
        else:
            print(f"Running RAGAS evaluation at threshold={threshold}...")
            scores = run_evaluation(
                pipeline_responses=in_scope_responses,
                ground_truths=in_scope_truths,
                evaluator_llm=evaluator_llm,
                evaluator_embeddings=evaluator_embeddings,
            )

        hmean = _harmonic_mean(
            [v for k, v in scores.items() if k != "evaluated_samples" and v is not None]
        )

        sweep_results.append(
            {
                "threshold": threshold,
                "scores": scores,
                "harmonic_mean": hmean,
            }
        )
        print(
            f"  faithfulness={scores.get('faithfulness', 'N/A')!r}  "
            f"answer_relevancy={scores.get('answer_relevancy', 'N/A')!r}  "
            f"context_recall={scores.get('context_recall', 'N/A')!r}  "
            f"hmean={hmean:.4f}"
        )

    # ── Results table ──────────────────────────────────────────────────────────
    _format_table(sweep_results)

    recommended = _recommend_threshold(sweep_results)
    if recommended is not None:
        print(f"\n  Recommended threshold: {recommended:.2f}")
        print(
            "  (Threshold with highest harmonic mean of Faithfulness, "
            "Answer Relevancy, and Context Recall)"
        )
    print()

    # ── Save results ──────────────────────────────────────────────────────────
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "sweep_config": {
                    "thresholds": args.thresholds,
                    "llm_model": args.llm_model,
                    "embedding_model": args.embedding_model,
                    "base_url": args.base_url,
                },
                "results": sweep_results,
                "recommended_threshold": recommended,
            },
            indent=2,
        )
    )
    print(f"Sweep results saved to: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
