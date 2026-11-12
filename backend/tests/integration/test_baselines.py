import json

import pytest

from app.evaluation.answer_runner import run_answer_benchmark
from app.generation.baselines import NoRetrievalEngine, TraditionalRagEngine
from app.generation.engine import AnswerEngine
from app.generation.interfaces import LLMUnavailable
from app.ingestion.pipeline import IngestionPipeline
from app.models import EvaluationDataset
from app.retrieval.interfaces import RetrievalFilters
from app.retrieval.lexical import LexicalRetriever
from tests.conftest import DATA_DIR

pytestmark = pytest.mark.integration


class FakeLLM:
    name, model_id = "fake", "fake-llm"

    def __init__(self, out):
        self.out = out

    def complete(self, system, user, max_tokens=800):
        return self.out


@pytest.fixture()
def ds(db):
    IngestionPipeline(db).ingest_path(DATA_DIR / "synthetic")
    spec = json.loads((DATA_DIR / "evaluation" / "synthetic_v1.json").read_text())
    d = EvaluationDataset(
        name=spec["name"], version=spec["version"], records=spec["records"], split=spec["split"]
    )
    db.add(d)
    db.flush()
    return d


def test_traditional_rag_recommends_outdated_source_that_versionproof_excludes(db, ds):
    f = RetrievalFilters("nimbus-crm", target_version="Spring '25")
    q = "How many scheduled jobs can run concurrently?"
    trad = TraditionalRagEngine(db, LexicalRetriever(db)).answer(q, f)
    assert not trad.abstained and trad.excluded == [] and trad.applicability_status == "applies"
    assert any(
        e.applicability_status.value == "not_applicable" for e in trad.evidence
    )  # outdated doc is in its context
    vp = AnswerEngine(db, LexicalRetriever(db)).answer(q, f)
    assert all(e.applicability_status.value != "not_applicable" for e in vp.evidence)


def test_benchmark_compares_baselines_with_real_numbers(db, ds):
    b = run_answer_benchmark(db, ds, TraditionalRagEngine(db, LexicalRetriever(db)))
    c = run_answer_benchmark(db, ds, AnswerEngine(db, LexicalRetriever(db)))
    assert (
        b.strategy == "answer:traditional_rag:lexical"
        and c.strategy == "answer:versionproof:lexical"
    )
    assert c.metrics["outdated_recommendation_rate"] <= b.metrics["outdated_recommendation_rate"]
    assert c.metrics["citation_validity_rate"] == 1.0
    assert c.metrics["correct_abstention_rate"] >= b.metrics["correct_abstention_rate"]
    assert all({"question", "contexts", "reference_answer"} <= set(q) for q in c.per_question)


def test_no_retrieval_baseline_requires_llm_and_has_no_citations(db, ds):
    with pytest.raises(LLMUnavailable):
        NoRetrievalEngine(None)
    run = run_answer_benchmark(
        db, ds, NoRetrievalEngine(FakeLLM('{"answer": "Probably 5.", "abstain": false}'))
    )
    assert run.strategy == "answer:no_retrieval:none" and run.model_identifier == "fake-llm"
    assert run.metrics["citation_validity_rate"] is None and all(
        q["cited_documents"] == [] for q in run.per_question
    )


def test_answer_run_api_baselines_and_ragas_export(client, db):
    client.post("/api/ingestion/local", json={"path": "synthetic"})
    spec = json.loads((DATA_DIR / "evaluation" / "synthetic_v1_heldout.json").read_text())
    d = EvaluationDataset(
        name=spec["name"], version=spec["version"], records=spec["records"], split=spec["split"]
    )
    db.add(d)
    db.commit()
    assert (
        client.post(
            "/api/evaluation/answer-runs",
            json={"dataset_id": str(d.id), "baseline": "no_retrieval"},
        ).status_code
        == 501
    )
    r = client.post(
        "/api/evaluation/answer-runs", json={"dataset_id": str(d.id), "baseline": "traditional_rag"}
    )
    assert r.status_code == 201 and r.json()["config"]["split"] == "held_out"
    rid = r.json()["id"]
    rag = client.get(f"/api/evaluation/runs/{rid}/ragas.json").json()
    assert len(rag) == 12 and {"question", "answer", "contexts", "ground_truth"} <= set(rag[0])
    assert client.get(f"/api/evaluation/runs/{rid}/export.csv").text.startswith("id,abstained,")
    resp = client.get("/api/health")
    assert resp.headers["x-request-id"] and "app;dur=" in resp.headers["server-timing"]
