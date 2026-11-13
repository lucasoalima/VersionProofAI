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

## Phase 5: baseline comparison (answer level)

| | Engine | Retrieval | Abstention / verdict logic |
|---|---|---|---|
| A | `NoRetrievalEngine` | none | model self-report only. **Requires an LLM; never simulated.** |
| B | `TraditionalRagEngine` | same retriever, `enforce_version=false` | none: answers from the top results and presents the answer as valid (verdict recorded as `applies`) |
| C | `AnswerEngine` | version-constrained + exclusion list | coverage-based abstention, evidence-derived verdict, conflict surfacing, citation validation |

B and C share the retriever, corpus, `top_k` and generation mode, so the only independent
variable is version-awareness. Run with `scripts/benchmark_all.py` (writes JSON + CSV under
`reports/`) or from the Evaluation Lab.

### Splits
- `nimbus-synthetic:1` (**dev**, 10 q): used while designing C's rules. Results on it are tuned.
- `nimbus-synthetic-heldout:1` (**held_out**, 12 q): written before any run and never used to
  change a rule or threshold. After the single run below, **no change was made to the engine**.

### Measured (2026-11-12, hybrid retrieval, k=5, `hashed-bow-v1` embeddings, extractive generation)

| split | engine | correct abstention | applicability acc. | outdated recommendation | citation validity | supported answer |
|---|---|---|---|---|---|---|
| dev | B traditional RAG | 0.80 | 0.60 | 0.50 | 0.60 | 0.67 |
| dev | C VersionProof | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 |
| held-out | B traditional RAG | 0.83 | 0.58 | 0.33 | 0.75 | 0.86 |
| held-out | C VersionProof | 1.00 | 0.92 | 0.00 | 1.00 | 1.00 |

Baseline A was **not run** (no LLM available in the development environment).

### What this does and does not show
- On held-out questions C cited no outdated source (B: 1 of 3 outdated-trap questions; an earlier
  run reported 2 of 3 because two near-identical documents tied in semantic search and the
  tie-break was not deterministic. It now is, and the table shows the deterministic run) and its
  citations were all applicable (B: 0.67). This is consistent with H1 at the mechanism level.
- C's held-out miss (h03, "Is the Async Trigger Framework available?" on Summer '24): an
  applicable document that merely *mentions* the framework cleared the coverage threshold, so C
  answered `applies` instead of `not_applicable`. Lexical coverage cannot tell "about X" from
  "mentions X". Left unfixed on purpose: fixing it now would turn the held-out set into a dev set.
- n = 12, one fictional product, questions and corpus by the same author, extractive generation,
  a bag-of-words stand-in for embeddings. The corpus was built to contain version traps, so the
  size of the B-C gap says nothing about real documentation. No statistical claim is made.
- C is slower (p50 roughly 2x B) because of the second pass that builds the exclusion list.

## LLM-judged metrics (Ragas)
VersionProof does not execute an LLM judge. `GET /api/evaluation/runs/{id}/ragas.json` exports
answer runs as `question / answer / contexts / ground_truth` records, the shape Ragas-style
faithfulness, answer-relevancy and context precision/recall evaluators consume. Running them
needs a judge model and the current Ragas API, neither of which could be verified in the
development environment, so no Ragas code path is claimed to work. Judge scores, when produced,
must be stored with the judge model id and reported separately from the deterministic metrics.

## Observability
Every HTTP request is logged as structured JSON (`request_id`, method, path, status,
`duration_ms`) and returns `x-request-id` and `server-timing` headers; answers and benchmark rows
carry retrieval and end-to-end latency. OpenTelemetry tracing and token-cost accounting are not
implemented (cost is only measurable with a real LLM provider).

## Phase 6: real documentation (Salesforce CLI release notes)

Corpus: 157 released versions, 614 entries (see docs/sources.md). Dataset
`salesforce-cli-real:1`: 11 questions whose reference answers were checked against the source
text by the author. Hybrid retrieval, k=5, `hashed-bow-v1` embeddings, extractive generation.

### First run: a negative result
The questions were written before any run on this corpus. With the engine exactly as tuned on
synthetic data, VersionProof was **worse** than traditional RAG:

| run | engine | correct abstention | applicability acc. | outdated recommendation | citation validity | supported answer |
|---|---|---|---|---|---|---|
| first run | B traditional RAG | 0.91 | 0.82 | 0.43 | 0.91 | 0.44 |
| first run | C VersionProof | **0.18** | **0.18** | **0.57** | 1.00 | 0.56 |

Two design assumptions did not survive real data:
1. **Conflict detection** treated "similar titles, different numbers" as a contradiction. Every
   release note is titled "Salesforce CLI x.y.z release notes", so any two versions "conflicted"
   and the engine abstained on 8 of 11 questions.
2. **Coverage** counted the product's own name ("Salesforce", "CLI"), present in every chunk, as
   evidence of topicality, so the not-in-corpus question was answered instead of abstained.

### After two rule changes (this set is now a dev set)
- Changelog entries of different releases are not conflicts (they are ordered by release).
- Terms present in more than 25% of a product's chunks are ignored for coverage, when the product
  has at least 100 chunks.

| run | engine | correct abstention | applicability acc. | outdated recommendation | citation validity | supported answer |
|---|---|---|---|---|---|---|
| after changes | B traditional RAG | 0.91 | 0.82 | 0.43 | 0.91 | 0.44 |
| after changes | C VersionProof | 1.00 | 0.91 | 0.00 | 1.00 | 1.00 |

The synthetic dev and held-out results for C were unchanged by these changes (regression check).
C's remaining miss (r08) is the same failure seen on synthetic held-out: an applicable entry that
mentions `agent test run` was taken as evidence that `agent test run-eval` exists in that version.

### What can be claimed
- The first-run table is the only untuned measurement on real documentation, and it is negative.
- The second table shows the mechanism works on this corpus once two corpus-shape assumptions
  are fixed; it was tuned on these 11 questions and proves nothing about unseen questions.
- A new real held-out set (different questions, ideally a different author, ideally a second
  source) is required before H1 can be evaluated on real documentation.
- "Most recent applicable release first" was decided before the first run, from the nature of
  release notes, and is a heuristic, not verified applicability.
- C's p50 latency on this corpus is about 4x B's (51 ms vs 13 ms): exclusion pass plus per-term
  document-frequency queries. Not optimised.
