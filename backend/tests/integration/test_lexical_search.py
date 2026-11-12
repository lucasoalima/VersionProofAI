import pytest

from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.interfaces import RetrievalFilters
from app.retrieval.lexical import LexicalRetriever
from app.versioning.ordering import VersionOrderingError
from tests.conftest import DATA_DIR

pytestmark = pytest.mark.integration


@pytest.fixture()
def corpus(db):
    IngestionPipeline(db).ingest_path(DATA_DIR / "synthetic")
    return LexicalRetriever(db)


def _titles(res):
    return [r.title for r in res]


def test_exact_error_code_ranks_first(corpus):
    res = corpus.retrieve("NIMBUS_LIMIT_EXCEEDED_0427", RetrievalFilters("nimbus-crm"), top_k=5)
    assert res and res[0].title.startswith("Error reference: NIMBUS_LIMIT_EXCEEDED_0427")


def test_version_constraint_excludes_verified_not_applicable(corpus):
    f = RetrievalFilters("nimbus-crm", target_version="Winter '25")
    res = corpus.retrieve("BulkExportService export cursor pagination records limit", f, top_k=10)
    titles = _titles(res)
    assert any("Bulk Export API v2" in t for t in titles)
    assert not any("2,000-record" in t for t in titles)  # workaround ends at Summer '24 → excluded
    assert all(r.applicability_status.value in {"applies", "unknown"} for r in res)


def test_same_query_earlier_version_returns_workaround(corpus):
    f = RetrievalFilters("nimbus-crm", target_version="Spring '24")
    res = corpus.retrieve("BulkExportService export cursor pagination records limit", f, top_k=10)
    titles = _titles(res)
    assert any("2,000-record" in t for t in titles)
    assert not any("Bulk Export API v2" in t for t in titles)


def test_similar_wording_different_behaviour_resolved_by_version(corpus):
    q = "how many scheduled jobs can run concurrently"
    spring = corpus.retrieve(q, RetrievalFilters("nimbus-crm", target_version="Spring '25"), 5)
    summer = corpus.retrieve(q, RetrievalFilters("nimbus-crm", target_version="Summer '24"), 5)
    assert "at most 10" in spring[0].excerpt and "at most 5" in summer[0].excerpt


def test_unknown_applicability_is_reported_not_hidden(corpus):
    res = corpus.retrieve(
        "Field History retention months",
        RetrievalFilters("nimbus-crm", target_version="Spring '25"),
        5,
    )
    assert len(res) >= 2
    assert {r.applicability_status.value for r in res} == {"unknown"}


def test_enforce_version_false_keeps_outdated_but_labels_it(corpus):
    f = RetrievalFilters("nimbus-crm", target_version="Winter '25", enforce_version=False)
    res = corpus.retrieve("2,000-record Bulk Export limit workaround cursor", f, top_k=10)
    outdated = [r for r in res if "2,000-record" in r.title]
    assert outdated and outdated[0].applicability_status.value == "not_applicable"


def test_feature_not_in_earlier_version(corpus):
    res = corpus.retrieve(
        "@AsyncTrigger async trigger framework",
        RetrievalFilters("nimbus-crm", target_version="Winter '25"),
        5,
    )
    assert not any("Async Trigger Framework" == r.title for r in res)
    res2 = corpus.retrieve(
        "@AsyncTrigger async trigger framework",
        RetrievalFilters("nimbus-crm", target_version="Spring '25"),
        5,
    )
    assert (
        res2[0].title == "Async Trigger Framework"
        and res2[0].applicability_status.value == "applies"
    )


def test_unregistered_version_is_an_error(corpus):
    with pytest.raises(VersionOrderingError):
        corpus.retrieve("anything", RetrievalFilters("nimbus-crm", target_version="Summer '30"), 5)


def test_truly_unmatched_query_returns_empty(corpus):
    assert (
        corpus.retrieve(
            "zzqx plorf wibble", RetrievalFilters("nimbus-crm", target_version="Spring '25"), 5
        )
        == []
    )


def test_weak_matches_are_flagged_as_relaxed_not_hidden(corpus):
    """Case 5 (not in KB): lexical OR-fallback may surface weak candidates. They must carry
    query_mode='relaxed' so the answer engine can abstain instead of trusting them."""
    res = corpus.retrieve(
        "flow interview maximum size",
        RetrievalFilters("nimbus-crm", target_version="Spring '25"),
        5,
    )
    assert all(r.diagnostics["query_mode"] == "relaxed" for r in res)
    strict = corpus.retrieve(
        "NIMBUS_LIMIT_EXCEEDED_0427", RetrievalFilters("nimbus-crm", target_version="Spring '25"), 5
    )
    assert strict[0].diagnostics["query_mode"] == "strict"
