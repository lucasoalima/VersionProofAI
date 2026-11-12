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

Retrieval-only metrics for B vs C run **without** an LLM.

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
