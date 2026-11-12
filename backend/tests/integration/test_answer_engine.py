import json

import pytest

from app.generation.engine import AnswerEngine
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.interfaces import RetrievalFilters
from app.retrieval.lexical import LexicalRetriever
from tests.conftest import DATA_DIR

pytestmark = pytest.mark.integration


class FakeLLM:
    name, model_id = "fake", "fake-llm"

    def __init__(self, respond):
        self.respond, self.calls = respond, []

    def complete(self, system, user, max_tokens=800):
        self.calls.append((system, user))
        return self.respond(user)


@pytest.fixture()
def engine(db):
    IngestionPipeline(db).ingest_path(DATA_DIR / "synthetic")
    return lambda llm=None: AnswerEngine(db, LexicalRetriever(db), llm)


def F(v):
    return RetrievalFilters("nimbus-crm", target_version=v)


def test_workaround_no_longer_required_extractive(engine):
    a = engine().answer(
        "Is manual cursor pagination still required for BulkExportService.export()?",
        F("Winter '25"),
    )
    assert (
        not a.abstained
        and a.applicability_status == "applies"
        and a.generation_mode == "extractive"
    )
    cited_titles = {e.title for e in a.evidence if e.chunk_id in a.citations}
    assert cited_titles and not any("2,000-record" in t for t in cited_titles)
    assert any(
        "2,000-record" in e.title for e in a.excluded
    )  # the outdated workaround is shown as excluded
    assert a.diagnostics["coverage_results"] >= 0.5


def test_abstains_when_not_in_knowledge_base(engine):
    a = engine().answer(
        "What is the maximum size of a Flow interview in Nimbus CRM?", F("Spring '25")
    )
    assert a.abstained and a.applicability_status == "unknown" and a.citations == []
    assert any("Insufficient evidence" in w for w in a.warnings)


def test_feature_from_later_release_is_not_applicable_not_abstained(engine):
    a = engine().answer("Can I use @AsyncTrigger on this release?", F("Winter '25"))
    assert a.applicability_status == "not_applicable" and not a.abstained
    assert "Spring '25" in a.answer and a.citations == []


def test_conflicting_sources_are_surfaced_not_resolved(engine):
    a = engine().answer("How long are Field History entries retained?", F("Spring '25"))
    assert a.conflicts and a.abstained and a.applicability_status == "unknown"
    assert len(a.citations) == 2 and any("conflict" in w.lower() for w in a.warnings)


def test_missing_version_is_flagged(engine):
    a = engine().answer(
        "How many scheduled jobs can run concurrently?", RetrievalFilters("nimbus-crm")
    )
    assert (
        a.applicability_status == "unknown"
        and "Which release are you running?" in a.unresolved_questions
    )


def test_llm_fabricated_citation_is_rejected(engine):
    llm = FakeLLM(
        lambda u: json.dumps(
            {
                "answer": "Use the workaround.",
                "citations": ["00000000-0000-0000-0000-000000000000"],
                "abstain": False,
            }
        )
    )
    a = engine(llm).answer("How many scheduled jobs can run concurrently?", F("Spring '25"))
    assert a.abstained and a.citations == [] and a.generation_mode == "llm"
    assert a.diagnostics["invalid_citations"] == ["00000000-0000-0000-0000-000000000000"]


def test_llm_valid_citation_accepted_and_excluded_chunk_not_citable(engine):
    def respond(user):
        import re

        ev = re.findall(r'<evidence chunk_id="([^"]+)"', user)
        ex = re.findall(r'<excluded chunk_id="([^"]+)"', user)
        return json.dumps(
            {"answer": "10 concurrent jobs.", "citations": [ev[0], *ex], "abstain": False}
        )

    llm = FakeLLM(respond)
    a = engine(llm).answer("How many scheduled jobs can run concurrently?", F("Spring '25"))
    assert not a.abstained and a.applicability_status == "applies" and len(a.citations) == 1
    assert a.citations[0] in {e.chunk_id for e in a.evidence}
    system, user = llm.calls[0]
    assert "at most 10" in user and "at most 10" not in system


def test_llm_invalid_json_falls_back_to_extractive(engine):
    a = engine(FakeLLM(lambda u: "Sure! Here is my answer")).answer(
        "How many scheduled jobs can run concurrently?", F("Spring '25")
    )
    assert a.generation_mode == "extractive" and not a.abstained
    assert any("not valid JSON" in w for w in a.warnings)


def test_ask_endpoint_logs_query_and_dashboard_shows_it(client):
    client.post("/api/ingestion/local", json={"path": "synthetic"})
    r = client.post(
        "/api/ask",
        json={
            "question": "What causes NIMBUS_LIMIT_EXCEEDED_0427?",
            "product": "nimbus-crm",
            "target_version": "Summer '24",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (
        body["applicability_status"] == "applies"
        and body["citations"]
        and body["model_identifier"] is None
    )
    dash = client.get("/api/dashboard").json()
    assert (
        dash["recent_queries"][0]["question"].startswith("What causes")
        and dash["recent_queries"][0]["abstained"] is False
    )


def test_version_label_in_question_is_not_topical_evidence(engine):
    a = engine().answer("Can I use @AsyncTrigger on Winter '25?", F("Winter '25"))
    assert a.applicability_status == "not_applicable" and a.citations == []


def test_applicable_evidence_wins_over_better_matching_excluded(engine):
    a = engine().answer(
        "Is manual cursor pagination still required for BulkExportService.export()?",
        F("Spring '24"),
    )
    assert a.applicability_status == "applies" and not a.abstained
    assert any("2,000-record" in e.title for e in a.evidence if e.chunk_id in a.citations)
