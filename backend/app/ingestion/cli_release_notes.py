"""Loader for the Salesforce CLI release-notes Markdown (forcedotcom/cli, Apache-2.0).

One document per released version. The heading `## 2.119.8 (Jan 20, 2026) [stable]` supplies
the version and its date, both stated by the source, so they are stored as verified.
Applicability is `effective_from = that version`, open-ended: a release note describes the CLI
from that version on. It does NOT know when a later note supersedes it; see docs/sources.md.
Release candidates (`[stable-rc]`, "subject to change") are skipped.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app.ingestion.interfaces import RawDocument, RawRelease

_HEADING = re.compile(r"^## (\d+\.\d+\.\d+) \(([^)]+)\)(?: \[([\w-]+)\])?\s*$", re.MULTILINE)
_DATE = re.compile(r"([A-Za-z]+)\.? (\d{1,2}), (\d{4})")
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
SOURCE_URL = "https://github.com/forcedotcom/cli/blob/main/releasenotes/README.md"


def parse_date(text: str) -> date | None:
    m = _DATE.search(text)
    if not m or m.group(1)[:3].lower() not in _MONTHS:
        return None
    try:
        return date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    except ValueError:
        return None


class SalesforceCliReleaseNotesLoader:
    name = "salesforce_cli_release_notes"

    def supports(self, path: Path) -> bool:
        return path.name.startswith("salesforce-cli-releasenotes") and path.suffix == ".md"

    def load(self, path: Path) -> list[RawDocument]:
        text = path.read_text(encoding="utf-8")
        heads = list(_HEADING.finditer(text))
        sections = []
        for i, m in enumerate(heads):
            body = text[m.end() : heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip()
            if m.group(3) == "stable-rc" or not body:
                continue
            sections.append((m.group(1), parse_date(m.group(2)), body))
        releases = [
            RawRelease(
                label=v, release_date=d, release_date_provenance="verified" if d else "unknown"
            )
            for v, d, _ in sections
        ]
        docs = []
        for version, d, body in sections:
            docs.append(
                RawDocument(
                    product_slug="salesforce-cli",
                    product_name="Salesforce CLI",
                    version_scheme="semver",
                    source_name="forcedotcom/cli release notes",
                    source_type="release_notes",
                    trust_level="official",
                    external_id=f"sf-cli-{version}",
                    title=f"Salesforce CLI {version} release notes",
                    content=f"# Salesforce CLI {version}\n\n{body}",
                    content_format="release_notes",
                    source_url=f"{SOURCE_URL}#{version.replace('.', '')}",
                    category="release-note",
                    published_at=d,
                    effective_from=version,
                    applicability_provenance="verified",
                    metadata_provenance={
                        "published_at": "verified" if d else "unknown",
                        "effective_from": "verified",
                    },
                    releases=releases,
                    product_is_synthetic=False,
                    license_note="Apache-2.0. Copyright (c) Salesforce, Inc. Source: github.com/forcedotcom/cli",
                )
            )
        return docs
