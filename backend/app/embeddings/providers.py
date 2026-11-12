from __future__ import annotations

import hashlib
import math
import re

from app.core.config import settings
from app.embeddings.interfaces import EmbeddingProvider, EmbeddingUnavailable


class HashedBagOfWordsProvider:
    """Deterministic, dependency-free embedding used for tests and offline development.

    Each lower-cased token (and each 3-gram inside it) is hashed into one of `dimensions`
    buckets with a signed weight; the vector is L2-normalised. It captures lexical overlap
    with some tolerance to inflection, NOT semantics. It is labelled as such everywhere
    (model_id = "hashed-bow-v1") so no evaluation can mistake it for a real model.
    """

    name = "hashed"
    model_id = "hashed-bow-v1"
    _tok = re.compile(r"[a-z0-9_.]+")

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def _features(self, text: str) -> list[str]:
        feats: list[str] = []
        for tok in self._tok.findall(text.lower()):
            feats.append(tok)
            if len(tok) >= 5:
                feats.extend(tok[i : i + 3] for i in range(len(tok) - 2))
        return feats

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dimensions
            for f in self._features(text):
                h = hashlib.blake2b(f.encode(), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "little") % self.dimensions
                sign = 1.0 if h[4] & 1 else -1.0
                vec[idx] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class SentenceTransformersProvider:
    name = "sentence_transformers"

    def __init__(self, model_id: str, dimensions: int):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise EmbeddingUnavailable(
                "sentence-transformers is not installed; pip install -e '.[embeddings]'"
            ) from exc
        self.model_id = model_id
        self.dimensions = dimensions
        self._model = SentenceTransformer(model_id)
        got = self._model.get_sentence_embedding_dimension()
        if got != dimensions:
            raise EmbeddingUnavailable(
                f"model {model_id} produces {got}-d vectors but the schema stores {dimensions}-d"
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).tolist()


def get_embedding_provider() -> EmbeddingProvider | None:
    """None when EMBEDDING_PROVIDER=none. Raises EmbeddingUnavailable on a broken config."""
    p = settings.embedding_provider
    if p == "none":
        return None
    if p == "hashed":
        return HashedBagOfWordsProvider(settings.embedding_dimensions)
    if p == "sentence_transformers":
        return SentenceTransformersProvider(settings.embedding_model, settings.embedding_dimensions)
    raise EmbeddingUnavailable(f"unknown EMBEDDING_PROVIDER {p!r}")
