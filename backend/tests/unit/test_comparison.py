from app.comparison.engine import classify_range, extract_statements

RELS = ["Winter '24", "Spring '24", "Summer '24", "Winter '25", "Spring '25"]


def test_extracts_explicit_statements_with_registered_releases_only():
    text = (
        "Introduced in Spring '25. The framework is new.\n"
        "As of Summer '24, the `LegacySyncCallout.send()` API is deprecated. It was removed in Autumn '30."
    )
    got = {(s.change_type, s.release_label) for s in extract_statements(text, RELS)}
    assert got == {
        ("introduced", "Spring '25"),
        ("deprecated", "Summer '24"),
    }  # unregistered release ignored


def test_no_statement_without_a_release_or_change_verb():
    assert (
        extract_statements(
            "The 2,000-record ceiling is removed. No removal date has been announced.", RELS
        )
        == []
    )
    assert extract_statements("Applies to Winter '24 and Spring '24.", RELS) == []
    assert extract_statements("Introduced in Spring '25.", []) == []


def test_label_variants_and_sentence_capture():
    (s,) = extract_statements(
        "Starting with winter 25, export uses the v2 engine. Other text.", RELS
    )
    assert s.release_label == "Winter '25" and s.sentence.startswith("Starting with winter 25")


def test_classify_range():
    assert classify_range(10, None, "verified", 5, 10) == "introduced"
    assert classify_range(1, 20, "verified", 5, 10) == "unchanged"
    assert classify_range(1, 7, "verified", 5, 10) == "ended"
    assert classify_range(20, None, "verified", 5, 10) is None  # outside the window entirely
    assert classify_range(1, 7, "unknown", 5, 10) == "unknown"
    assert classify_range(None, None, "verified", 5, 10) == "unknown"
