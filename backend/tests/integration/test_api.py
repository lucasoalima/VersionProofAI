import pytest

pytestmark = pytest.mark.integration


def test_health_reports_db_and_capabilities(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] == "ok" and body["pgvector"]
    assert body["capabilities"]["lexical_retrieval"] is True
    assert body["capabilities"]["answer_generation"] is False


def test_ingest_dashboard_documents_search_flow(client):
    r = client.post("/api/ingestion/local", json={"path": "synthetic"})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "completed" and job["stats"]["revisions_created"] == 12

    dash = client.get("/api/dashboard").json()
    assert dash["document_count"] == 12 and dash["chunk_count"] > 12
    assert dash["products"][0]["slug"] == "nimbus-crm" and dash["products"][0]["is_synthetic"]
    assert dash["recent_jobs"][0]["id"] == job["id"]

    prod = client.get("/api/products/nimbus-crm").json()
    assert prod["releases"][0]["label"] == "Winter '24"

    docs = client.get("/api/documents", params={"product": "nimbus-crm"}).json()
    doc = next(d for d in docs if d["external_id"] == "bulk-export-batch-workaround")
    detail = client.get(f"/api/documents/{doc['id']}").json()
    assert detail["current_revision"]["effective_to"] == "Summer '24"
    chunks = client.get(f"/api/revisions/{detail['current_revision']['id']}/chunks").json()
    assert chunks and chunks[0]["has_embedding"] is False

    s = client.post(
        "/api/search",
        json={
            "query": "NIMBUS_LIMIT_EXCEEDED_0427",
            "product": "nimbus-crm",
            "target_version": "Winter '25",
        },
    )
    assert s.status_code == 200
    body = s.json()
    assert body["results"][0]["applicability_status"] == "applies"
    assert body["retrieval_latency_ms"] > 0


def test_ingestion_path_traversal_rejected(client):
    assert client.post("/api/ingestion/local", json={"path": "../backend/app"}).status_code == 403
    assert client.post("/api/ingestion/local", json={"path": "/etc/passwd"}).status_code == 403
    assert client.post("/api/ingestion/local", json={"path": "nope"}).status_code == 404


def test_semantic_mode_fails_clearly_without_provider(client):
    r = client.post(
        "/api/search", json={"query": "x y", "product": "nimbus-crm", "mode": "semantic"}
    )
    assert r.status_code == 501


def test_search_unknown_product_and_version(client):
    client.post("/api/ingestion/local", json={"path": "synthetic"})
    assert client.post("/api/search", json={"query": "jobs", "product": "ghost"}).status_code == 404
    assert (
        client.post(
            "/api/search",
            json={"query": "jobs", "product": "nimbus-crm", "target_version": "Summer '99"},
        ).status_code
        == 422
    )
