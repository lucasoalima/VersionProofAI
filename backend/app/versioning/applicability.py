"""Applicability resolution: does a document revision apply to a target release?

A release range is [effective_from, effective_to] inclusive, expressed as sequences.
`None` bounds are open. Provenance `unknown` means we cannot state applicability at all.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class ApplicabilityStatus(enum.StrEnum):
    applies = "applies"
    not_applicable = "not_applicable"
    unknown = "unknown"
    inferred_applies = "inferred_applies"
    inferred_not_applicable = "inferred_not_applicable"


@dataclass(frozen=True)
class ApplicabilityRange:
    from_sequence: int | None
    to_sequence: int | None
    provenance: str  # verified | inferred | unknown


def resolve(target_sequence: int | None, rng: ApplicabilityRange) -> ApplicabilityStatus:
    if target_sequence is None:
        return ApplicabilityStatus.unknown
    if rng.provenance == "unknown" or (rng.from_sequence is None and rng.to_sequence is None):
        return ApplicabilityStatus.unknown
    inside = (rng.from_sequence is None or target_sequence >= rng.from_sequence) and (
        rng.to_sequence is None or target_sequence <= rng.to_sequence
    )
    if rng.provenance == "verified":
        return ApplicabilityStatus.applies if inside else ApplicabilityStatus.not_applicable
    return (
        ApplicabilityStatus.inferred_applies
        if inside
        else ApplicabilityStatus.inferred_not_applicable
    )
