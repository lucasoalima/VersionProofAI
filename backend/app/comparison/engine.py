"""Deterministic version comparison. No LLM.

Three evidence bases, in order of precedence:
1. explicit_statement  - a sentence in a source that names a registered release next to a change
   verb ("introduced in X", "deprecated as of X", "removed in X"). Verified only when the source's
   own verified effective_from equals the stated release (two independent signals agree);
   otherwise inferred.
2. paired_documents    - one document stops applying and a similarly titled one starts applying
   inside the window: classified "modified", with a diff and the differing numeric values.
3. applicability_range - the document's verified release range alone.

Rules that keep the output honest:
* A document that merely stops applying is NOT "removed": absence of documentation is not
  evidence of removal. It is reported as "unknown" with an explanatory note.
* Unknown applicability -> "unknown". Inferred metadata -> classification with verified=False.
* Release labels are taken from the product's registered releases; nothing is Salesforce-specific.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field

from sqlalchemy import Text, func, select
from sqlalchemy.orm import Session

from app.generation.engine import title_similarity
from app.models import Document, DocumentRevision, Product, ProductRelease
from app.retrieval.base import load_product, target_sequence

_NUM = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
_VERBS = {
    "introduced": r"(?:introduced in|starting with|new in|available (?:from|in|since))\s+{rel}",
    "deprecated": r"(?:deprecated\b[^\n]{{0,40}}?(?:as of|in|since)\s+{rel}|(?:as of|in|since)\s+{rel}[^\n]{{0,80}}?\bdeprecated\b)",
    "removed": r"(?:removed\b[^\n]{{0,40}}?(?:as of|in|from)\s+{rel}|(?:as of|in)\s+{rel}[^\n]{{0,80}}?\bremoved\b)",
}


@dataclass
class Statement:
    change_type: str
    release_label: str
    sentence: str


@dataclass
class Change:
    document_id: str
    external_id: str
    title: str
    source_url: str | None
    classification: str  # introduced | modified | deprecated | removed | unchanged | unknown
    verified: bool
    provenance: str
    basis: str  # explicit_statement | paired_documents | applicability_range
    release: str | None
    applies_from: str | None
    applies_to: str | None
    evidence_excerpt: str | None = None
    note: str | None = None
    paired_with: dict | None = None
    differing_values: list | None = None
    diff: list[str] = field(default_factory=list)


def extract_statements(content: str, release_labels: list[str]) -> list[Statement]:
    """Find explicit change statements that name one of the product's registered releases."""
    if not release_labels:
        return []
    variants = {}
    for label in release_labels:
        pattern = re.escape(label).replace(r"\ ", r"\s*").replace("'", "'?")
        variants[label] = pattern
    rel = "(?:" + "|".join(variants.values()) + ")"
    rel_re = re.compile(rel, re.IGNORECASE)
    out: list[Statement] = []
    for sentence in (s.strip() for s in _SENT.split(content) if s.strip()):
        for change_type, tmpl in _VERBS.items():
            m = re.search(tmpl.format(rel=rel), sentence, re.IGNORECASE)
            if not m:
                continue
            found = rel_re.search(m.group(0))
            label = next(
                (
                    lb
                    for lb, p in variants.items()
                    if found and re.fullmatch(p, found.group(0), re.IGNORECASE)
                ),
                None,
            )
            if label and not any(
                s.change_type == change_type and s.release_label == label for s in out
            ):
                out.append(Statement(change_type, label, sentence[:300]))
    return out


def classify_range(
    from_seq: int | None, to_seq: int | None, provenance: str, earlier: int, later: int
) -> str | None:
    """Range-only classification. Returns None when the document is irrelevant to the window."""
    if provenance == "unknown" or (from_seq is None and to_seq is None):
        return "unknown"

    def applies(seq: int) -> bool:
        return (from_seq is None or seq >= from_seq) and (to_seq is None or seq <= to_seq)

    e, l = applies(earlier), applies(later)  # noqa: E741
    if e and l:
        return "unchanged"
    if not e and l:
        return "introduced"
    if e and not l:
        return "ended"  # resolved by pairing, else reported as unknown
    return None


def _diff(a: str, b: str, limit: int = 40) -> list[str]:
    lines = [
        ln
        for ln in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)
        if not ln.startswith(("---", "+++", "@@"))
    ]
    return lines[:limit]


class ComparisonEngine:
    def __init__(self, db: Session):
        self.db = db

    def _rows(self, product: Product, topic: str | None):
        stmt = (
            select(Document, DocumentRevision)
            .join(DocumentRevision, Document.current_revision_id == DocumentRevision.id)
            .where(Document.product_id == product.id)
            .order_by(Document.title, Document.external_id)
        )
        if topic:
            strict = (
                self.db.scalar(select(func.cast(func.websearch_to_tsquery("english", topic), Text)))
                or ""
            )
            relaxed = strict.replace(" & ", " | ")
            if relaxed:
                stmt = stmt.where(
                    DocumentRevision.search_vector.op("@@")(func.to_tsquery("english", relaxed))
                )
        return list(self.db.execute(stmt))

    def _releases(self, product: Product) -> list[ProductRelease]:
        return list(
            self.db.scalars(
                select(ProductRelease)
                .where(ProductRelease.product_id == product.id)
                .order_by(ProductRelease.sequence)
            )
        )

    def compare(
        self, product_slug: str, earlier: str, later: str, topic: str | None = None
    ) -> dict:
        product = load_product(self.db, product_slug)
        e_seq, l_seq = (
            target_sequence(self.db, product, earlier),
            target_sequence(self.db, product, later),
        )
        if e_seq is None or l_seq is None or e_seq >= l_seq:
            raise ValueError("earlier release must precede later release")
        releases = self._releases(product)
        seq = {r.label: r.sequence for r in releases}
        labels = list(seq)
        changes: list[Change] = []
        ended: list[tuple[Document, DocumentRevision]] = []
        started: list[tuple[Document, DocumentRevision]] = []
        for doc, rev in self._rows(product, topic):
            f, t = rev.effective_from_release, rev.effective_to_release
            prov = rev.applicability_provenance.value
            base = dict(
                document_id=str(doc.id),
                external_id=doc.external_id,
                title=doc.title,
                source_url=doc.source_url,
                provenance=prov,
                applies_from=f.label if f else None,
                applies_to=t.label if t else None,
            )
            cls = classify_range(
                f.sequence if f else None, t.sequence if t else None, prov, e_seq, l_seq
            )
            in_window = [
                s
                for s in extract_statements(rev.content, labels)
                if e_seq < seq[s.release_label] <= l_seq
            ]
            if in_window and cls is not None:
                s = in_window[0]
                agrees = prov == "verified" and f is not None and f.label == s.release_label
                changes.append(
                    Change(
                        **base,
                        classification=s.change_type,
                        verified=agrees,
                        basis="explicit_statement",
                        release=s.release_label,
                        evidence_excerpt=s.sentence,
                        note=None
                        if agrees
                        else "Stated in the source text; not corroborated by verified release metadata.",
                    )
                )
                continue
            if cls is None:
                continue
            if cls == "unknown":
                changes.append(
                    Change(
                        **base,
                        classification="unknown",
                        verified=False,
                        basis="applicability_range",
                        release=None,
                        note="The source does not establish which releases it applies to.",
                    )
                )
            elif cls == "unchanged":
                changes.append(
                    Change(
                        **base,
                        classification="unchanged",
                        verified=prov == "verified",
                        basis="applicability_range",
                        release=None,
                    )
                )
            elif cls == "introduced":
                started.append((doc, rev))
                changes.append(
                    Change(
                        **base,
                        classification="introduced",
                        verified=prov == "verified",
                        basis="applicability_range",
                        release=f.label if f else None,
                        note="Documentation starts applying in this window; the source does not state an introduction explicitly.",
                    )
                )
            elif cls == "ended":
                ended.append((doc, rev))
        by_id = {c.document_id: c for c in changes}
        for doc, rev in ended:
            f, t = rev.effective_from_release, rev.effective_to_release
            prov = rev.applicability_provenance.value
            base = dict(
                document_id=str(doc.id),
                external_id=doc.external_id,
                title=doc.title,
                source_url=doc.source_url,
                provenance=prov,
                applies_from=f.label if f else None,
                applies_to=t.label if t else None,
            )
            partner = max(
                started, key=lambda p: title_similarity(doc.title, p[0].title), default=None
            )
            if partner and title_similarity(doc.title, partner[0].title) >= 0.6:
                pdoc, prev = partner
                na, nb = set(_NUM.findall(rev.content)), set(_NUM.findall(prev.content))
                both_verified = (
                    prov == "verified" and prev.applicability_provenance.value == "verified"
                )
                changes.append(
                    Change(
                        **base,
                        classification="modified",
                        verified=both_verified,
                        basis="paired_documents",
                        release=prev.effective_from_release.label
                        if prev.effective_from_release
                        else None,
                        paired_with={
                            "document_id": str(pdoc.id),
                            "external_id": pdoc.external_id,
                            "title": pdoc.title,
                        },
                        differing_values=[sorted(na - nb), sorted(nb - na)],
                        diff=_diff(rev.content, prev.content),
                        note="A similarly titled document replaces this one in the window.",
                    )
                )
                changes[:] = [c for c in changes if c is not by_id.get(str(pdoc.id))]
            else:
                changes.append(
                    Change(
                        **base,
                        classification="unknown",
                        verified=False,
                        basis="applicability_range",
                        release=None,
                        note=f"This documentation stops applying after {t.label if t else 'an earlier release'}. No source states that the feature was removed; "
                        "absence of documentation is not evidence of removal.",
                    )
                )
        order = {
            "removed": 0,
            "deprecated": 1,
            "modified": 2,
            "introduced": 3,
            "unknown": 4,
            "unchanged": 5,
        }
        changes.sort(key=lambda c: (order[c.classification], c.title))
        summary: dict[str, int] = {}
        for c in changes:
            summary[c.classification] = summary.get(c.classification, 0) + 1
        return {
            "product": product.slug,
            "earlier": earlier,
            "later": later,
            "topic": topic,
            "summary": summary,
            "verified_changes": sum(
                1
                for c in changes
                if c.verified and c.classification not in {"unchanged", "unknown"}
            ),
            "changes": [asdict(c) for c in changes],
        }

    def timeline(self, product_slug: str) -> dict:
        """Per-release events with their supporting source. Only what sources state or verified ranges show."""
        product = load_product(self.db, product_slug)
        releases = self._releases(product)
        labels = [r.label for r in releases]
        events: dict[str, list[dict]] = {lb: [] for lb in labels}
        undated: list[dict] = []
        for doc, rev in self._rows(product, None):
            prov = rev.applicability_provenance.value
            f, t = rev.effective_from_release, rev.effective_to_release
            src = {"document_id": str(doc.id), "title": doc.title, "source_url": doc.source_url}
            stmts = extract_statements(rev.content, labels)
            for s in stmts:
                agrees = prov == "verified" and f is not None and f.label == s.release_label
                events[s.release_label].append(
                    {
                        **src,
                        "event": s.change_type,
                        "verified": agrees,
                        "basis": "explicit_statement",
                        "excerpt": s.sentence,
                    }
                )
            if prov == "unknown":
                undated.append(
                    {
                        **src,
                        "event": "unknown",
                        "verified": False,
                        "basis": "applicability_range",
                        "excerpt": None,
                    }
                )
                continue
            if f and not any(s.release_label == f.label for s in stmts):
                events[f.label].append(
                    {
                        **src,
                        "event": "documented_from",
                        "verified": prov == "verified",
                        "basis": "applicability_range",
                        "excerpt": None,
                    }
                )
            if t:
                events[t.label].append(
                    {
                        **src,
                        "event": "last_documented",
                        "verified": prov == "verified",
                        "basis": "applicability_range",
                        "excerpt": None,
                    }
                )
        return {
            "product": product.slug,
            "releases": [
                {
                    "label": r.label,
                    "sequence": r.sequence,
                    "release_date": r.release_date.isoformat() if r.release_date else None,
                    "events": sorted(events[r.label], key=lambda e: (e["event"], e["title"])),
                }
                for r in releases
            ],
            "unplaced": undated,
        }
