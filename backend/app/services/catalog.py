"""Read-side queries for products, documents, chunks and dashboard aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Document,
    DocumentChunk,
    DocumentRevision,
    EvaluationRun,
    IngestionJob,
    Product,
    ProductRelease,
    QueryLog,
)
from app.schemas.api import (
    ChunkOut,
    DocumentDetailOut,
    DocumentOut,
    IngestionJobOut,
    ProductDetailOut,
    ProductOut,
    ReleaseOut,
    RevisionSummaryOut,
)


def _product_out(db: Session, p: Product) -> ProductOut:
    return ProductOut(
        id=str(p.id),
        slug=p.slug,
        name=p.name,
        version_scheme=p.version_scheme,
        is_synthetic=p.is_synthetic,
        release_count=db.scalar(
            select(func.count())
            .select_from(ProductRelease)
            .where(ProductRelease.product_id == p.id)
        )
        or 0,
        document_count=db.scalar(
            select(func.count()).select_from(Document).where(Document.product_id == p.id)
        )
        or 0,
    )


def list_products(db: Session) -> list[ProductOut]:
    return [_product_out(db, p) for p in db.scalars(select(Product).order_by(Product.slug))]


def get_product(db: Session, slug: str) -> ProductDetailOut | None:
    p = db.scalar(select(Product).where(Product.slug == slug))
    if p is None:
        return None
    base = _product_out(db, p)
    rels = [
        ReleaseOut(
            id=str(r.id),
            label=r.label,
            sequence=r.sequence,
            release_date=r.release_date,
            release_date_provenance=r.release_date_provenance.value,
        )
        for r in db.scalars(
            select(ProductRelease)
            .where(ProductRelease.product_id == p.id)
            .order_by(ProductRelease.sequence)
        )
    ]
    return ProductDetailOut(**base.model_dump(), releases=rels)


def _rev_out(db: Session, r: DocumentRevision) -> RevisionSummaryOut:
    return RevisionSummaryOut(
        id=str(r.id),
        revision_number=r.revision_number,
        checksum=r.checksum,
        published_at=r.published_at,
        last_updated_at=r.last_updated_at,
        effective_from=r.effective_from_release.label if r.effective_from_release else None,
        effective_to=r.effective_to_release.label if r.effective_to_release else None,
        applicability_provenance=r.applicability_provenance.value,
        metadata_provenance=r.metadata_provenance or {},
        technical_tokens=r.technical_tokens or [],
        chunk_count=db.scalar(
            select(func.count()).select_from(DocumentChunk).where(DocumentChunk.revision_id == r.id)
        )
        or 0,
        ingested_at=r.ingested_at,
    )


def _doc_out(db: Session, d: Document) -> DocumentOut:
    return DocumentOut(
        id=str(d.id),
        product_slug=d.product.slug,
        source_name=d.source.name,
        trust_level=d.source.trust_level.value,
        external_id=d.external_id,
        title=d.title,
        source_url=d.source_url,
        category=d.category,
        current_revision=_rev_out(db, d.current_revision) if d.current_revision else None,
    )


def list_documents(
    db: Session, product_slug: str | None, limit: int, offset: int
) -> list[DocumentOut]:
    stmt = select(Document).join(Product).order_by(Document.title).limit(limit).offset(offset)
    if product_slug:
        stmt = stmt.where(Product.slug == product_slug)
    return [_doc_out(db, d) for d in db.scalars(stmt)]


def get_document(db: Session, doc_id: uuid.UUID) -> DocumentDetailOut | None:
    d = db.get(Document, doc_id)
    if d is None:
        return None
    return DocumentDetailOut(
        **_doc_out(db, d).model_dump(), revisions=[_rev_out(db, r) for r in d.revisions]
    )


def list_chunks(db: Session, revision_id: uuid.UUID) -> list[ChunkOut]:
    rows = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.revision_id == revision_id)
        .order_by(DocumentChunk.ordinal)
    )
    return [
        ChunkOut(
            id=str(c.id),
            ordinal=c.ordinal,
            heading=c.heading,
            content=c.content,
            char_count=c.char_count,
            technical_tokens=c.technical_tokens or [],
            has_embedding=c.embedding is not None,
        )
        for c in rows
    ]


def job_out(j: IngestionJob) -> IngestionJobOut:
    return IngestionJobOut(
        id=str(j.id),
        source_path=j.source_path,
        status=j.status.value,
        started_at=j.started_at,
        finished_at=j.finished_at,
        stats=j.stats or {},
        error=j.error,
    )


def list_jobs(db: Session, limit: int = 20) -> list[IngestionJobOut]:
    return [
        job_out(j)
        for j in db.scalars(
            select(IngestionJob).order_by(IngestionJob.started_at.desc()).limit(limit)
        )
    ]


def dashboard(db: Session, capabilities: dict) -> dict:
    return {
        "products": list_products(db),
        "document_count": db.scalar(select(func.count()).select_from(Document)) or 0,
        "revision_count": db.scalar(select(func.count()).select_from(DocumentRevision)) or 0,
        "chunk_count": db.scalar(select(func.count()).select_from(DocumentChunk)) or 0,
        "embedded_chunk_count": db.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.embedding.is_not(None))
        )
        or 0,
        "recent_jobs": list_jobs(db, 10),
        "recent_queries": [
            {
                "id": str(q.id),
                "created_at": q.created_at.isoformat(),
                "question": q.question,
                "product": q.product_slug,
                "target_version": q.target_version,
                "mode": q.mode,
                "applicability_status": q.applicability_status,
                "abstained": q.abstained,
                "generation_mode": q.generation_mode,
                "latency_ms": q.latency_ms,
            }
            for q in db.scalars(select(QueryLog).order_by(QueryLog.created_at.desc()).limit(10))
        ],
        "evaluation_runs": [
            {
                "id": str(r.id),
                "strategy": r.strategy,
                "model_identifier": r.model_identifier,
                "started_at": r.started_at.isoformat(),
                "metrics": r.metrics,
            }
            for r in db.scalars(
                select(EvaluationRun).order_by(EvaluationRun.started_at.desc()).limit(10)
            )
        ],
        "capabilities": capabilities,
    }
