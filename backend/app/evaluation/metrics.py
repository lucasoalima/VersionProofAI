"""Deterministic retrieval metrics. Each function documents exactly what it measures.

`ranked` is the ordered list of document external_ids returned by a retriever (deduplicated
at document level, first occurrence wins). `relevant` is the set of supporting document ids.
"""

from __future__ import annotations

import math


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float | None:
    """Fraction of relevant documents found in the top-k. None when nothing is relevant
    (abstention cases) — those are scored by abstention metrics, not recall."""
    if not relevant:
        return None
    return len(set(ranked[:k]) & relevant) / len(relevant)


def mrr(ranked: list[str], relevant: set[str]) -> float | None:
    """1 / rank of the first relevant document; 0 if none retrieved."""
    if not relevant:
        return None
    for i, d in enumerate(ranked, 1):
        if d in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[str], gains: dict[str, float], k: int) -> float | None:
    """Graded nDCG@k. `gains` maps document id → relevance (supporting=1, outdated=0)."""
    if not any(g > 0 for g in gains.values()):
        return None
    dcg = sum(gains.get(d, 0.0) / math.log2(i + 1) for i, d in enumerate(ranked[:k], 1))
    ideal = sorted((g for g in gains.values() if g > 0), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal, 1))
    return dcg / idcg if idcg else None


def outdated_in_top_k(ranked: list[str], outdated: set[str], k: int) -> bool:
    """True if any document the dataset marks as outdated-for-this-version is in the top-k.
    At retrieval level this is the 'outdated recommendation' precursor: if the retriever
    surfaces it, a generator can cite it."""
    return bool(set(ranked[:k]) & outdated)


def applicability_accuracy(predicted: str | None, expected: str) -> bool | None:
    """Top result's applicability status vs. the dataset's expected status.
    'applies'/'not_applicable' expected with no result at all counts as wrong; 'unknown'
    expected with no result counts as correct (nothing applicable was found)."""
    if predicted is None:
        return expected == "unknown"
    return predicted == expected


def summarize(values: list[float | bool | None]) -> float | None:
    vals = [float(v) for v in values if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None
