"""Retrieval-only benchmark: runs every dataset record through a retriever and stores an
EvaluationRun with per-question results. No LLM involved; nothing is estimated."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation import metrics as m
from app.models import Document, EvaluationDataset, EvaluationRun
from app.retrieval.interfaces import RetrievalFilters, Retriever
from app.retrieval.service import retrieve_with_exclusions


def _doc_external_ids(db: Session, evidences) -> list[str]:
    ids = {e.document_id for e in evidences}
    if not ids:
        return []
    lookup = {
        str(d.id): d.external_id
        for d in db.scalars(
            select(Document).where(Document.id.in_([__import__("uuid").UUID(i) for i in ids]))
        )
    }
    out: list[str] = []
    for e in evidences:
        ext = lookup.get(e.document_id)
        if ext and ext not in out:
            out.append(ext)
    return out


def run_retrieval_benchmark(
    db: Session,
    dataset: EvaluationDataset,
    retriever: Retriever,
    *,
    enforce_version: bool,
    top_k: int = 5,
    config: dict | None = None,
    model_identifier: str | None = None,
) -> EvaluationRun:
    strategy = f"{retriever.name}:{'version_constrained' if enforce_version else 'unconstrained'}"
    run = EvaluationRun(
        dataset_id=dataset.id,
        strategy=strategy,
        config={
            "top_k": top_k,
            "enforce_version": enforce_version,
            "dataset": f"{dataset.name}:{dataset.version}",
            **(config or {}),
        },
        model_identifier=model_identifier,
    )
    db.add(run)
    db.flush()
    per_q: list[dict] = []
    latencies: list[float] = []
    for rec in dataset.records:
        relevant = set(rec.get("supporting_document_ids", []))
        outdated = set(rec.get("outdated_document_ids", []))
        filters = RetrievalFilters(
            product_slug=rec["product"],
            target_version=rec.get("target_version"),
            enforce_version=enforce_version,
        )
        t0 = time.perf_counter()
        error = None
        try:
            outcome = retrieve_with_exclusions(retriever, rec["question"], filters, top_k)
            evid, excluded = outcome.results, outcome.excluded
        except Exception as exc:
            evid, excluded, error = [], [], f"{type(exc).__name__}: {exc}"
        latency = (time.perf_counter() - t0) * 1000
        latencies.append(latency)
        ranked = _doc_external_ids(db, evid)
        excluded_docs = _doc_external_ids(db, excluded)
        expected = rec["expected_applicability_status"]
        # Expected not_applicable: correct when a supporting doc was found AND classified as not
        # applicable (surfaced in the excluded list), or when the top result itself says so.
        if expected == "not_applicable":
            applic_ok = bool(set(excluded_docs) & relevant) or (
                bool(evid) and evid[0].applicability_status.value == "not_applicable"
            )
        else:
            applic_ok = m.applicability_accuracy(
                evid[0].applicability_status.value if evid else None, expected
            )
        gains = {d: 1.0 for d in relevant} | {d: 0.0 for d in outdated}
        top_status = evid[0].applicability_status.value if evid else None
        per_q.append(
            {
                "id": rec["id"],
                "case": rec.get("case"),
                "target_version": rec.get("target_version"),
                "ranked_documents": ranked,
                "excluded_documents": excluded_docs,
                "recall_at_k": m.recall_at_k(ranked, relevant, top_k),
                "mrr": m.mrr(ranked, relevant),
                "ndcg_at_k": m.ndcg_at_k(ranked, gains, top_k),
                "outdated_surfaced": m.outdated_in_top_k(ranked, outdated, top_k)
                if outdated
                else None,
                "applicability_correct": applic_ok,
                "top_applicability_status": top_status,
                "should_abstain": rec.get("should_abstain", False),
                "retrieval_latency_ms": round(latency, 2),
                "error": error,
            }
        )
    run.per_question = per_q
    run.metrics = {
        "questions": len(per_q),
        "recall_at_k": m.summarize([q["recall_at_k"] for q in per_q]),
        "mrr": m.summarize([q["mrr"] for q in per_q]),
        "ndcg_at_k": m.summarize([q["ndcg_at_k"] for q in per_q]),
        "outdated_surfaced_rate": m.summarize([q["outdated_surfaced"] for q in per_q]),
        "applicability_accuracy": m.summarize([q["applicability_correct"] for q in per_q]),
        "retrieval_latency_ms_p50": round(median(latencies), 2) if latencies else None,
        "retrieval_latency_ms_max": round(max(latencies), 2) if latencies else None,
        "errors": sum(1 for q in per_q if q["error"]),
    }
    run.finished_at = datetime.now(UTC)
    db.commit()
    return run
