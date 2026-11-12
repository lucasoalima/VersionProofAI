"""Run the retrieval-only benchmark for every mode × version-constraint combination.

    EMBEDDING_PROVIDER=hashed python scripts/benchmark_retrieval.py [--dataset nimbus-synthetic:1] [--top-k 5]

Semantic/hybrid are skipped (not faked) when no embedding provider is configured.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.embeddings.indexer import build_embeddings  # noqa: E402
from app.embeddings.providers import get_embedding_provider  # noqa: E402
from app.evaluation.retrieval_runner import run_retrieval_benchmark  # noqa: E402
from app.models import EvaluationDataset  # noqa: E402
from app.retrieval.factory import build_retriever  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="nimbus-synthetic:1")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()
    name, version = args.dataset.split(":")
    with SessionLocal() as db:
        ds = db.scalar(select(EvaluationDataset).where(EvaluationDataset.name == name, EvaluationDataset.version == version))
        if ds is None:
            sys.exit(f"dataset {args.dataset} not registered; run scripts/seed.py")
        provider = get_embedding_provider()
        modes = ["lexical"]
        if provider:
            r = build_embeddings(db, provider)
            print(f"embeddings: model={r.model_id} embedded={r.embedded} skipped={r.skipped}")
            modes += ["semantic", "hybrid"]
        else:
            print("EMBEDDING_PROVIDER=none: semantic/hybrid skipped")
        print(f"{'strategy':34} recall@k  mrr     ndcg@k  outdated  applic  p50ms")
        for mode in modes:
            for enforce in (True, False):
                run = run_retrieval_benchmark(db, ds, build_retriever(db, mode), enforce_version=enforce, top_k=args.top_k,
                                              model_identifier=provider.model_id if provider and mode != "lexical" else None)
                m = run.metrics
                print(f"{run.strategy:34} {m['recall_at_k']!s:9} {m['mrr']!s:7} {m['ndcg_at_k']!s:7} {m['outdated_surfaced_rate']!s:9} {m['applicability_accuracy']!s:7} {m['retrieval_latency_ms_p50']}")
