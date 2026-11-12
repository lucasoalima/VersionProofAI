import pytest

from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.interfaces import RetrievalFilters
from app.retrieval.lexical import LexicalRetriever
from app.retrieval.service import retrieve_with_exclusions
from tests.conftest import DATA_DIR

pytestmark = pytest.mark.integration


def test_excluded_list_explains_feature_introduced_later(db):
    IngestionPipeline(db).ingest_path(DATA_DIR / "synthetic")
    out = retrieve_with_exclusions(
        LexicalRetriever(db), "Can I use @AsyncTrigger on this release?", RetrievalFilters("nimbus-crm", target_version="Winter '25"), 5
    )
    assert not any(r.title == "Async Trigger Framework" for r in out.results)
    assert out.excluded and out.excluded[0].title == "Async Trigger Framework"
    assert out.excluded[0].applicability_status.value == "not_applicable"
    assert out.excluded[0].effective_from == "Spring '25"
    assert {e.chunk_id for e in out.results}.isdisjoint({e.chunk_id for e in out.excluded})


def test_no_exclusions_when_version_not_enforced(db):
    IngestionPipeline(db).ingest_path(DATA_DIR / "synthetic")
    out = retrieve_with_exclusions(LexicalRetriever(db), "@AsyncTrigger", RetrievalFilters("nimbus-crm", target_version="Winter '25", enforce_version=False), 5)
    assert out.excluded == [] and any(r.applicability_status.value == "not_applicable" for r in out.results)
