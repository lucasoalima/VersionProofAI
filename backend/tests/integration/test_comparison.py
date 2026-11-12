import pytest

from app.comparison.engine import ComparisonEngine
from app.ingestion.pipeline import IngestionPipeline
from tests.conftest import DATA_DIR

pytestmark = pytest.mark.integration


@pytest.fixture()
def cmp(db):
    IngestionPipeline(db).ingest_path(DATA_DIR / "synthetic")
    return ComparisonEngine(db)


def _by(result):
    return {c["external_id"]: c for c in result["changes"]}


def test_summer24_to_spring25(cmp):
    r = cmp.compare("nimbus-crm", "Summer '24", "Spring '25")
    c = _by(r)
    assert (
        c["async-trigger-framework"]["classification"] == "introduced"
        and c["async-trigger-framework"]["verified"]
    )
    assert (
        c["async-trigger-framework"]["basis"] == "explicit_statement"
        and c["async-trigger-framework"]["release"] == "Spring '25"
    )
    assert (
        c["bulk-export-v2-release-note"]["classification"] == "introduced"
        and c["bulk-export-v2-release-note"]["release"] == "Winter '25"
    )
    m = c["scheduled-jobs-concurrency-winter24"]
    assert m["classification"] == "modified" and m["verified"] and m["basis"] == "paired_documents"
    assert (
        m["differing_values"] == [["5"], ["10"]]
        and m["paired_with"]["external_id"] == "scheduled-jobs-concurrency-spring25"
    )
    assert any(line.startswith("-") for line in m["diff"]) and any(
        line.startswith("+") for line in m["diff"]
    )
    assert "scheduled-jobs-concurrency-spring25" not in c  # folded into the pair
    # documentation that stops applying is NOT reported as removed
    w = c["bulk-export-batch-workaround"]
    assert (
        w["classification"] == "unknown"
        and not w["verified"]
        and "not evidence of removal" in w["note"]
    )
    assert "removed" not in r["summary"]
    assert c["field-history-retention-a"]["classification"] == "unknown"
    assert c["queueable-job-guide"]["classification"] == "unchanged"
    assert (
        c["legacy-sync-callouts-deprecation"]["classification"] == "unchanged"
    )  # deprecated at Summer '24 = window start


def test_deprecation_reported_inside_window(cmp):
    c = _by(cmp.compare("nimbus-crm", "Spring '24", "Winter '25"))
    d = c["legacy-sync-callouts-deprecation"]
    assert d["classification"] == "deprecated" and d["verified"] and d["release"] == "Summer '24"
    assert "deprecated" in d["evidence_excerpt"]


def test_topic_filter_and_validation(cmp):
    r = cmp.compare("nimbus-crm", "Summer '24", "Spring '25", topic="scheduled jobs concurrency")
    assert {c["classification"] for c in r["changes"]} >= {"modified"} and len(r["changes"]) < 11
    with pytest.raises(ValueError):
        cmp.compare("nimbus-crm", "Spring '25", "Summer '24")


def test_timeline_and_api(cmp, client):
    t = cmp.timeline("nimbus-crm")
    assert t["releases"][0]["label"] == "Winter '24"
    spring = next(r for r in t["releases"] if r["label"] == "Spring '25")
    assert any(
        e["event"] == "introduced" and e["title"] == "Async Trigger Framework" and e["verified"]
        for e in spring["events"]
    )
    assert len(t["unplaced"]) == 3  # two retention docs + community note: unknown applicability
    assert (
        client.get(
            "/api/compare",
            params={"product": "nimbus-crm", "earlier": "Summer '24", "later": "Spring '25"},
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/compare",
            params={"product": "nimbus-crm", "earlier": "Spring '25", "later": "Summer '24"},
        ).status_code
        == 422
    )
    assert client.get("/api/products/nimbus-crm/timeline").json()["product"] == "nimbus-crm"
