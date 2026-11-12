"""Source-agnostic ingestion contracts.

A DocumentLoader turns a local path into RawDocuments. The pipeline never sees formats; it
only sees RawDocuments. Adding HTML/PDF/URL support means adding a loader, not touching
the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol


@dataclass
class RawRelease:
    label: str
    sequence: int | None = None  # required only for the "explicit" scheme
    release_date: date | None = None
    release_date_provenance: str = "unknown"
    notes: str | None = None


@dataclass
class RawDocument:
    product_slug: str
    product_name: str
    version_scheme: str
    source_name: str
    source_type: str
    trust_level: str
    external_id: str
    title: str
    content: str
    content_format: str = "markdown"
    source_url: str | None = None
    category: str | None = None
    published_at: date | None = None
    last_updated_at: date | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    applicability_provenance: str = "unknown"
    metadata_provenance: dict[str, str] = field(default_factory=dict)
    releases: list[RawRelease] = field(default_factory=list)
    product_is_synthetic: bool = False
    license_note: str | None = None


class DocumentLoader(Protocol):
    name: str

    def supports(self, path: Path) -> bool: ...
    def load(self, path: Path) -> list[RawDocument]: ...
