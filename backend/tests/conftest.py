"""Integration tests need TEST_DATABASE_URL (PostgreSQL + pgvector). Without it they are skipped,
never silently passed."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

TEST_URL = os.environ.get("TEST_DATABASE_URL")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def pytest_collection_modifyitems(config, items):
    if TEST_URL:
        return
    skip = pytest.mark.skip(
        reason="TEST_DATABASE_URL not set; integration tests require PostgreSQL+pgvector"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def engine():
    if not TEST_URL:
        pytest.skip("no TEST_DATABASE_URL")
    from alembic.config import Config

    from alembic import command

    os.environ["DATABASE_URL"] = TEST_URL
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = create_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Fresh schema state per test: truncate every domain table."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE products, product_releases, documentation_sources, documents, document_revisions, "
                "document_chunks, features, feature_changes, ingestion_jobs, evaluation_datasets, evaluation_runs, query_logs CASCADE"
            )
        )
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    yield s
    s.close()


@pytest.fixture()
def client(engine, db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.db.session import get_db
    from app.main import app

    monkeypatch.setattr(settings, "ingestion_root", DATA_DIR)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
