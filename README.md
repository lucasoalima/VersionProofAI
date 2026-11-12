# VersionProof AI

**Version-aware documentation retrieval: relevant is not the same as still valid.**

VersionProof AI is an open-source AI Engineering project that helps software engineers determine
whether a documented technical solution still applies to a specific software version. It combines
hybrid retrieval, explicit version-applicability metadata, document revision tracking and a
reproducible evaluation lab that measures whether version-aware retrieval actually reduces
outdated recommendations compared with conventional RAG.

> **Status: Phase 1 (Foundation) complete.** Ingestion, versioned knowledge base, deterministic
> lexical retrieval with version constraints, dashboard, tests and CI. Semantic/hybrid retrieval
> (Phase 2), grounded answer generation (Phase 3), version comparison (Phase 4), the evaluation
> lab (Phase 5) and real Salesforce documentation (Phase 6) are not implemented yet. The UI says
> so explicitly rather than showing placeholder numbers. See [docs/limitations.md](docs/limitations.md).

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
  Q --> S[Semantic pgvector<br/>Phase 2]
  L --> F[Reciprocal Rank Fusion<br/>Phase 2]
  S --> F
  F --> C{Applicability<br/>constraint}
  C -- verified & in range --> E[Evidence: applies]
  C -- verified & out of range --> X[Excluded]
  C -- unknown / inferred --> U[Evidence: flagged unknown/inferred]
  E --> A[Grounded answer + citations<br/>Phase 3]
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

Not yet available (Phase 5). The synthetic evaluation dataset
(`data/evaluation/synthetic_v1.json`) is already registered by `scripts/seed.py`; the three
baselines (no retrieval / traditional RAG / VersionProof) and the metrics are described in
[docs/evaluation-methodology.md](docs/evaluation-methodology.md).

## 7. Interpreting benchmark results

See [docs/evaluation-methodology.md](docs/evaluation-methodology.md). The dashboard only shows
metrics from recorded `EvaluationRun` rows; it never displays illustrative numbers.

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
