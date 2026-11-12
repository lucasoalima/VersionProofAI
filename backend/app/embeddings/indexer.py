"""Populate DocumentChunk.embedding for chunks that lack a vector from the given model.

Idempotent: chunks already embedded by the same model_id are skipped; chunks embedded by
a different model are re-embedded (one model per deployment is the supported mode)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.embeddings.interfaces import EmbeddingProvider
from app.models import DocumentChunk


@dataclass
class IndexResult:
    model_id: str
    embedded: int
    skipped: int


def build_embeddings(db: Session, provider: EmbeddingProvider, batch_size: int = 64) -> IndexResult:
    total = db.scalar(select(__import__("sqlalchemy").func.count()).select_from(DocumentChunk)) or 0
    stmt = (
        select(DocumentChunk)
        .where(
            or_(
                DocumentChunk.embedding.is_(None),
                DocumentChunk.embedding_model != provider.model_id,
            )
        )
        .order_by(DocumentChunk.id)
    )
    pending = list(db.scalars(stmt))
    done = 0
    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        vectors = provider.embed([c.content for c in batch])
        for chunk, vec in zip(batch, vectors, strict=True):
            chunk.embedding = vec
            chunk.embedding_model = provider.model_id
        db.flush()
        done += len(batch)
    db.commit()
    return IndexResult(model_id=provider.model_id, embedded=done, skipped=int(total) - done)
