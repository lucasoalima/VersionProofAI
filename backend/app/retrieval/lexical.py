"""Lexical retrieval over PostgreSQL full-text search.

Query construction mirrors indexing: `websearch_to_tsquery('english', q)` OR-ed with the
verbatim technical tokens extracted from the query. The strict (AND) form runs first; if it
yields nothing, a relaxed (OR) form runs so that paraphrased questions still surface
candidates. `diagnostics.query_mode` records which one produced the results.

Ranking: ts_rank_cd with normalisation 32 (rank/(rank+1)); title and technical identifiers are
weight A, body text weight B, so an exact identifier hit outranks a stemmed body match.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import TSQUERY
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
from app.retrieval.tokens import extract_technical_tokens, technical_tsquery_literal
from app.versioning.applicability import ApplicabilityRange, resolve
from app.versioning.ordering import VersionOrderingError, get_ordering

_TRUST_RANK = {"official": 3, "community": 2, "synthetic": 1, "untrusted": 0}


class LexicalRetriever:
    name = "lexical"

    def __init__(self, db: Session):
        self.db = db

    def _target_sequence(self, product: Product, label: str | None) -> int | None:
        if not label:
            return None
        ordering = get_ordering(product.version_scheme)
        try:
            norm = ordering.normalize(label)
        except VersionOrderingError:
            norm = label.strip()
        rel = self.db.scalar(
            select(ProductRelease).where(
                ProductRelease.product_id == product.id, ProductRelease.label == norm
            )
        )
        if rel is None:
            raise VersionOrderingError(
                f"Release {label!r} is not registered for product {product.slug!r}"
            )
        return rel.sequence

    def _tsquery_texts(self, query: str, tokens: list[str]) -> tuple[str, str]:
        """Return (strict, relaxed) tsquery source strings."""
        strict = (
            self.db.execute(
                text("SELECT websearch_to_tsquery('english', :q)::text"), {"q": query}
            ).scalar()
            or ""
        )
        relaxed = strict.replace(" & ", " | ")
        tech = technical_tsquery_literal(tokens)
        if tech:
            strict = f"({strict}) | {tech}" if strict else tech
            relaxed = f"({relaxed}) | {tech}" if relaxed else tech
        return strict, relaxed

    def retrieve(self, query: str, filters: RetrievalFilters, top_k: int) -> list[Evidence]:
        product = self.db.scalar(select(Product).where(Product.slug == filters.product_slug))
        if product is None:
            raise LookupError(f"Unknown product {filters.product_slug!r}")
        target_seq = self._target_sequence(product, filters.target_version)
        tokens = extract_technical_tokens(query)
        strict, relaxed = self._tsquery_texts(query, tokens)
        if not strict:
            return []
        rows = self._run(strict, product, filters, target_seq, top_k)
        mode = "strict"
        if not rows and relaxed != strict:
            rows = self._run(relaxed, product, filters, target_seq, top_k)
            mode = "relaxed"
        results: list[Evidence] = []
        for i, row in enumerate(rows, start=1):
            chunk, rev, doc = row.DocumentChunk, row.DocumentRevision, row.Document
            status = resolve(
                target_seq,
                ApplicabilityRange(row.from_seq, row.to_seq, rev.applicability_provenance.value),
            )
            results.append(
                Evidence(
                    chunk_id=str(chunk.id),
                    document_id=str(doc.id),
                    revision_id=str(rev.id),
                    title=doc.title,
                    source_url=doc.source_url,
                    heading=chunk.heading,
                    excerpt=chunk.content[:700],
                    score=float(row.score),
                    rank=i,
                    effective_from=row.from_label,
                    effective_to=row.to_label,
                    applicability_status=status,
                    applicability_provenance=rev.applicability_provenance.value,
                    published_at=rev.published_at.isoformat() if rev.published_at else None,
                    trust_level=row.trust_level.value,
                    strategy=self.name,
                    diagnostics={
                        "technical_tokens_in_query": tokens,
                        "query_mode": mode,
                        "revision_number": rev.revision_number,
                    },
                )
            )
        return results

    def _run(
        self,
        tsq_text: str,
        product: Product,
        filters: RetrievalFilters,
        target_seq: int | None,
        top_k: int,
    ):
        tsq = func.cast(tsq_text, TSQUERY)
        FromRel = ProductRelease.__table__.alias("from_rel")
        ToRel = ProductRelease.__table__.alias("to_rel")
        rank = func.ts_rank_cd(DocumentChunk.search_vector, tsq, 32)
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
                rank.label("score"),
            )
            .join(DocumentRevision, DocumentChunk.revision_id == DocumentRevision.id)
            .join(Document, DocumentRevision.document_id == Document.id)
            .join(DocumentationSource, Document.source_id == DocumentationSource.id)
            .outerjoin(FromRel, DocumentRevision.effective_from_release_id == FromRel.c.id)
            .outerjoin(ToRel, DocumentRevision.effective_to_release_id == ToRel.c.id)
            .where(Document.product_id == product.id)
            .where(Document.current_revision_id == DocumentRevision.id)  # current revisions only
            .where(DocumentChunk.search_vector.op("@@")(tsq))
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
            allowed = [
                k for k, v in _TRUST_RANK.items() if v >= _TRUST_RANK.get(filters.min_trust, 0)
            ]
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
        stmt = stmt.order_by(rank.desc(), Document.title, DocumentChunk.ordinal).limit(top_k)
        return list(self.db.execute(stmt))
