"""Semantic retrieval: exact cosine nearest-neighbour search in pgvector.

Exact search (sequential scan) is used deliberately; an HNSW/IVFFlat index is introduced only
when measured latency on a real corpus justifies the recall trade-off (see retrieval-design.md).
Only chunks embedded by the active model are candidates, so a model change never mixes spaces.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.embeddings.interfaces import EmbeddingProvider
from app.models import DocumentChunk
from app.retrieval.base import base_statement, load_product, row_to_evidence, target_sequence
from app.retrieval.interfaces import Evidence, RetrievalFilters


class SemanticRetriever:
    name = "semantic"

    def __init__(self, db: Session, provider: EmbeddingProvider):
        self.db = db
        self.provider = provider

    def retrieve(self, query: str, filters: RetrievalFilters, top_k: int) -> list[Evidence]:
        product = load_product(self.db, filters.product_slug)
        target_seq = target_sequence(self.db, product, filters.target_version)
        qvec = self.provider.embed([query])[0]
        distance = DocumentChunk.embedding.cosine_distance(qvec)
        similarity = 1 - distance
        stmt = (
            base_statement(similarity, product, filters, target_seq)
            .where(DocumentChunk.embedding.is_not(None))
            .where(DocumentChunk.embedding_model == self.provider.model_id)
            .order_by(distance)
            .limit(top_k)
        )
        rows = list(self.db.execute(stmt))
        diag = {"embedding_model": self.provider.model_id, "metric": "cosine"}
        return [row_to_evidence(r, i, target_seq, self.name, diag) for i, r in enumerate(rows, 1)]
