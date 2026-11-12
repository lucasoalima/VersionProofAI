"""Embedding provider contract. Providers are replaceable; the rest of the system only
sees `embed()` and `model_id`. Dimension must match DocumentChunk.embedding (384)."""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str
    model_id: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingUnavailable(RuntimeError):
    """Raised when the configured provider cannot run (missing dependency, no model)."""
