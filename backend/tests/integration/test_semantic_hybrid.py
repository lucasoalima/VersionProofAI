import pytest

from app.embeddings.indexer import build_embeddings
from app.embeddings.providers import HashedBagOfWordsProvider
from app.evaluation.retrieval_runner import run_retrieval_benchmark
from app.ingestion.pipeline import IngestionPipeline
from app.models import EvaluationDataset
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.interfaces import RetrievalFilters
from app.retrieval.lexical import LexicalRetriever
from app.retrieval.semantic import SemanticRetriever
from tests.conftest import DATA_DIR

pytestmark = pytest.mark.integration


@pytest.fixture()
def corpus(db):
    IngestionPipeline(db).ingest_path(DATA_DIR / "synthetic")
    provider = HashedBagOfWordsProvider(384)
    res = build_embeddings(db, provider)
    assert res.embedded > 0 and res.skipped == 0
    return provider


def test_embedding_build_is_idempotent(db, corpus):
    again = build_embeddings(db, corpus)
    assert again.embedded == 0 and again.skipped > 0


def test_semantic_search_applies_version_constraint(db, corpus):
    sem = SemanticRetriever(db, corpus)
    q = "how many scheduled jobs can run at the same time"
    spring = sem.retrieve(q, RetrievalFilters("nimbus-crm", target_version="Spring '25"), 3)
    summer = sem.retrieve(q, RetrievalFilters("nimbus-crm", target_version="Summer '24"), 3)
    assert (
        spring
        and "at most 10" in spring[0].excerpt
        and spring[0].applicability_status.value == "applies"
    )
    assert summer and "at most 5" in summer[0].excerpt
    assert all(r.diagnostics["embedding_model"] == "hashed-bow-v1" for r in spring)


def test_semantic_ignores_chunks_from_other_models(db, corpus):
    other = HashedBagOfWordsProvider(384)
    other.model_id = "other-model"
    assert (
        SemanticRetriever(db, other).retrieve("scheduled jobs", RetrievalFilters("nimbus-crm"), 5)
        == []
    )


def test_hybrid_fuses_and_keeps_constraint(db, corpus):
    hyb = HybridRetriever(LexicalRetriever(db), SemanticRetriever(db, corpus))
    f = RetrievalFilters("nimbus-crm", target_version="Winter '25")
    res = hyb.retrieve("Is cursor pagination still required for BulkExportService.export()?", f, 5)
    assert res and res[0].strategy == "hybrid"
    assert not any("2,000-record" in r.title for r in res)  # excluded by both components
    assert all(r.applicability_status.value in {"applies", "unknown"} for r in res)
    assert any(
        "component_ranks" in r.diagnostics and len(r.diagnostics["component_ranks"]) == 2
        for r in res
    )
    assert [r.rank for r in res] == list(range(1, len(res) + 1))


def test_retrieval_benchmark_records_real_numbers(db, corpus):
    import json

    spec = json.loads((DATA_DIR / "evaluation" / "synthetic_v1.json").read_text())
    ds = EvaluationDataset(
        name=spec["name"], version=spec["version"], records=spec["records"], is_synthetic=True
    )
    db.add(ds)
    db.flush()
    hyb = HybridRetriever(LexicalRetriever(db), SemanticRetriever(db, corpus))
    constrained = run_retrieval_benchmark(db, ds, hyb, enforce_version=True, top_k=5)
    unconstrained = run_retrieval_benchmark(db, ds, hyb, enforce_version=False, top_k=5)
    for run in (constrained, unconstrained):
        assert run.metrics["questions"] == 10 and run.metrics["errors"] == 0
        assert 0 <= run.metrics["recall_at_k"] <= 1
        assert len(run.per_question) == 10 and run.finished_at is not None
    # The version constraint must not surface MORE outdated documents than no constraint.
    assert (
        constrained.metrics["outdated_surfaced_rate"]
        <= unconstrained.metrics["outdated_surfaced_rate"]
    )
