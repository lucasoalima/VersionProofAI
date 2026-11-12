import pytest
from sqlalchemy import func, select

from app.ingestion.pipeline import IngestionPipeline
from app.models import (
    Document,
    DocumentChunk,
    DocumentRevision,
    IngestionJob,
    IngestionStatus,
    Product,
    ProductRelease,
)
from tests.conftest import DATA_DIR

pytestmark = pytest.mark.integration
FIXTURE = DATA_DIR / "synthetic" / "nimbus-crm" / "nimbus-docs.json"


def test_ingests_synthetic_corpus_with_release_ordering(db):
    res = IngestionPipeline(db).ingest_path(FIXTURE)
    assert res.failures == []
    assert res.documents_seen == 11 and res.revisions_created == 11 and res.chunks_created > 11
    product = db.scalar(select(Product).where(Product.slug == "nimbus-crm"))
    assert product.is_synthetic and product.version_scheme == "salesforce_seasonal"
    labels = [
        r.label
        for r in db.scalars(
            select(ProductRelease)
            .where(ProductRelease.product_id == product.id)
            .order_by(ProductRelease.sequence)
        )
    ]
    assert labels == ["Winter '24", "Spring '24", "Summer '24", "Winter '25", "Spring '25"]
    job = db.get(IngestionJob, __import__("uuid").UUID(res.job_id))
    assert job.status == IngestionStatus.completed and job.stats["revisions_created"] == 11


def test_reingest_unchanged_creates_no_revisions(db):
    IngestionPipeline(db).ingest_path(FIXTURE)
    res = IngestionPipeline(db).ingest_path(FIXTURE)
    assert res.revisions_created == 0 and res.chunks_created == 0
    assert db.scalar(select(func.count()).select_from(DocumentRevision)) == 11


def test_changed_content_creates_new_revision_and_keeps_history(db, tmp_path):
    IngestionPipeline(db).ingest_path(FIXTURE)
    import json

    data = json.loads(FIXTURE.read_text())
    target = next(d for d in data["documents"] if d["external_id"] == "async-trigger-framework")
    target["content"] += (
        "\n\n## Addendum\n\nUp to 100 async handlers per object from Spring '25 patch 2."
    )
    data["documents"] = [target]
    p = tmp_path / "update.json"
    p.write_text(json.dumps(data))
    res = IngestionPipeline(db).ingest_path(p)
    assert res.revisions_created == 1
    doc = db.scalar(select(Document).where(Document.external_id == "async-trigger-framework"))
    assert [r.revision_number for r in doc.revisions] == [1, 2]
    assert doc.current_revision.revision_number == 2
    assert "Addendum" not in doc.revisions[0].content  # history untouched
    assert doc.revisions[0].checksum != doc.revisions[1].checksum


def test_unknown_release_reference_is_a_recorded_failure_not_silent(db, tmp_path):
    import json

    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps(
            {
                "defaults": {"product": "p1", "version_scheme": "salesforce_seasonal"},
                "releases": [{"label": "Winter '24"}],
                "documents": [
                    {
                        "external_id": "d",
                        "title": "t",
                        "effective_from": "Spring '30",
                        "applicability_provenance": "verified",
                        "content": "x" * 50,
                    }
                ],
            }
        )
    )
    res = IngestionPipeline(db).ingest_path(p)
    assert res.revisions_created == 0
    assert len(res.failures) == 1 and "Spring '30" in res.failures[0]["error"]


def test_provenance_is_stored_distinctly(db):
    IngestionPipeline(db).ingest_path(FIXTURE)
    a = db.scalar(
        select(Document).where(Document.external_id == "field-history-retention-b")
    ).current_revision
    assert a.applicability_provenance.value == "unknown"
    assert a.metadata_provenance == {"published_at": "inferred", "last_updated_at": "verified"}
    assert a.effective_from_release_id is None


def test_directory_ingest_uses_multiple_loaders(db):
    res = IngestionPipeline(db).ingest_path(DATA_DIR / "synthetic")
    assert res.failures == []
    assert res.documents_seen == 12
    assert db.scalar(select(func.count()).select_from(DocumentChunk)) > 0
