import pytest

from app.versioning.ordering import (
    ExplicitOrdering,
    SalesforceSeasonalOrdering,
    SemverOrdering,
    VersionOrderingError,
    get_ordering,
)


def test_semver_orders_numerically_not_lexically():
    o = SemverOrdering()
    assert o.sequence("1.10.0") > o.sequence("1.9.3")
    assert o.sequence("v2") == o.sequence("2.0.0")
    assert o.normalize("v3.1") == "3.1.0"


def test_seasonal_ordering_winter_before_spring_before_summer():
    o = SalesforceSeasonalOrdering()
    labels = ["Summer '24", "Winter '25", "Spring '24", "Winter '24", "Spring '25"]
    assert sorted(labels, key=o.sequence) == [
        "Winter '24",
        "Spring '24",
        "Summer '24",
        "Winter '25",
        "Spring '25",
    ]


@pytest.mark.parametrize(
    "raw,norm",
    [("spring 25", "Spring '25"), ("Winter'2026", "Winter '26"), ("SUMMER '24", "Summer '24")],
)
def test_seasonal_normalizes_variants(raw, norm):
    assert SalesforceSeasonalOrdering().normalize(raw) == norm


def test_seasonal_rejects_garbage():
    with pytest.raises(VersionOrderingError):
        SalesforceSeasonalOrdering().sequence("Autumn 25")


def test_explicit_requires_registration():
    o = ExplicitOrdering({"Aurora": 1, "Borealis": 2})
    assert o.sequence("Borealis") > o.sequence("Aurora")
    with pytest.raises(VersionOrderingError):
        o.sequence("Cirrus")


def test_registry():
    assert get_ordering("semver").name == "semver"
    with pytest.raises(VersionOrderingError):
        get_ordering("calver")
