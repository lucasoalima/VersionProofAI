from __future__ import annotations

from sqlalchemy.orm import Session

from app.embeddings.interfaces import EmbeddingUnavailable
from app.embeddings.providers import get_embedding_provider
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.interfaces import Retriever
from app.retrieval.lexical import LexicalRetriever
from app.retrieval.semantic import SemanticRetriever


def build_retriever(db: Session, mode: str) -> Retriever:
    if mode == "lexical":
        return LexicalRetriever(db)
    provider = get_embedding_provider()
    if provider is None:
        raise EmbeddingUnavailable(
            f"{mode} retrieval requires an embedding provider (EMBEDDING_PROVIDER is 'none')."
        )
    semantic = SemanticRetriever(db, provider)
    if mode == "semantic":
        return semantic
    if mode == "hybrid":
        return HybridRetriever(LexicalRetriever(db), semantic)
    raise ValueError(f"unknown retrieval mode {mode!r}")
