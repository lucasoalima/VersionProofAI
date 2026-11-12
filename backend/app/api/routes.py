from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.ingestion.paths import ForbiddenPathError, resolve_within_root
from app.ingestion.pipeline import IngestionPipeline
from app.models import IngestionJob
from app.retrieval.interfaces import RetrievalFilters
from app.retrieval.lexical import LexicalRetriever
from app.schemas.api import (
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
    caps = capabilities()
    if req.mode in {"semantic", "hybrid"} and not caps["semantic_retrieval"]:
        raise HTTPException(
            501,
            f"{req.mode} retrieval requires an embedding provider (EMBEDDING_PROVIDER is 'none'). "
            "Semantic and hybrid modes are delivered in Phase 2.",
        )
    filters = RetrievalFilters(
        product_slug=req.product,
        target_version=req.target_version,
        category=req.category,
        min_trust=req.min_trust,
        enforce_version=req.enforce_version,
    )
    retriever = LexicalRetriever(db)
    t0 = time.perf_counter()
    try:
        results = retriever.retrieve(req.query, filters, req.top_k)
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
        retrieval_latency_ms=round(latency, 2),
        notices=notices,
    )
