"""Ingestion pipeline.

Guarantees:
* Re-ingesting unchanged content creates no new revision (checksum dedup).
* Changed content creates a new DocumentRevision; previous revisions are never modified.
* Release ordering is computed by the product's VersionOrdering; inferred/unknown
  applicability is stored with its provenance, never promoted to verified.
* Every failure is recorded on the IngestionJob; nothing is reported as ingested unless it was.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Session

from app.chunking.heading_chunker import HeadingChunker
from app.chunking.interfaces import Chunker
from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.interfaces import DocumentLoader, RawDocument
from app.ingestion.loaders import DEFAULT_LOADERS
from app.models import (
    Document,
    DocumentationSource,
    DocumentChunk,
    DocumentRevision,
    IngestionJob,
    IngestionStatus,
    MetadataProvenance,
    Product,
    ProductRelease,
    TrustLevel,
)
from app.retrieval.tokens import extract_technical_tokens, technical_tsvector_literal
from app.versioning.ordering import ExplicitOrdering, VersionOrderingError, get_ordering

log = get_logger(__name__)


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class IngestionResult:
    job_id: str
    documents_seen: int = 0
    revisions_created: int = 0
    unchanged: int = 0
    chunks_created: int = 0
    failures: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "documents_seen": self.documents_seen,
            "revisions_created": self.revisions_created,
            "unchanged": self.unchanged,
            "chunks_created": self.chunks_created,
            "failures": self.failures,
        }


def _search_vector(content: str, tokens: list[str], title: str | None = None):
    """Stemmed body (weight B) + title (weight A) + positional technical identifiers (weight A)."""
    vec = func.setweight(func.to_tsvector("english", content), literal_column("'B'"))
    if title:
        vec = vec.op("||")(
            func.setweight(func.to_tsvector("english", title), literal_column("'A'"))
        )
    if tokens:
        vec = vec.op("||")(func.cast(technical_tsvector_literal(tokens), TSVECTOR))
    return vec


class IngestionPipeline:
    def __init__(
        self,
        db: Session,
        loaders: list[DocumentLoader] | None = None,
        chunker: Chunker | None = None,
    ):
        self.db = db
        self.loaders = loaders or DEFAULT_LOADERS
        self.chunker = chunker or HeadingChunker()

    # -- public ------------------------------------------------------------------

    def ingest_path(self, path: Path) -> IngestionResult:
        job = IngestionJob(source_path=str(path), status=IngestionStatus.running)
        self.db.add(job)
        self.db.flush()
        result = IngestionResult(job_id=str(job.id))
        try:
            files = sorted(p for p in (path.rglob("*") if path.is_dir() else [path]) if p.is_file())
            raw_docs: list[RawDocument] = []
            for f in files:
                loader = next((ld for ld in self.loaders if ld.supports(f)), None)
                if loader is None or f.name.lower().startswith("readme"):
                    continue
                if f.stat().st_size > settings.max_document_bytes:
                    result.failures.append({"file": str(f), "error": "exceeds max_document_bytes"})
                    continue
                try:
                    raw_docs.extend(loader.load(f))
                except Exception as exc:
                    result.failures.append(
                        {"file": str(f), "error": f"{type(exc).__name__}: {exc}"}
                    )
            if len(raw_docs) > settings.max_documents_per_job:
                raise ValueError(
                    f"{len(raw_docs)} documents exceeds max_documents_per_job={settings.max_documents_per_job}"
                )
            for raw in raw_docs:
                result.documents_seen += 1
                try:
                    with self.db.begin_nested():
                        self._ingest_document(raw, job)
                except Exception as exc:
                    log.warning("document_failed", external_id=raw.external_id, error=str(exc))
                    result.failures.append(
                        {"external_id": raw.external_id, "error": f"{type(exc).__name__}: {exc}"}
                    )
            # recompute counters from the job rows so the report reflects what was persisted
            self._finalize(job, result, IngestionStatus.completed)
        except Exception as exc:
            self.db.rollback()
            self.db.add(job)
            job.error = f"{type(exc).__name__}: {exc}"
            self._finalize(job, result, IngestionStatus.failed)
            raise
        return result

    # -- internals ---------------------------------------------------------------

    def _finalize(
        self, job: IngestionJob, result: IngestionResult, status: IngestionStatus
    ) -> None:
        revs = (
            self.db.scalar(
                select(func.count())
                .select_from(DocumentRevision)
                .where(DocumentRevision.ingestion_job_id == job.id)
            )
            or 0
        )
        chunks = (
            self.db.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .join(DocumentRevision)
                .where(DocumentRevision.ingestion_job_id == job.id)
            )
            or 0
        )
        result.revisions_created = int(revs)
        result.chunks_created = int(chunks)
        job.status = status
        job.finished_at = datetime.now(UTC)
        job.stats = result.as_dict()
        self.db.commit()

    def _get_or_create_product(self, raw: RawDocument) -> Product:
        product = self.db.scalar(select(Product).where(Product.slug == raw.product_slug))
        if product is None:
            product = Product(
                slug=raw.product_slug,
                name=raw.product_name,
                version_scheme=raw.version_scheme,
                is_synthetic=raw.product_is_synthetic,
            )
            self.db.add(product)
            self.db.flush()
        return product

    def _ensure_releases(self, product: Product, raw: RawDocument) -> dict[str, ProductRelease]:
        existing = {
            r.label: r
            for r in self.db.scalars(
                select(ProductRelease).where(ProductRelease.product_id == product.id)
            )
        }
        ordering = get_ordering(product.version_scheme)
        if isinstance(ordering, ExplicitOrdering):
            for r in existing.values():
                ordering.register(r.label, r.sequence)
            for rr in raw.releases:
                if rr.sequence is not None:
                    ordering.register(rr.label, rr.sequence)
        for rr in raw.releases:
            label = ordering.normalize(rr.label)
            if label in existing:
                continue
            rel = ProductRelease(
                product_id=product.id,
                label=label,
                sequence=ordering.sequence(rr.label),
                release_date=rr.release_date,
                release_date_provenance=MetadataProvenance(rr.release_date_provenance),
                notes=rr.notes,
            )
            self.db.add(rel)
            self.db.flush()
            existing[label] = rel
        return existing

    def _resolve_release(
        self, label: str | None, releases: dict[str, ProductRelease], product: Product
    ) -> ProductRelease | None:
        if not label:
            return None
        ordering = get_ordering(product.version_scheme)
        try:
            norm = ordering.normalize(label)
        except VersionOrderingError:
            norm = label.strip()
        if norm not in releases:
            raise VersionOrderingError(
                f"Document references release {label!r} which is not registered for product {product.slug!r}"
            )
        return releases[norm]

    def _get_or_create_source(self, product: Product, raw: RawDocument) -> DocumentationSource:
        src = self.db.scalar(
            select(DocumentationSource).where(
                DocumentationSource.product_id == product.id,
                DocumentationSource.name == raw.source_name,
            )
        )
        if src is None:
            src = DocumentationSource(
                product_id=product.id,
                name=raw.source_name,
                source_type=raw.source_type,
                trust_level=TrustLevel(raw.trust_level),
                license_note=raw.license_note,
            )
            self.db.add(src)
            self.db.flush()
        return src

    def _ingest_document(self, raw: RawDocument, job: IngestionJob) -> None:
        product = self._get_or_create_product(raw)
        releases = self._ensure_releases(product, raw)
        source = self._get_or_create_source(product, raw)
        doc = self.db.scalar(
            select(Document).where(
                Document.product_id == product.id, Document.external_id == raw.external_id
            )
        )
        if doc is None:
            doc = Document(
                product_id=product.id,
                source_id=source.id,
                external_id=raw.external_id,
                title=raw.title,
                source_url=raw.source_url,
                category=raw.category,
            )
            self.db.add(doc)
            self.db.flush()
        else:
            doc.title, doc.source_url, doc.category = raw.title, raw.source_url, raw.category

        content = raw.content.strip()
        digest = checksum(content)
        current = doc.current_revision
        if current is not None and current.checksum == digest:
            # Unchanged: dedup. We do not create a revision; the job stats record it.
            job.stats = {
                **(job.stats or {}),
                "unchanged": (job.stats or {}).get("unchanged", 0) + 1,
            }
            return

        next_number = (current.revision_number + 1) if current else 1
        tokens = extract_technical_tokens(content)
        rev = DocumentRevision(
            document_id=doc.id,
            revision_number=next_number,
            content=content,
            content_format=raw.content_format,
            checksum=digest,
            published_at=raw.published_at,
            last_updated_at=raw.last_updated_at,
            effective_from_release=self._resolve_release(raw.effective_from, releases, product),
            effective_to_release=self._resolve_release(raw.effective_to, releases, product),
            applicability_provenance=MetadataProvenance(raw.applicability_provenance),
            metadata_provenance=raw.metadata_provenance,
            technical_tokens=tokens,
            search_vector=_search_vector(content, tokens, raw.title),
            ingestion_job_id=job.id,
        )
        self.db.add(rev)
        self.db.flush()
        for ch in self.chunker.chunk(content, raw.content_format):
            ctoks = extract_technical_tokens(ch.content)
            self.db.add(
                DocumentChunk(
                    revision_id=rev.id,
                    ordinal=ch.ordinal,
                    heading=ch.heading,
                    content=ch.content,
                    checksum=checksum(ch.content),
                    char_count=len(ch.content),
                    technical_tokens=ctoks,
                    search_vector=_search_vector(ch.content, ctoks, raw.title),
                )
            )
        doc.current_revision_id = rev.id
        self.db.flush()
