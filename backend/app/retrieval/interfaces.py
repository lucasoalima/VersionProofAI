from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.versioning.applicability import ApplicabilityStatus


@dataclass
class RetrievalFilters:
    product_slug: str
    target_version: str | None = None
    category: str | None = None
    min_trust: str | None = None  # official > community > synthetic > untrusted
    published_after: str | None = None  # ISO date
    published_before: str | None = None
    # When True, revisions whose applicability is verified-not-applicable are EXCLUDED
    # (constraint), not merely down-ranked. Unknown applicability is kept and flagged.
    enforce_version: bool = True


@dataclass
class Evidence:
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
    applicability_status: ApplicabilityStatus
    applicability_provenance: str
    published_at: str | None
    trust_level: str
    strategy: str
    diagnostics: dict = field(default_factory=dict)


class Retriever(Protocol):
    name: str

    def retrieve(self, query: str, filters: RetrievalFilters, top_k: int) -> list[Evidence]: ...
