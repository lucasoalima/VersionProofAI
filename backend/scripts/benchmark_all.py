"""Full comparison: baseline A (if an LLM is configured), B (traditional RAG) and C (VersionProof)
on every registered dataset. Writes reports/benchmark_<timestamp>.{json,csv}.

    EMBEDDING_PROVIDER=hashed python scripts/benchmark_all.py [--mode hybrid]
"""

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.embeddings.indexer import build_embeddings
from app.embeddings.providers import get_embedding_provider
from app.evaluation.answer_runner import run_answer_benchmark
from app.generation.baselines import NoRetrievalEngine, TraditionalRagEngine
from app.generation.engine import AnswerEngine
from app.generation.providers import get_llm_provider
from app.models import EvaluationDataset
from app.retrieval.factory import build_retriever

KEYS = [
    "correct_abstention_rate",
    "applicability_accuracy",
    "outdated_recommendation_rate",
    "citation_validity_rate",
    "supported_answer_rate",
    "end_to_end_latency_ms_p50",
]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mode",
        default=None,
        help="lexical | semantic | hybrid (default: hybrid if embeddings are configured, else lexical)",
    )
    args = ap.parse_args()
    rows = []
    with SessionLocal() as db:
        provider, llm = get_embedding_provider(), get_llm_provider()
        if provider:
            build_embeddings(db, provider)
        mode = args.mode or ("hybrid" if provider else "lexical")
        print(
            f"retrieval={mode} embedding={provider.model_id if provider else 'none'} generation={'llm:' + llm.model_id if llm else 'extractive'}"
        )
        if llm is None:
            print(
                "baseline A (no retrieval) SKIPPED: requires an LLM provider; it is not simulated."
            )
        for ds in db.scalars(select(EvaluationDataset).order_by(EvaluationDataset.name)):
            engines = ([NoRetrievalEngine(llm)] if llm else []) + [
                TraditionalRagEngine(db, build_retriever(db, mode), llm),
                AnswerEngine(db, build_retriever(db, mode), llm),
            ]
            print(f"\n{ds.name}:{ds.version} [{ds.split}] n={len(ds.records)}")
            print(f"  {'strategy':34} " + " ".join(f"{k[:14]:>14}" for k in KEYS))
            for eng in engines:
                run = run_answer_benchmark(db, ds, eng)
                print(f"  {run.strategy:34} " + " ".join(f"{run.metrics[k]!s:>14}" for k in KEYS))
                rows.append(
                    {
                        "dataset": f"{ds.name}:{ds.version}",
                        "split": ds.split,
                        "strategy": run.strategy,
                        "run_id": str(run.id),
                        "model": run.model_identifier,
                        "embedding": provider.model_id if provider else None,
                        **{k: run.metrics[k] for k in KEYS},
                        "misses": [
                            q["id"]
                            for q in run.per_question
                            if not (q["abstention_correct"] and q["applicability_correct"])
                        ],
                    }
                )
    out = Path(__file__).resolve().parents[2] / "reports"
    out.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (out / f"benchmark_{stamp}.json").write_text(json.dumps(rows, indent=2))
    with (out / f"benchmark_{stamp}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nreports written to {out}/benchmark_{stamp}.json|csv")
