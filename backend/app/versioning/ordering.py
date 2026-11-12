"""Per-product version ordering strategies.

The schema never assumes semantic versioning. Each product names a strategy; the strategy
turns a release label into an integer `sequence` used for all applicability comparisons.
"""

from __future__ import annotations

import re
from typing import ClassVar, Protocol


class VersionOrderingError(ValueError):
    pass


class VersionOrdering(Protocol):
    name: str

    def sequence(self, label: str) -> int: ...
    def normalize(self, label: str) -> str: ...


class SemverOrdering:
    """MAJOR.MINOR.PATCH (missing parts default to 0; pre-release suffixes ignored)."""

    name = "semver"
    _re = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")

    def normalize(self, label: str) -> str:
        m = self._re.match(label.strip())
        if not m:
            raise VersionOrderingError(f"Not a semver-like label: {label!r}")
        major, minor, patch = (int(g or 0) for g in m.groups())
        return f"{major}.{minor}.{patch}"

    def sequence(self, label: str) -> int:
        major, minor, patch = (int(p) for p in self.normalize(label).split("."))
        return major * 1_000_000 + minor * 1_000 + patch


class SalesforceSeasonalOrdering:
    """Seasonal release names such as "Winter '26", "Spring 26", "summer'25".

    Within a release year, the order is Winter < Spring < Summer. Note that a Salesforce
    "Winter 'YY" release actually ships in the preceding calendar year; we order by the
    *release-year label*, which is the convention the platform itself uses.
    """

    name = "salesforce_seasonal"
    _seasons: ClassVar[dict[str, int]] = {"winter": 0, "spring": 1, "summer": 2}
    _re = re.compile(r"^(winter|spring|summer)\s*'?\s*(\d{2}|\d{4})$", re.IGNORECASE)

    def normalize(self, label: str) -> str:
        m = self._re.match(label.strip())
        if not m:
            raise VersionOrderingError(f"Not a seasonal release label: {label!r}")
        season = m.group(1).capitalize()
        year = int(m.group(2))
        if year < 100:
            year += 2000
        return f"{season} '{year % 100:02d}"

    def sequence(self, label: str) -> int:
        norm = self.normalize(label)
        season, yy = norm.split(" '")
        return (2000 + int(yy)) * 10 + self._seasons[season.lower()]


class ExplicitOrdering:
    """Order supplied by the caller (e.g. from a fixture's `sequence` field).

    Used for products whose labels carry no parseable order (named releases, dates).
    """

    name = "explicit"

    def __init__(self, order: dict[str, int] | None = None):
        self._order = dict(order or {})

    def register(self, label: str, sequence: int) -> None:
        self._order[label] = sequence

    def normalize(self, label: str) -> str:
        return label.strip()

    def sequence(self, label: str) -> int:
        key = self.normalize(label)
        if key not in self._order:
            raise VersionOrderingError(f"No explicit sequence registered for {key!r}")
        return self._order[key]


_REGISTRY: dict[str, type] = {
    SemverOrdering.name: SemverOrdering,
    SalesforceSeasonalOrdering.name: SalesforceSeasonalOrdering,
    ExplicitOrdering.name: ExplicitOrdering,
}


def get_ordering(scheme: str, **kwargs) -> VersionOrdering:
    try:
        return _REGISTRY[scheme](**kwargs)
    except KeyError as exc:
        raise VersionOrderingError(f"Unknown version scheme {scheme!r}") from exc
