"""Hybrid retrieval: Reciprocal Rank Fusion of lexical and semantic candidate lists.

RRF(d) = Σ_i 1 / (k + rank_i(d)), k = 60 (Cormack et al., 2009). Each strategy contributes
`candidate_multiplier * top_k` candidates; fused results are truncated to top_k. Version
constraints were already applied inside each retriever, so fusion cannot resurrect an excluded
revision. An optional Reranker re-orders the fused list; it never adds candidates.
"""

from __future__ import annotations

from typing import Protocol

from app.retrieval.interfaces import Evidence, RetrievalFilters, Retriever


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, candidates: list[Evidence]) -> list[Evidence]: ...


class HybridRetriever:
    name = "hybrid"

    def __init__(
        self,
        lexical: Retriever,
        semantic: Retriever,
        k: int = 60,
        candidate_multiplier: int = 3,
        reranker: Reranker | None = None,
    ):
        self.lexical = lexical
        self.semantic = semantic
        self.k = k
        self.candidate_multiplier = candidate_multiplier
        self.reranker = reranker

    @staticmethod
    def fuse(
        lists: dict[str, list[Evidence]], k: int
    ) -> list[tuple[Evidence, float, dict[str, int]]]:
        scores: dict[str, float] = {}
        ranks: dict[str, dict[str, int]] = {}
        first: dict[str, Evidence] = {}
        for strategy, evidences in lists.items():
            for e in evidences:
                scores[e.chunk_id] = scores.get(e.chunk_id, 0.0) + 1.0 / (k + e.rank)
                ranks.setdefault(e.chunk_id, {})[strategy] = e.rank
                first.setdefault(e.chunk_id, e)
        ordered = sorted(scores.items(), key=lambda kv: (-kv[1], first[kv[0]].title, kv[0]))
        return [(first[cid], s, ranks[cid]) for cid, s in ordered]

    def retrieve(self, query: str, filters: RetrievalFilters, top_k: int) -> list[Evidence]:
        n = top_k * self.candidate_multiplier
        lists = {
            self.lexical.name: self.lexical.retrieve(query, filters, n),
            self.semantic.name: self.semantic.retrieve(query, filters, n),
        }
        fused: list[Evidence] = []
        for i, (e, score, ranks) in enumerate(self.fuse(lists, self.k), 1):
            fused.append(
                Evidence(
                    **{
                        **e.__dict__,
                        "score": score,
                        "rank": i,
                        "strategy": self.name,
                        "diagnostics": {**e.diagnostics, "rrf_k": self.k, "component_ranks": ranks},
                    }
                )
            )
        if self.reranker:
            fused = self.reranker.rerank(query, fused)
            for i, e in enumerate(fused, 1):
                e.rank = i
        return fused[:top_k]
