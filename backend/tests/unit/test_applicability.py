from app.versioning.applicability import ApplicabilityRange as R
from app.versioning.applicability import ApplicabilityStatus as S
from app.versioning.applicability import resolve


def test_verified_inside_and_outside():
    rng = R(10, 20, "verified")
    assert resolve(15, rng) == S.applies
    assert resolve(10, rng) == S.applies  # inclusive
    assert resolve(21, rng) == S.not_applicable


def test_open_ended_bounds():
    assert resolve(999, R(10, None, "verified")) == S.applies
    assert resolve(1, R(10, None, "verified")) == S.not_applicable
    assert resolve(5, R(None, 10, "verified")) == S.applies


def test_unknown_provenance_never_asserts_applicability():
    assert resolve(15, R(10, 20, "unknown")) == S.unknown
    assert resolve(15, R(None, None, "verified")) == S.unknown


def test_inferred_is_labelled_as_inferred():
    assert resolve(15, R(10, 20, "inferred")) == S.inferred_applies
    assert resolve(50, R(10, 20, "inferred")) == S.inferred_not_applicable


def test_no_target_version_is_unknown():
    assert resolve(None, R(10, 20, "verified")) == S.unknown
