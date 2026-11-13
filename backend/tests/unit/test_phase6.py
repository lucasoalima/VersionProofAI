from datetime import date

import pytest

from app.chunking.bullet_chunker import BulletChunker
from app.generation.engine import detect_conflicts
from app.ingestion.cli_release_notes import SalesforceCliReleaseNotesLoader, parse_date
from app.ingestion.remote import UrlNotAllowed, validate_url
from app.retrieval.interfaces import Evidence
from app.versioning.applicability import ApplicabilityStatus

# Invented text in the release-notes format (not copied from the real file).
SAMPLE = """# Example CLI Release Notes

## 3.2.0 (November 11, 2026) [stable-rc]

* NEW: Candidate feature, subject to change.

## 3.1.4 (Sept 3, 2026) [stable]

* CHANGE: We removed the `demo login legacy` command.

* FIX: The `demo deploy` command no longer hangs.
    More detail on a continuation line.

## 3.0.0 (Jan 20, 2026)

* NEW: Try the new `demo login legacy` command.
"""


def test_cli_loader_one_document_per_released_version(tmp_path):
    p = tmp_path / "salesforce-cli-releasenotes.md"
    p.write_text(SAMPLE)
    loader = SalesforceCliReleaseNotesLoader()
    assert loader.supports(p) and not loader.supports(tmp_path / "other.md")
    docs = loader.load(p)
    assert [d.external_id for d in docs] == [
        "sf-cli-3.1.4",
        "sf-cli-3.0.0",
    ]  # release candidate skipped
    d = docs[0]
    assert (
        d.effective_from == "3.1.4"
        and d.effective_to is None
        and d.applicability_provenance == "verified"
    )
    assert (
        d.published_at == date(2026, 9, 3)
        and d.version_scheme == "semver"
        and d.trust_level == "official"
    )
    assert (
        d.content_format == "release_notes"
        and not d.product_is_synthetic
        and "Apache-2.0" in d.license_note
    )
    assert [r.label for r in d.releases] == ["3.1.4", "3.0.0"]


def test_parse_date_variants():
    assert parse_date("Feb 4, 2026") == date(2026, 2, 4)
    assert parse_date("November 11, 2026") == date(2026, 11, 11)
    assert parse_date("Sept 24, 2025") == date(2025, 9, 24)
    assert parse_date("sometime soon") is None


def test_bullet_chunker_one_entry_per_chunk_with_heading():
    chunks = BulletChunker().chunk(
        "# Example CLI 3.1.4\n\n* CHANGE: removed X.\n\n* FIX: Y no longer hangs.\n    continuation line."
    )
    assert len(chunks) == 2 and all(c.heading == "Example CLI 3.1.4" for c in chunks)
    assert chunks[1].content.endswith("continuation line.") and chunks[0].content.startswith(
        "Example CLI 3.1.4"
    )
    assert len(BulletChunker().chunk("no bullets here")) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://raw.githubusercontent.com/forcedotcom/cli/main/releasenotes/README.md",
        "https://raw.githubusercontent.com/forcedotcom/other/main/releasenotes/README.md",
        "https://raw.githubusercontent.com.evil.example/forcedotcom/cli/main/releasenotes/README.md",
        "https://user:pw@raw.githubusercontent.com/forcedotcom/cli/main/releasenotes/README.md",
        "https://raw.githubusercontent.com:8443/forcedotcom/cli/main/releasenotes/README.md",
        "https://raw.githubusercontent.com/forcedotcom/cli/main/releasenotes/../../../x",
        "https://169.254.169.254/latest/meta-data/",
        "https://help.salesforce.com/s/articleView?id=release-notes",
        "file:///etc/passwd",
    ],
)
def test_remote_allowlist_rejects(url):
    with pytest.raises(UrlNotAllowed):
        validate_url(url)


def test_remote_allowlist_accepts_reviewed_source():
    src = validate_url(
        "https://raw.githubusercontent.com/forcedotcom/cli/main/releasenotes/README.md"
    )
    assert src.license == "Apache-2.0"


def _ev(cid, doc, fmt):
    return Evidence(
        chunk_id=cid,
        document_id=doc,
        revision_id="r",
        title=f"Example CLI {cid} release notes",
        source_url=None,
        heading=None,
        excerpt=f"limit is {cid}",
        score=1.0,
        rank=1,
        effective_from=None,
        effective_to=None,
        applicability_status=ApplicabilityStatus.applies,
        applicability_provenance="verified",
        published_at=None,
        trust_level="official",
        strategy="lexical",
        diagnostics={"content_format": fmt},
    )


def test_changelog_entries_are_not_conflicts_but_documents_are():
    assert (
        detect_conflicts([_ev("5", "d1", "release_notes"), _ev("10", "d2", "release_notes")]) == []
    )
    assert len(detect_conflicts([_ev("5", "d1", "markdown"), _ev("10", "d2", "markdown")])) == 1
