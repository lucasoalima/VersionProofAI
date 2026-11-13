import pytest

from app.generation.engine import AnswerEngine
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.interfaces import RetrievalFilters
from app.retrieval.lexical import LexicalRetriever
from tests.unit.test_phase6 import SAMPLE

pytestmark = pytest.mark.integration


@pytest.fixture()
def engine(db, tmp_path):
    (tmp_path / "salesforce-cli-releasenotes.md").write_text(SAMPLE)
    (tmp_path / "LICENSE-x.txt").write_text("licence text")
    (tmp_path / "SOURCE.json").write_text("{}")
    res = IngestionPipeline(db).ingest_path(tmp_path)
    assert res.failures == [] and res.documents_seen == 2 and res.chunks_created == 3
    return AnswerEngine(db, LexicalRetriever(db))


def test_later_release_note_supersedes_earlier_one(engine):
    a = engine.answer(
        "Can I use the demo login legacy command?",
        RetrievalFilters("salesforce-cli", target_version="3.1.4"),
    )
    assert (
        not a.abstained
        and a.conflicts == []
        and a.diagnostics["evidence_ordering"] == "most_recent_applicable_release_first"
    )
    cited = next(e for e in a.evidence if e.chunk_id == a.citations[0])
    assert cited.effective_from == "3.1.4" and "removed" in cited.excerpt


def test_future_release_note_is_excluded_for_older_target(engine):
    a = engine.answer(
        "Can I use the demo login legacy command?",
        RetrievalFilters("salesforce-cli", target_version="3.0.0"),
    )
    cited = next(e for e in a.evidence if e.chunk_id == a.citations[0])
    assert cited.effective_from == "3.0.0" and "new" in cited.excerpt.lower()
    assert any(e.effective_from == "3.1.4" for e in a.excluded)
