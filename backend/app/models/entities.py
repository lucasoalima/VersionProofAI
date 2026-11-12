"""Version-aware knowledge base data model.

Key design rules (see docs/data-model.md):
* A Document is a stable identity; its content lives in immutable DocumentRevisions.
* Every version-related fact carries a MetadataProvenance (verified / inferred / unknown).
  We never store an inferred value in a column that readers would treat as fact.
* Release ordering is stored as an integer `sequence` computed by a per-product
  VersionOrdering strategy, so nothing in the schema assumes semantic versioning.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

EMBEDDING_DIM = 384


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class MetadataProvenance(enum.StrEnum):
    verified = "verified"
    inferred = "inferred"
    unknown = "unknown"


class TrustLevel(enum.StrEnum):
    official = "official"
    community = "community"
    synthetic = "synthetic"
    untrusted = "untrusted"


class IngestionStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ChangeType(enum.StrEnum):
    introduced = "introduced"
    modified = "modified"
    deprecated = "deprecated"
    removed = "removed"
    unchanged = "unchanged"
    unknown = "unknown"


PROVENANCE_ENUM = Enum(MetadataProvenance, name="metadata_provenance")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    # Name of the VersionOrdering strategy: "semver", "salesforce_seasonal", "explicit"
    version_scheme: Mapped[str] = mapped_column(String(50), default="explicit")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    releases: Mapped[list[ProductRelease]] = relationship(
        back_populates="product", order_by="ProductRelease.sequence"
    )
    documents: Mapped[list[Document]] = relationship(back_populates="product")


class ProductRelease(Base):
    __tablename__ = "product_releases"
    __table_args__ = (UniqueConstraint("product_id", "label"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(100))
    # Canonical total order within a product. Computed by the product's VersionOrdering.
    sequence: Mapped[int] = mapped_column(Integer)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    release_date_provenance: Mapped[MetadataProvenance] = mapped_column(
        PROVENANCE_ENUM, default=MetadataProvenance.unknown
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped[Product] = relationship(back_populates="releases")


class DocumentationSource(Base):
    __tablename__ = "documentation_sources"
    __table_args__ = (UniqueConstraint("product_id", "name"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(50))  # markdown | text | json_fixture | url
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trust_level: Mapped[TrustLevel] = mapped_column(
        Enum(TrustLevel, name="trust_level"), default=TrustLevel.untrusted
    )
    license_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list[Document]] = relationship(back_populates="source")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("product_id", "external_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentation_sources.id", ondelete="CASCADE")
    )
    external_id: Mapped[str] = mapped_column(String(300))
    title: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "document_revisions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_documents_current_revision",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[Product] = relationship(back_populates="documents")
    source: Mapped[DocumentationSource] = relationship(back_populates="documents")
    revisions: Mapped[list[DocumentRevision]] = relationship(
        back_populates="document",
        foreign_keys="DocumentRevision.document_id",
        order_by="DocumentRevision.revision_number",
    )
    current_revision: Mapped[DocumentRevision | None] = relationship(
        foreign_keys=[current_revision_id], post_update=True
    )


class DocumentRevision(Base):
    """Immutable snapshot of a document's content plus its version applicability."""

    __tablename__ = "document_revisions"
    __table_args__ = (
        UniqueConstraint("document_id", "revision_number"),
        Index("ix_document_revisions_search", "search_vector", postgresql_using="gin"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    revision_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_format: Mapped[str] = mapped_column(String(30), default="markdown")
    checksum: Mapped[str] = mapped_column(String(64), index=True)

    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_updated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Applicability range expressed in releases (inclusive). NULL = open-ended / unknown.
    effective_from_release_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_releases.id", ondelete="SET NULL"), nullable=True
    )
    effective_to_release_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_releases.id", ondelete="SET NULL"), nullable=True
    )
    applicability_provenance: Mapped[MetadataProvenance] = mapped_column(
        PROVENANCE_ENUM, default=MetadataProvenance.unknown
    )
    # Per-field provenance for every metadata value: {"published_at": "verified", ...}
    metadata_provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    # Extracted technical identifiers (API names, error codes, class names, version labels).
    technical_tokens: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    search_vector = mapped_column(TSVECTOR, nullable=True)

    ingestion_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"), nullable=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped[Document] = relationship(
        back_populates="revisions", foreign_keys=[document_id]
    )
    effective_from_release: Mapped[ProductRelease | None] = relationship(
        foreign_keys=[effective_from_release_id]
    )
    effective_to_release: Mapped[ProductRelease | None] = relationship(
        foreign_keys=[effective_to_release_id]
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="revision", order_by="DocumentChunk.ordinal", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("revision_id", "ordinal"),
        Index("ix_document_chunks_search", "search_vector", postgresql_using="gin"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    char_count: Mapped[int] = mapped_column(Integer)
    technical_tokens: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    search_vector = mapped_column(TSVECTOR, nullable=True)
    # Phase 2: populated by the embedding provider. NULL until then.
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)

    revision: Mapped[DocumentRevision] = relationship(back_populates="chunks")


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("product_id", "slug"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(150))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    changes: Mapped[list[FeatureChange]] = relationship(back_populates="feature")


class FeatureChange(Base):
    __tablename__ = "feature_changes"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    feature_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"))
    release_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_releases.id", ondelete="CASCADE")
    )
    change_type: Mapped[ChangeType] = mapped_column(Enum(ChangeType, name="change_type"))
    provenance: Mapped[MetadataProvenance] = mapped_column(
        PROVENANCE_ENUM, default=MetadataProvenance.unknown
    )
    evidence_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="SET NULL"), nullable=True
    )
    replacement: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    feature: Mapped[Feature] = relationship(back_populates="changes")
    release: Mapped[ProductRelease] = relationship()


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    source_path: Mapped[str] = mapped_column(String(1000))
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, name="ingestion_status"), default=IngestionStatus.pending
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # {"documents_seen": n, "revisions_created": n, "unchanged": n, "chunks_created": n, "failures": [...]}
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvaluationDataset(Base):
    __tablename__ = "evaluation_datasets"
    __table_args__ = (UniqueConstraint("name", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    split: Mapped[str] = mapped_column(String(30), default="dev")  # dev | tuning | held_out
    records: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE")
    )
    strategy: Mapped[str] = mapped_column(
        String(50)
    )  # no_retrieval | traditional_rag | versionproof
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    model_identifier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    per_question: Mapped[list] = mapped_column(JSON, default=list)


class QueryLog(Base):
    """One row per /api/ask call. Stores the question and outcome, never retrieved content."""

    __tablename__ = "query_logs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    product_slug: Mapped[str] = mapped_column(String(100))
    target_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mode: Mapped[str] = mapped_column(String(30))
    question: Mapped[str] = mapped_column(Text)
    applicability_status: Mapped[str] = mapped_column(String(30))
    abstained: Mapped[bool] = mapped_column(Boolean, default=False)
    generation_mode: Mapped[str] = mapped_column(String(30))
    latency_ms: Mapped[int] = mapped_column(Integer)
