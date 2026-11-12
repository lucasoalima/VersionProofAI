from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.comparison.engine import ComparisonEngine
from app.core.config import settings
from app.db.session import get_db
from app.embeddings.indexer import build_embeddings
from app.embeddings.interfaces import EmbeddingUnavailable
from app.embeddings.providers import get_embedding_provider
from app.evaluation.answer_runner import run_answer_benchmark
from app.evaluation.retrieval_runner import run_retrieval_benchmark
from app.generation.engine import AnswerEngine
from app.generation.interfaces import LLMUnavailable
from app.generation.providers import get_llm_provider
from app.ingestion.paths import ForbiddenPathError, resolve_within_root
from app.ingestion.pipeline import IngestionPipeline
from app.models import EvaluationDataset, EvaluationRun, IngestionJob, QueryLog
from app.retrieval.factory import build_retriever
from app.retrieval.interfaces import RetrievalFilters
from app.retrieval.service import retrieve_with_exclusions
from app.schemas.api import (
    AnswerOut,
    AskRequest,
    ChunkOut,
    DashboardOut,
    DocumentDetailOut,
    DocumentOut,
    EvidenceOut,
    IngestionJobOut,
    IngestionRequest,
    ProductDetailOut,
    ProductOut,
    SearchRequest,
    SearchResponse,
)
from app.services import catalog
from app.versioning.ordering import VersionOrderingError

router = APIRouter(prefix="/api")


def capabilities() -> dict:
    return {
        "lexical_retrieval": True,
        "semantic_retrieval": settings.embedding_provider != "none",
        "hybrid_retrieval": settings.embedding_provider != "none",
        "answer_generation": settings.llm_provider != "none",
        "embedding_provider": settings.embedding_provider,
        "llm_provider": settings.llm_provider,
    }


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    from sqlalchemy import text

    try:
        db.execute(text("SELECT 1"))
        pgvector = db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname='vector'")
        ).scalar()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"database unavailable: {type(exc).__name__}"
        ) from exc
    return {"status": "ok", "database": "ok", "pgvector": pgvector, "capabilities": capabilities()}


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db)):
    return catalog.dashboard(db, capabilities())


@router.get("/products", response_model=list[ProductOut])
def get_products(db: Session = Depends(get_db)):
    return catalog.list_products(db)


@router.get("/products/{slug}", response_model=ProductDetailOut)
def get_product(slug: str, db: Session = Depends(get_db)):
    p = catalog.get_product(db, slug)
    if p is None:
        raise HTTPException(404, "product not found")
    return p


@router.get("/documents", response_model=list[DocumentOut])
def get_documents(
    product: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return catalog.list_documents(db, product, limit, offset)


@router.get("/documents/{doc_id}", response_model=DocumentDetailOut)
def get_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    d = catalog.get_document(db, doc_id)
    if d is None:
        raise HTTPException(404, "document not found")
    return d


@router.get("/revisions/{revision_id}/chunks", response_model=list[ChunkOut])
def get_chunks(revision_id: uuid.UUID, db: Session = Depends(get_db)):
    return catalog.list_chunks(db, revision_id)


@router.get("/ingestion/jobs", response_model=list[IngestionJobOut])
def get_jobs(db: Session = Depends(get_db)):
    return catalog.list_jobs(db)


@router.get("/ingestion/jobs/{job_id}", response_model=IngestionJobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    j = db.get(IngestionJob, job_id)
    if j is None:
        raise HTTPException(404, "job not found")
    return catalog.job_out(j)


@router.post("/ingestion/local", response_model=IngestionJobOut, status_code=201)
def ingest_local(req: IngestionRequest, db: Session = Depends(get_db)):
    """Ingest files under INGESTION_ROOT. Synchronous by design for Phase 1 (small fixtures)."""
    try:
        path = resolve_within_root(req.path, settings.resolved_ingestion_root)
    except ForbiddenPathError as exc:
        raise HTTPException(403, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, f"path not found under ingestion root: {req.path}") from exc
    pipeline = IngestionPipeline(db)
    try:
        result = pipeline.ingest_path(path)
    except Exception as exc:
        raise HTTPException(500, f"ingestion failed: {type(exc).__name__}: {exc}") from exc
    job = db.get(IngestionJob, uuid.UUID(result.job_id))
    return catalog.job_out(job)


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, db: Session = Depends(get_db)):
    filters = RetrievalFilters(
        product_slug=req.product,
        target_version=req.target_version,
        category=req.category,
        min_trust=req.min_trust,
        enforce_version=req.enforce_version,
    )
    try:
        retriever = build_retriever(db, req.mode)
    except EmbeddingUnavailable as exc:
        raise HTTPException(501, str(exc)) from exc
    t0 = time.perf_counter()
    try:
        outcome = retrieve_with_exclusions(retriever, req.query, filters, req.top_k)
        results = outcome.results
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except VersionOrderingError as exc:
        raise HTTPException(422, str(exc)) from exc
    latency = (time.perf_counter() - t0) * 1000
    notices: list[str] = []
    if req.target_version is None:
        notices.append(
            "No target version supplied: applicability cannot be assessed; results are unfiltered."
        )
    unknown = sum(1 for r in results if r.applicability_status.value == "unknown")
    if outcome.excluded:
        notices.append(
            f"{len(outcome.excluded)} relevant source(s) are verified NOT applicable to {req.target_version} and are listed separately; they must not be used as recommendations."
        )
    if req.target_version and unknown:
        notices.append(
            f"{unknown} result(s) have unknown applicability for {req.target_version}; treat them as unverified."
        )
    return SearchResponse(
        query=req.query,
        product=req.product,
        target_version=req.target_version,
        mode=req.mode,
        enforce_version=req.enforce_version,
        results=[
            EvidenceOut(**{**r.__dict__, "applicability_status": r.applicability_status.value})
            for r in results
        ],
        excluded=[
            EvidenceOut(**{**r.__dict__, "applicability_status": r.applicability_status.value})
            for r in outcome.excluded
        ],
        retrieval_latency_ms=round(latency, 2),
        notices=notices,
    )


@router.post("/embeddings/build")
def build_embeddings_endpoint(db: Session = Depends(get_db)):
    """Embed every chunk lacking a vector from the configured model. Synchronous (Phase 2)."""
    try:
        provider = get_embedding_provider()
    except EmbeddingUnavailable as exc:
        raise HTTPException(501, str(exc)) from exc
    if provider is None:
        raise HTTPException(
            501, "EMBEDDING_PROVIDER is 'none'; configure a provider to build embeddings."
        )
    res = build_embeddings(db, provider)
    return {"model_id": res.model_id, "embedded": res.embedded, "skipped": res.skipped}


@router.get("/evaluation/datasets")
def list_datasets(db: Session = Depends(get_db)):
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "version": d.version,
            "split": d.split,
            "is_synthetic": d.is_synthetic,
            "records": len(d.records or []),
            "description": d.description,
        }
        for d in db.scalars(
            select(EvaluationDataset).order_by(EvaluationDataset.name, EvaluationDataset.version)
        )
    ]


class RetrievalBenchmarkRequest(BaseModel):
    dataset_id: uuid.UUID
    mode: str = Field(default="lexical", pattern="^(lexical|semantic|hybrid)$")
    enforce_version: bool = True
    top_k: int = Field(default=5, ge=1, le=50)


def _run_out(r: EvaluationRun) -> dict:
    return {
        "id": str(r.id),
        "dataset_id": str(r.dataset_id),
        "strategy": r.strategy,
        "config": r.config,
        "model_identifier": r.model_identifier,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "metrics": r.metrics,
        "per_question": r.per_question,
    }


@router.post("/evaluation/retrieval-runs", status_code=201)
def create_retrieval_run(req: RetrievalBenchmarkRequest, db: Session = Depends(get_db)):
    dataset = db.get(EvaluationDataset, req.dataset_id)
    if dataset is None:
        raise HTTPException(404, "dataset not found")
    try:
        retriever = build_retriever(db, req.mode)
    except EmbeddingUnavailable as exc:
        raise HTTPException(501, str(exc)) from exc
    provider = get_embedding_provider() if req.mode != "lexical" else None
    run = run_retrieval_benchmark(
        db,
        dataset,
        retriever,
        enforce_version=req.enforce_version,
        top_k=req.top_k,
        model_identifier=provider.model_id if provider else None,
    )
    return _run_out(run)


@router.get("/evaluation/runs")
def list_runs(db: Session = Depends(get_db)):
    return [
        _run_out(r)
        for r in db.scalars(
            select(EvaluationRun).order_by(EvaluationRun.started_at.desc()).limit(50)
        )
    ]


@router.get("/evaluation/runs/{run_id}")
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.get(EvaluationRun, run_id)
    if r is None:
        raise HTTPException(404, "run not found")
    return _run_out(r)


@router.get("/evaluation/runs/{run_id}/export.csv")
def export_run_csv(run_id: uuid.UUID, db: Session = Depends(get_db)):
    import csv
    import io

    from fastapi.responses import PlainTextResponse

    r = db.get(EvaluationRun, run_id)
    if r is None:
        raise HTTPException(404, "run not found")
    buf = io.StringIO()
    cols = [
        "id",
        "case",
        "target_version",
        "recall_at_k",
        "mrr",
        "ndcg_at_k",
        "outdated_surfaced",
        "applicability_correct",
        "top_applicability_status",
        "should_abstain",
        "retrieval_latency_ms",
        "error",
    ]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(r.per_question or [])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


def _ev_out(e) -> EvidenceOut:
    return EvidenceOut(**{**e.__dict__, "applicability_status": e.applicability_status.value})


@router.post("/ask", response_model=AnswerOut)
def ask(req: AskRequest, db: Session = Depends(get_db)):
    """Grounded answer. Works without an LLM (extractive mode); the verdict, abstention and
    citation checks are deterministic either way."""
    try:
        retriever = build_retriever(db, req.mode)
    except EmbeddingUnavailable as exc:
        raise HTTPException(501, str(exc)) from exc
    try:
        llm = get_llm_provider()
    except LLMUnavailable as exc:
        raise HTTPException(503, f"LLM provider misconfigured: {exc}") from exc
    filters = RetrievalFilters(product_slug=req.product, target_version=req.target_version)
    try:
        a = AnswerEngine(db, retriever, llm).answer(req.question, filters, req.top_k)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except VersionOrderingError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(
        QueryLog(
            product_slug=req.product,
            target_version=req.target_version,
            mode=req.mode,
            question=req.question,
            applicability_status=a.applicability_status,
            abstained=a.abstained,
            generation_mode=a.generation_mode,
            latency_ms=int(a.diagnostics.get("end_to_end_latency_ms", 0)),
        )
    )
    db.commit()
    return AnswerOut(
        **{
            **a.__dict__,
            "evidence": [_ev_out(e) for e in a.evidence],
            "excluded": [_ev_out(e) for e in a.excluded],
        }
    )


@router.post("/evaluation/answer-runs", status_code=201)
def create_answer_run(req: RetrievalBenchmarkRequest, db: Session = Depends(get_db)):
    """Answer-level benchmark with the version-aware engine (extractive unless an LLM is configured)."""
    dataset = db.get(EvaluationDataset, req.dataset_id)
    if dataset is None:
        raise HTTPException(404, "dataset not found")
    try:
        retriever = build_retriever(db, req.mode)
        llm = get_llm_provider()
    except EmbeddingUnavailable as exc:
        raise HTTPException(501, str(exc)) from exc
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return _run_out(
        run_answer_benchmark(db, dataset, AnswerEngine(db, retriever, llm), top_k=req.top_k)
    )


@router.get("/compare")
def compare(
    product: str,
    earlier: str,
    later: str,
    topic: str | None = Query(None, max_length=200),
    db: Session = Depends(get_db),
):
    """Deterministic documentation comparison between two releases (no LLM)."""
    try:
        return ComparisonEngine(db).compare(product, earlier, later, topic)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (VersionOrderingError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/products/{slug}/timeline")
def timeline(slug: str, db: Session = Depends(get_db)):
    try:
        return ComparisonEngine(db).timeline(slug)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
