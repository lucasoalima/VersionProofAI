import math

from app.evaluation import metrics as m


def test_recall_mrr_ndcg_basic():
    ranked = ["x", "a", "b", "y"]
    rel = {"a", "b", "c"}
    assert math.isclose(m.recall_at_k(ranked, rel, 3), 2 / 3)
    assert m.recall_at_k(ranked, rel, 1) == 0.0
    assert m.mrr(ranked, rel) == 0.5
    assert m.mrr(["q"], rel) == 0.0
    gains = {"a": 1.0, "b": 1.0, "c": 1.0}
    dcg = 1 / math.log2(3) + 1 / math.log2(4)
    idcg = 1 + 1 / math.log2(3) + 1 / math.log2(4)
    assert math.isclose(m.ndcg_at_k(ranked, gains, 4), dcg / idcg)


def test_abstention_cases_return_none_not_zero():
    assert m.recall_at_k(["a"], set(), 5) is None
    assert m.mrr(["a"], set()) is None
    assert m.ndcg_at_k(["a"], {"old": 0.0}, 5) is None
    assert m.summarize([None, None]) is None
    assert m.summarize([1.0, None, 0.0]) == 0.5


def test_outdated_and_applicability():
    assert m.outdated_in_top_k(["new", "old"], {"old"}, 2) is True
    assert m.outdated_in_top_k(["new", "old"], {"old"}, 1) is False
    assert m.applicability_accuracy("applies", "applies") is True
    assert m.applicability_accuracy(None, "unknown") is True
    assert m.applicability_accuracy(None, "applies") is False
