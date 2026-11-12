import math

from app.embeddings.providers import HashedBagOfWordsProvider
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.interfaces import Evidence
from app.versioning.applicability import ApplicabilityStatus


def test_hashed_provider_is_deterministic_normalised_and_overlap_sensitive():
    p = HashedBagOfWordsProvider(384)
    a, b = p.embed(["scheduled jobs concurrency limit"] * 2)
    assert a == b and len(a) == 384
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    near = p.embed(["how many scheduled jobs run concurrently"])[0]
    far = p.embed(["platform cache partition sizing"])[0]
    dot = lambda u, v: sum(x * y for x, y in zip(u, v, strict=True))  # noqa: E731
    assert dot(a, near) > dot(a, far)


def _ev(cid: str, rank: int, strategy: str) -> Evidence:
    return Evidence(
        chunk_id=cid,
        document_id="d",
        revision_id="r",
        title=cid,
        source_url=None,
        heading=None,
        excerpt="",
        score=1.0,
        rank=rank,
        effective_from=None,
        effective_to=None,
        applicability_status=ApplicabilityStatus.unknown,
        applicability_provenance="unknown",
        published_at=None,
        trust_level="synthetic",
        strategy=strategy,
    )


def test_rrf_rewards_agreement_and_is_deterministic():
    lex = [_ev("A", 1, "lexical"), _ev("B", 2, "lexical"), _ev("C", 3, "lexical")]
    sem = [_ev("B", 1, "semantic"), _ev("D", 2, "semantic"), _ev("A", 3, "semantic")]
    fused = HybridRetriever.fuse({"lexical": lex, "semantic": sem}, k=60)
    order = [e.chunk_id for e, _, _ in fused]
    assert order[0] == "B" or order[0] == "A"  # both appear in both lists
    assert set(order[:2]) == {"A", "B"}
    assert order.index("C") > order.index("D") or order.index("D") > order.index(
        "C"
    )  # singletons last
    assert order[2:] == sorted(order[2:], key=lambda c: -(1 / (60 + {"C": 3, "D": 2}[c])))
    _, score_b, ranks_b = next(t for t in fused if t[0].chunk_id == "B")
    assert math.isclose(score_b, 1 / 61 + 1 / 62) and ranks_b == {"lexical": 2, "semantic": 1}
    assert fused == HybridRetriever.fuse({"lexical": lex, "semantic": sem}, k=60)
