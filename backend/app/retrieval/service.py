"""Retrieval with an explicit exclusion list.

Excluding verified-not-applicable revisions is correct for *recommendations*, but it removes the
evidence needed to explain *why* something does not apply ("introduced in Spring '25"). So the
service returns two labelled lists: `results` (constraint applied) and `excluded` (relevant hits
that are verified NOT applicable to the target version). Excluded items are never merged into
results; downstream components must treat them as "exists in another version" evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.retrieval.interfaces import Evidence, RetrievalFilters, Retriever
from app.versioning.applicability import ApplicabilityStatus


@dataclass
class RetrievalOutcome:
    results: list[Evidence]
    excluded: list[Evidence] = field(default_factory=list)


def retrieve_with_exclusions(
    retriever: Retriever, query: str, filters: RetrievalFilters, top_k: int, excluded_k: int = 3
) -> RetrievalOutcome:
    results = retriever.retrieve(query, filters, top_k)
    if not (filters.enforce_version and filters.target_version):
        return RetrievalOutcome(results=results)
    relaxed = retriever.retrieve(query, replace(filters, enforce_version=False), top_k + excluded_k)
    seen = {e.chunk_id for e in results}
    excluded = [
        e
        for e in relaxed
        if e.chunk_id not in seen and e.applicability_status is ApplicabilityStatus.not_applicable
    ][:excluded_k]
    for i, e in enumerate(excluded, 1):
        e.rank = i
        e.diagnostics = {
            **e.diagnostics,
            "excluded_reason": "verified not applicable to target version",
        }
    return RetrievalOutcome(results=results, excluded=excluded)
