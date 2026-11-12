# VersionProof AI

**Version-aware documentation retrieval: relevant is not the same as still valid.**

VersionProof AI is an open-source AI Engineering project that helps software engineers determine
whether a documented technical solution still applies to a specific software version. It combines
hybrid retrieval, explicit version-applicability metadata, document revision tracking and a
reproducible evaluation lab that measures whether version-aware retrieval actually reduces
outdated recommendations compared with conventional RAG.

> **Status: Phase 4 (Version Intelligence) complete.** Ingestion, versioned knowledge base,
> lexical + semantic + hybrid retrieval with version constraints and an exclusion list, a
> grounded answer engine (abstention, conflict surfacing, validated citations; LLM optional),
> deterministic version comparison with a release timeline, retrieval and answer benchmarks,
> dashboard, tests and CI. The LLM baselines A/B, Ragas and a held-out dataset (Phase 5) and
> real Salesforce documentation (Phase 6) are not implemented yet. The UI says so explicitly
> rather than showing placeholder numbers. See [docs/limitations.md](docs/limitations.md).

## 1. The problem

A developer adds a workaround for a platform limitation. Two releases later the platform fixes
the limitation. The workaround document is still *semantically* the best match for any question
about that limitation — so a conventional RAG assistant keeps recommending it. The motivating
case for this project came from exactly that experience on a Salesforce project; the system is
designed to be platform-agnostic.

## 2. Why conventional RAG gives outdated answers

Vector similarity measures topical closeness, not temporal validity. A chunk describing the old
behaviour and a chunk describing the new behaviour are both "about" the feature; the obsolete one
often scores *higher* because it uses the same vocabulary as the question ("limit", "workaround").
Publication dates don't fix this: a document published in 2023 can describe behaviour that still
holds, and a 2025 page can describe a feature that did not exist in the release you run.

## 3. How version-aware retrieval works here

```mermaid
flowchart LR
  Q[Question + product + target version] --> L[Lexical FTS]
  Q --> S[Semantic pgvector]
  L --> F[Reciprocal Rank Fusion]
  S --> F
  F --> C{Applicability<br/>constraint}
  C -- verified & in range --> E[Evidence: applies]
  C -- verified & out of range --> X[Excluded list<br/>explains, never recommends]
  C -- unknown / inferred --> U[Evidence: flagged unknown/inferred]
  E --> A[Grounded answer + validated citations]
  U --> A
```

* Every document revision stores an **applicability range** in releases (`effective_from`,
  `effective_to`) plus a **provenance**: `verified`, `inferred` or `unknown`. Nothing inferred is
  ever stored where a reader would take it as fact.
* Release ordering is a **per-product strategy** (`semver`, `salesforce_seasonal`, `explicit`),
  so "Winter '26 < Spring '26" works without assuming semantic versioning.
* Version restrictions are **constraints applied in SQL**, not ranking bonuses: a revision that is
  verified not to apply to the target release is excluded. Revisions whose applicability is
  unknown are returned but labelled, so the caller (and later the answer engine) can abstain.
* Technical identifiers (`NIMBUS_LIMIT_EXCEEDED_0427`, `Foo.bar()`, `Spring '25`) are indexed
  verbatim with positions and a higher weight than stemmed prose, so an exact error-code hit
  outranks a paraphrase. See [docs/retrieval-design.md](docs/retrieval-design.md).

## 4. Running the application

```bash
cp .env.example .env
docker compose up --build        # db (pgvector/pg16) + backend :8000 + frontend :3000
```

Without Docker:

```bash
# PostgreSQL 16 with the pgvector extension must be reachable at DATABASE_URL
cd backend && pip install -e ".[dev]" && alembic upgrade head
uvicorn app.main:app --reload --port 8000
cd ../frontend && npm install && npm run dev
```

No Salesforce credentials, no LLM key and no embedding model are required. The dashboard's
capability panel reflects what is configured.

## 5. Importing documentation

Everything under `data/` (configurable with `INGESTION_ROOT`) can be ingested from the
Knowledge Base page or the API:

```bash
curl -X POST localhost:8000/api/ingestion/local -H 'content-type: application/json' -d '{"path":"synthetic"}'
# or: cd backend && python scripts/seed.py
```

Supported inputs: JSON fixtures, Markdown with YAML front matter, plain text with a `.meta.yaml`
sidecar. The shipped corpus is **Nimbus CRM**, a fictional product — see
[data/synthetic/README.md](data/synthetic/README.md). It is not Salesforce documentation.

Re-ingesting unchanged content creates no new revision; changed content creates a new
`DocumentRevision` and keeps the old one.

## 6. Executing evaluation benchmarks

Retrieval-only benchmarks (no LLM) run from the Evaluation Lab page, the API
(`POST /api/evaluation/retrieval-runs`) or the CLI:

```bash
cd backend && python scripts/seed.py                       # registers data/evaluation/synthetic_v1.json
EMBEDDING_PROVIDER=hashed python scripts/benchmark_retrieval.py   # lexical/semantic/hybrid x constrained/unconstrained
EMBEDDING_PROVIDER=hashed python scripts/benchmark_answers.py     # answer engine: abstention, citations, verdicts
```

`EMBEDDING_PROVIDER=sentence_transformers` (with `pip install -e ".[embeddings]"`) uses a real
model; `hashed` is a deterministic bag-of-words stand-in for offline tests and is labelled as
such in every run. Every run stores its configuration, dataset version, model id, timestamps,
aggregate metrics and per-question results; JSON and CSV exports are one click away.

## 7. Interpreting benchmark results

Measured on the synthetic corpus, hybrid retrieval, k=5, `hashed-bow-v1` embeddings
(so the absolute numbers say nothing about a real embedding model — the *contrast* is the point):

| | Recall@5 | nDCG@5 | Outdated source surfaced | Applicability accuracy |
|---|---|---|---|---|
| hybrid, no version constraint (traditional RAG) | 1.00 | 0.88 | **100 %** of outdated-trap questions | 0.70 |
| hybrid, version constraint (VersionProof) | 0.83 | 0.85 | **0 %** | 0.90 |

The constraint eliminates outdated sources from the recommendation set at the cost of recall
on questions whose correct answer is "this does not exist in your version" — which is why the
excluded list exists: the supporting document is still found, labelled *not applicable*, and
kept out of the recommendations. The remaining applicability miss is the not-in-KB question;
retrieval always returns *something*; abstaining is the answer engine's job.

Answer-level run (extractive mode, no LLM, same dataset): correct abstention 1.00, applicability
accuracy 1.00, outdated recommendation 0.00, citation validity 1.00, supported answers 1.00.
**Read this as a smoke test, not a result**: the abstention and verdict rules were adjusted
while looking at these same 10 questions, so the figures are tuned-on-dev by construction. A
held-out and a real-documentation dataset are required before any claim
(see [docs/answer-engine.md](docs/answer-engine.md)). Full
definitions in [docs/evaluation-methodology.md](docs/evaluation-methodology.md). The dashboard
only shows metrics from recorded `EvaluationRun` rows; it never displays illustrative numbers.

## 8. What the system cannot reliably determine

* Applicability for documents with no verified release metadata (it says "unknown").
* Whether a feature was removed when a newer document simply doesn't mention it.
* Which of two conflicting sources is right (it surfaces the conflict).
* Anything not in the knowledge base. Full list: [docs/limitations.md](docs/limitations.md).

## Repository layout

```
backend/   FastAPI · SQLAlchemy · Alembic · pgvector · pytest
frontend/  Next.js 15 · TypeScript · Tailwind
data/      synthetic corpus + evaluation dataset
docs/      architecture, data model, retrieval, versioning, evaluation, security, limitations
```

## Testing

```bash
cd backend
pytest -q                                   # unit tests only (integration skipped, not faked)
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/versionproof_test pytest -q
```

Integration tests run against a real PostgreSQL + pgvector instance (the CI workflow provisions
one). They are **skipped, never silently passed**, when `TEST_DATABASE_URL` is unset.

## License

MIT (synthetic data included).
