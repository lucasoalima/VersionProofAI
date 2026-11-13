"""Shared query scaffolding so every retriever applies identical filters and version constraints."""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Document,
    DocumentationSource,
    DocumentChunk,
    DocumentRevision,
    MetadataProvenance,
    Product,
    ProductRelease,
)
from app.retrieval.interfaces import Evidence, RetrievalFilters
from app.versioning.applicability import ApplicabilityRange, resolve
from app.versioning.ordering import VersionOrderingError, get_ordering

TRUST_RANK = {"official": 3, "community": 2, "synthetic": 1, "untrusted": 0}


def load_product(db: Session, slug: str) -> Product:
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise LookupError(f"Unknown product {slug!r}")
    return product


def target_sequence(db: Session, product: Product, label: str | None) -> int | None:
    if not label:
        return None
    ordering = get_ordering(product.version_scheme)
    try:
        norm = ordering.normalize(label)
    except VersionOrderingError:
        norm = label.strip()
    rel = db.scalar(
        select(ProductRelease).where(
            ProductRelease.product_id == product.id, ProductRelease.label == norm
        )
    )
    if rel is None:
        raise VersionOrderingError(
            f"Release {label!r} is not registered for product {product.slug!r}"
        )
    return rel.sequence


def base_statement(score_expr, product: Product, filters: RetrievalFilters, target_seq: int | None):
    """Chunk ⋈ current revision ⋈ document ⋈ source ⋈ release bounds, with all filters applied.

    `score_expr` is the strategy-specific ranking expression, labelled "score"."""
    FromRel = ProductRelease.__table__.alias("from_rel")
    ToRel = ProductRelease.__table__.alias("to_rel")
    stmt = (
        select(
            DocumentChunk,
            DocumentRevision,
            Document,
            DocumentationSource.trust_level,
            FromRel.c.label.label("from_label"),
            FromRel.c.sequence.label("from_seq"),
            ToRel.c.label.label("to_label"),
            ToRel.c.sequence.label("to_seq"),
            score_expr.label("score"),
        )
        .join(DocumentRevision, DocumentChunk.revision_id == DocumentRevision.id)
        .join(Document, DocumentRevision.document_id == Document.id)
        .join(DocumentationSource, Document.source_id == DocumentationSource.id)
        .outerjoin(FromRel, DocumentRevision.effective_from_release_id == FromRel.c.id)
        .outerjoin(ToRel, DocumentRevision.effective_to_release_id == ToRel.c.id)
        .where(Document.product_id == product.id)
        .where(Document.current_revision_id == DocumentRevision.id)
    )
    if filters.category:
        stmt = stmt.where(Document.category == filters.category)
    if filters.published_after:
        stmt = stmt.where(
            DocumentRevision.published_at >= date.fromisoformat(filters.published_after)
        )
    if filters.published_before:
        stmt = stmt.where(
            DocumentRevision.published_at <= date.fromisoformat(filters.published_before)
        )
    if filters.min_trust:
        allowed = [k for k, v in TRUST_RANK.items() if v >= TRUST_RANK.get(filters.min_trust, 0)]
        stmt = stmt.where(DocumentationSource.trust_level.in_(allowed))
    if filters.enforce_version and target_seq is not None:
        # Applicability is a CONSTRAINT: verified-not-applicable revisions are dropped in SQL.
        # Unknown/inferred applicability is kept and labelled, never silently promoted.
        verified = DocumentRevision.applicability_provenance == MetadataProvenance.verified
        inside = and_(
            or_(FromRel.c.sequence.is_(None), FromRel.c.sequence <= target_seq),
            or_(ToRel.c.sequence.is_(None), ToRel.c.sequence >= target_seq),
        )
        stmt = stmt.where(or_(~verified, inside))
    return stmt


def row_to_evidence(
    row, rank: int, target_seq: int | None, strategy: str, diagnostics: dict
) -> Evidence:
    chunk, rev, doc = row.DocumentChunk, row.DocumentRevision, row.Document
    status = resolve(
        target_seq, ApplicabilityRange(row.from_seq, row.to_seq, rev.applicability_provenance.value)
    )
    return Evidence(
        chunk_id=str(chunk.id),
        document_id=str(doc.id),
        revision_id=str(rev.id),
        title=doc.title,
        source_url=doc.source_url,
        heading=chunk.heading,
        excerpt=chunk.content[:700],
        score=float(row.score),
        rank=rank,
        effective_from=row.from_label,
        effective_to=row.to_label,
        applicability_status=status,
        applicability_provenance=rev.applicability_provenance.value,
        published_at=rev.published_at.isoformat() if rev.published_at else None,
        trust_level=row.trust_level.value,
        strategy=strategy,
        diagnostics={
            **diagnostics,
            "revision_number": rev.revision_number,
            "content_format": rev.content_format,
            "effective_from_sequence": row.from_seq,
        },
    )
