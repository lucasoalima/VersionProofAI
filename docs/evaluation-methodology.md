# Evaluation methodology

**Research question.** Does version-aware hybrid retrieval reduce outdated technical
recommendations compared with traditional RAG?

**Hypothesis (H1).** For version-sensitive questions, VersionProof (hybrid retrieval + version
constraints) yields a lower outdated-recommendation rate and higher version-applicability accuracy
than traditional RAG, at comparable answer relevancy. **H0:** no difference. The lab must be able
to report H0, or a mixed result (e.g. better applicability, worse recall).

## Variables
- Independent: retrieval strategy ∈ {no retrieval (A), traditional RAG (B), VersionProof (C)}.
- Dependent: the metrics below.
- Controls: identical questions, identical LLM and generation settings, same corpus snapshot,
  same `top_k`, fixed seeds where applicable, dataset version pinned in `EvaluationRun.config`.

## Baselines
| | Retrieval | Version constraint | Needs LLM |
|---|---|---|---|
| A | none | — | yes |
| B | hybrid, `enforce_version=false` | labels only | yes |
| C | hybrid, `enforce_version=true` + evidence validation | constraint | yes (abstention also testable without) |

Retrieval-only metrics for B vs C run **without** an LLM — this is what Phase 2 implements:
`scripts/benchmark_retrieval.py`, `POST /api/evaluation/retrieval-runs`, or the Evaluation Lab.

## Retrieval-level definitions used by the runner
- Ranked list = document external_ids of the top-k chunks, deduplicated, first occurrence wins.
- Recall@k, MRR, nDCG@k are `None` (not 0) for questions without supporting documents, and
  excluded from the aggregate; those questions are scored by abstention metrics in Phase 3.
- **Outdated surfaced rate**: among questions that name an `outdated_document_ids` entry, the
  share where that document reached the top-k results. It is the retrieval precursor of the
  outdated-recommendation rate: a generator can only cite what retrieval surfaces.
- **Applicability accuracy**: top result's status equals `expected_applicability_status`.
  When `not_applicable` is expected, finding a supporting document in the *excluded* list (verified
  not applicable to the target) also counts — that is precisely the correct behaviour.
- Latency: wall clock per question (p50 and max). Constrained runs include the second pass that
  builds the excluded list.

## Measured results (synthetic corpus, k=5, `hashed-bow-v1` embeddings)
Recorded with `scripts/benchmark_retrieval.py` in the development environment on 2026-11-12.
The embedding is a deterministic bag-of-words stand-in, so absolute semantic/hybrid figures are
not representative of a real model; the lexical rows and the constrained-vs-unconstrained
contrast are.

| strategy | Recall@5 | MRR | nDCG@5 | outdated surfaced | applicability acc. |
|---|---|---|---|---|---|
| lexical, constrained | 0.83 | 0.83 | 0.85 | 0.00 | 0.90 |
| lexical, unconstrained | 0.94 | 0.81 | 0.75 | 1.00 | 0.60 |
| semantic, constrained | 0.83 | 0.89 | 0.89 | 0.00 | 0.90 |
| semantic, unconstrained | 1.00 | 0.89 | 0.88 | 1.00 | 0.70 |
| hybrid, constrained | 0.83 | 0.83 | 0.85 | 0.00 | 0.90 |
| hybrid, unconstrained | 1.00 | 0.89 | 0.88 | 1.00 | 0.70 |

Observations, not conclusions (n=10, synthetic):
- The constraint removes every outdated-trap source from the result set (1.00 → 0.00).
- Recall drops where the correct answer is "not available in this version" (cases 2 and 7):
  the supporting document is, by design, excluded from results and appears in the excluded list,
  which the applicability metric credits (0.70 → 0.90).
- The remaining applicability miss is the not-in-KB question (case 5): retrieval always returns
  something; abstention is a generation-time decision (Phase 3).
- Hybrid does not beat semantic here because the hashed embedding is itself lexical; the
  comparison is only meaningful with a real embedding model.

## Dataset records
`question, product, target_version, reference_answer, supporting_document_ids,
outdated_document_ids, expected_applicability_status, should_abstain`.
The synthetic set (`data/evaluation/synthetic_v1.json`, 10 records, split `dev`) covers the eight
required case types. A held-out split and a verified public-documentation set come later and are
kept separate from tuning data.

## Deterministic metrics
| Metric | Definition |
|---|---|
| Recall@k | fraction of `supporting_document_ids` present in top-k |
| MRR | 1 / rank of the first supporting document |
| nDCG@k | graded: supporting = 1, outdated = 0, others = 0 |
| Citation validity rate | cited chunk ids that exist and belong to an `applies` revision |
| Version applicability accuracy | predicted status == `expected_applicability_status` |
| Outdated recommendation rate | answers citing or recommending an `outdated_document_ids` entry |
| Correct abstention rate | abstained == `should_abstain` |
| Retrieval / end-to-end latency | wall clock, p50/p95 |
| Approximate cost | provider-reported tokens × list price, when available |

## LLM-judged metrics (Ragas, optional)
Context precision/recall, faithfulness, answer relevancy — reported separately and **not** treated
as ground truth; judge model and version are recorded.

## Reproducibility
`EvaluationRun` stores strategy, config, dataset name+version, model identifier, timestamps,
aggregate metrics and per-question results. Reports export as JSON and CSV.

## Threats to validity
Small synthetic dataset; author-written questions; judge bias; corpus constructed to contain the
answer; single product; lexical baseline in PostgreSQL rather than BM25.
