from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ReleaseOut(BaseModel):
    id: str
    label: str
    sequence: int
    release_date: date | None
    release_date_provenance: str


class ProductOut(BaseModel):
    id: str
    slug: str
    name: str
    version_scheme: str
    is_synthetic: bool
    release_count: int
    document_count: int


class ProductDetailOut(ProductOut):
    releases: list[ReleaseOut]


class RevisionSummaryOut(BaseModel):
    id: str
    revision_number: int
    checksum: str
    published_at: date | None
    last_updated_at: date | None
    effective_from: str | None
    effective_to: str | None
    applicability_provenance: str
    metadata_provenance: dict[str, str]
    technical_tokens: list[str]
    chunk_count: int
    ingested_at: datetime


class DocumentOut(BaseModel):
    id: str
    product_slug: str
    source_name: str
    trust_level: str
    external_id: str
    title: str
    source_url: str | None
    category: str | None
    current_revision: RevisionSummaryOut | None


class DocumentDetailOut(DocumentOut):
    revisions: list[RevisionSummaryOut]


class ChunkOut(BaseModel):
    id: str
    ordinal: int
    heading: str | None
    content: str
    char_count: int
    technical_tokens: list[str]
    has_embedding: bool


class IngestionRequest(BaseModel):
    # Relative to INGESTION_ROOT. Absolute paths and traversal are rejected.
    path: str = Field(min_length=1, max_length=500)


class IngestionJobOut(BaseModel):
    id: str
    source_path: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    stats: dict[str, Any]
    error: str | None


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    product: str
    target_version: str | None = None
    mode: str = Field(default="lexical", pattern="^(lexical|semantic|hybrid)$")
    top_k: int = Field(default=10, ge=1, le=50)
    category: str | None = None
    min_trust: str | None = None
    enforce_version: bool = True


class EvidenceOut(BaseModel):
    chunk_id: str
    document_id: str
    revision_id: str
    title: str
    source_url: str | None
    heading: str | None
    excerpt: str
    score: float
    rank: int
    effective_from: str | None
    effective_to: str | None
    applicability_status: str
    applicability_provenance: str
    published_at: str | None
    trust_level: str
    strategy: str
    diagnostics: dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    product: str
    target_version: str | None
    mode: str
    enforce_version: bool
    results: list[EvidenceOut]
    # Relevant but verified-not-applicable hits, kept separate so they can explain, never recommend.
    excluded: list[EvidenceOut]
    retrieval_latency_ms: float
    notices: list[str]


class DashboardOut(BaseModel):
    products: list[ProductOut]
    document_count: int
    revision_count: int
    chunk_count: int
    embedded_chunk_count: int
    recent_jobs: list[IngestionJobOut]
    evaluation_runs: list[dict[str, Any]]
    capabilities: dict[str, Any]
