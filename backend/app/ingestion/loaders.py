from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from app.ingestion.interfaces import RawDocument, RawRelease

VALID_PROVENANCE = {"verified", "inferred", "unknown"}


class IngestionFormatError(ValueError):
    pass


def _date(v) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def _prov(v, field: str) -> str:
    v = (v or "unknown").lower()
    if v not in VALID_PROVENANCE:
        raise IngestionFormatError(f"Invalid provenance {v!r} for {field}")
    return v


def _build(meta: dict, content: str, defaults: dict, content_format: str) -> RawDocument:
    m = {**defaults, **meta}
    required = ["product", "external_id", "title"]
    missing = [k for k in required if not m.get(k)]
    if missing:
        raise IngestionFormatError(f"Missing required fields {missing} in {m.get('external_id')!r}")
    mp = {k: _prov(v, k) for k, v in (m.get("metadata_provenance") or {}).items()}
    releases = [
        RawRelease(
            label=r["label"],
            sequence=r.get("sequence"),
            release_date=_date(r.get("release_date")),
            release_date_provenance=_prov(r.get("release_date_provenance"), "release_date"),
            notes=r.get("notes"),
        )
        for r in (m.get("releases") or [])
    ]
    return RawDocument(
        product_slug=m["product"],
        product_name=m.get("product_name") or m["product"],
        version_scheme=m.get("version_scheme", "explicit"),
        source_name=m.get("source_name", "local"),
        source_type=m.get("source_type", content_format),
        trust_level=m.get("trust_level", "untrusted"),
        external_id=m["external_id"],
        title=m["title"],
        content=content,
        content_format=content_format,
        source_url=m.get("source_url"),
        category=m.get("category"),
        published_at=_date(m.get("published_at")),
        last_updated_at=_date(m.get("last_updated_at")),
        effective_from=m.get("effective_from"),
        effective_to=m.get("effective_to"),
        applicability_provenance=_prov(m.get("applicability_provenance"), "applicability"),
        metadata_provenance=mp,
        releases=releases,
        product_is_synthetic=bool(m.get("product_is_synthetic", False)),
        license_note=m.get("license_note"),
    )


class JsonFixtureLoader:
    """{"defaults": {...}, "releases": [...], "documents": [{...,"content": "..."}]}"""

    name = "json_fixture"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".json"

    def load(self, path: Path) -> list[RawDocument]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "documents" not in data:
            raise IngestionFormatError(f"{path.name}: expected an object with a 'documents' list")
        defaults = dict(data.get("defaults") or {})
        defaults["releases"] = data.get("releases") or []
        defaults.setdefault("source_type", "json_fixture")
        docs = []
        for d in data["documents"]:
            content = d.pop("content", "")
            docs.append(_build(d, content, defaults, d.get("content_format", "markdown")))
        return docs


class MarkdownLoader:
    """Markdown with a YAML front-matter block."""

    name = "markdown"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in {".md", ".markdown"}

    def load(self, path: Path) -> list[RawDocument]:
        text = path.read_text(encoding="utf-8")
        meta: dict = {}
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) < 3:
                raise IngestionFormatError(f"{path.name}: unterminated front matter")
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2].lstrip("\n")
        meta.setdefault("external_id", path.stem)
        meta.setdefault("title", path.stem)
        return [_build(meta, body, {"source_type": "markdown"}, "markdown")]


class PlainTextLoader:
    """Plain text; metadata must be supplied in a sidecar `<name>.meta.yaml`."""

    name = "text"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".txt"

    def load(self, path: Path) -> list[RawDocument]:
        sidecar = path.with_suffix(".meta.yaml")
        meta = yaml.safe_load(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
        meta = meta or {}
        meta.setdefault("external_id", path.stem)
        meta.setdefault("title", path.stem)
        return [_build(meta, path.read_text(encoding="utf-8"), {"source_type": "text"}, "text")]


def default_loaders() -> list:
    from app.ingestion.cli_release_notes import SalesforceCliReleaseNotesLoader

    # Source-specific loaders come first: the first loader that supports a path wins.
    return [
        SalesforceCliReleaseNotesLoader(),
        JsonFixtureLoader(),
        MarkdownLoader(),
        PlainTextLoader(),
    ]


DEFAULT_LOADERS = default_loaders()
