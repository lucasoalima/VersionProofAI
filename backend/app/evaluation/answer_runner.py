"""Answer-level benchmark. Runs the AnswerEngine over a dataset and stores an EvaluationRun.

Metrics (all deterministic):
* correct_abstention_rate   abstained == should_abstain, over all questions
* applicability_accuracy    answer verdict == expected_applicability_status
* outdated_recommendation_rate  among questions with a known outdated source: the answer CITES it
* citation_validity_rate    cited chunk ids that exist in the supplied evidence and are not
                            verified-not-applicable, over all citations (None if no citations)
* supported_answer_rate     among answerable questions: at least one cited doc is a supporting doc
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.metrics import summarize
from app.generation.engine import AnswerEngine
from app.models import Document, EvaluationDataset, EvaluationRun
from app.retrieval.interfaces import RetrievalFilters


def run_answer_benchmark(
    db: Session,
    dataset: EvaluationDataset,
    engine: AnswerEngine,
    *,
    top_k: int = 5,
    label: str = "versionproof",
) -> EvaluationRun:
    gen = engine.llm.model_id if engine.llm else "extractive"
    run = EvaluationRun(
        dataset_id=dataset.id,
        strategy=f"answer:{label}:{engine.retriever.name}",
        config={"top_k": top_k, "dataset": f"{dataset.name}:{dataset.version}", "generation": gen},
        model_identifier=engine.llm.model_id if engine.llm else None,
    )
    db.add(run)
    db.flush()
    per_q, lat = [], []
    for rec in dataset.records:
        a = engine.answer(
            rec["question"],
            RetrievalFilters(product_slug=rec["product"], target_version=rec.get("target_version")),
            top_k,
        )
        by_chunk = {e.chunk_id: e for e in a.evidence}
        doc_ids = {by_chunk[c].document_id for c in a.citations if c in by_chunk}
        ext = (
            {
                str(d.id): d.external_id
                for d in db.scalars(
                    select(Document).where(Document.id.in_([uuid.UUID(i) for i in doc_ids]))
                )
            }
            if doc_ids
            else {}
        )
        cited_docs = sorted(set(ext.values()))
        relevant, outdated = (
            set(rec.get("supporting_document_ids", [])),
            set(rec.get("outdated_document_ids", [])),
        )
        valid = [
            c in by_chunk and by_chunk[c].applicability_status.value != "not_applicable"
            for c in a.citations
        ]
        lat.append(a.diagnostics.get("end_to_end_latency_ms", 0.0))
        per_q.append(
            {
                "id": rec["id"],
                "case": rec.get("case"),
                "target_version": rec.get("target_version"),
                "abstained": a.abstained,
                "should_abstain": rec.get("should_abstain", False),
                "abstention_correct": a.abstained == rec.get("should_abstain", False),
                "verdict": a.applicability_status,
                "expected": rec["expected_applicability_status"],
                "applicability_correct": a.applicability_status
                == rec["expected_applicability_status"],
                "cited_documents": cited_docs,
                "outdated_cited": bool(set(cited_docs) & outdated) if outdated else None,
                "citation_validity": (sum(valid) / len(valid)) if valid else None,
                "supported": (
                    bool(set(cited_docs) & relevant)
                    if not rec.get("should_abstain")
                    and rec["expected_applicability_status"] == "applies"
                    else None
                ),
                "generation_mode": a.generation_mode,
                "warnings": a.warnings,
                "answer": a.answer,
                "end_to_end_latency_ms": a.diagnostics.get("end_to_end_latency_ms"),
            }
        )
    run.per_question = per_q
    run.metrics = {
        "questions": len(per_q),
        "correct_abstention_rate": summarize([q["abstention_correct"] for q in per_q]),
        "applicability_accuracy": summarize([q["applicability_correct"] for q in per_q]),
        "outdated_recommendation_rate": summarize([q["outdated_cited"] for q in per_q]),
        "citation_validity_rate": summarize([q["citation_validity"] for q in per_q]),
        "supported_answer_rate": summarize([q["supported"] for q in per_q]),
        "end_to_end_latency_ms_p50": round(median(lat), 2) if lat else None,
    }
    run.finished_at = datetime.now(UTC)
    db.commit()
    return run
