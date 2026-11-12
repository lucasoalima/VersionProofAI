from datetime import date
from pathlib import Path

import pytest

from app.ingestion.loaders import IngestionFormatError, JsonFixtureLoader, MarkdownLoader
from app.ingestion.paths import ForbiddenPathError, resolve_within_root

DATA = Path(__file__).resolve().parents[3] / "data"


def test_json_fixture_loader_reads_synthetic_corpus():
    docs = JsonFixtureLoader().load(DATA / "synthetic/nimbus-crm/nimbus-docs.json")
    assert len(docs) == 11
    d = {x.external_id: x for x in docs}["bulk-export-batch-workaround"]
    assert d.effective_from == "Winter '24" and d.effective_to == "Summer '24"
    assert d.applicability_provenance == "verified"
    assert d.published_at == date(2023, 11, 2)
    assert d.product_is_synthetic is True
    assert len(d.releases) == 5


def test_markdown_front_matter():
    (d,) = MarkdownLoader().load(DATA / "synthetic/markdown/nimbus-queueable-job.md")
    assert d.external_id == "queueable-job-guide"
    assert d.content.startswith("# QueueableJob developer guide")
    assert d.metadata_provenance == {"published_at": "verified", "last_updated_at": "verified"}


def test_invalid_provenance_rejected(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(
        '{"documents":[{"product":"p","external_id":"a","title":"t","applicability_provenance":"guessed","content":"c"}]}'
    )
    with pytest.raises(IngestionFormatError):
        JsonFixtureLoader().load(p)


def test_path_guard_blocks_traversal_and_absolute(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "ok.md").write_text("x")
    assert resolve_within_root("ok.md", root) == (root / "ok.md").resolve()
    with pytest.raises(ForbiddenPathError):
        resolve_within_root("../etc/passwd", root)
    with pytest.raises(ForbiddenPathError):
        resolve_within_root("/etc/passwd", root)
    with pytest.raises(FileNotFoundError):
        resolve_within_root("missing.md", root)
