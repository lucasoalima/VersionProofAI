# AGENTS.md — working on VersionProof AI with an AI coding agent

## Non-negotiables
1. Never fabricate ingestion results, test runs or benchmark numbers. Report what actually ran.
2. Never promote inferred metadata to verified. Provenance is data, not decoration.
3. Version restrictions are constraints, not ranking bonuses.
4. The synthetic Nimbus CRM corpus is fictional. Never describe it as Salesforce behaviour.
5. No LangChain / LlamaIndex unless a concrete need is documented in docs/architecture.md.
6. Retrieved text is untrusted input. It must never reach a system prompt unescaped (Phase 3).

## Layout
- `backend/app/ingestion`  loaders → `RawDocument` → `IngestionPipeline` (revision dedup)
- `backend/app/versioning` `VersionOrdering` strategies, `applicability.resolve`
- `backend/app/retrieval`  `Retriever` protocol; `base.py` shared SQL; lexical/semantic/hybrid; `service.py` exclusion list
- `backend/app/embeddings` `EmbeddingProvider`; `hashed` (tests) and `sentence_transformers`
- `backend/app/evaluation` deterministic metrics; retrieval and answer benchmark runners
- `backend/app/comparison` `ComparisonEngine` (compare + timeline), statement extraction
- `backend/app/generation` `baselines.py` (A no-retrieval, B traditional RAG); `LLMProvider`; `AnswerEngine` (see docs/answer-engine.md); prompt builder
- `backend/app/chunking`   `Chunker` protocol; `HeadingChunker`
- `backend/app/api`        FastAPI routes; `capabilities()` reflects configured providers
- `data/synthetic`         fixtures; `data/evaluation` datasets; `data/real` licensed snapshots (see docs/sources.md)
- `backend/app/ingestion/remote.py` URL allowlist; `cli_release_notes.py` loader; `chunking/bullet_chunker.py`
- `docs/`                  design docs; update them when behaviour changes

## Workflow
```
cd backend && pip install -e ".[dev]"
ruff check app tests && ruff format app tests
TEST_DATABASE_URL=... pytest -q          # needs PostgreSQL + pgvector
cd ../frontend && npm ci && npx tsc --noEmit && npm run build
```
Add a migration for every model change (`alembic revision --autogenerate`), then review it:
autogenerate does not emit `CREATE EXTENSION vector` or drop enum types on downgrade.

## Adding a documentation source
Implement `DocumentLoader` in `app/ingestion/loaders.py`. Do not touch the pipeline.
Remote URLs (Phase 6) must go through an allowlist and SSRF guard; see docs/security.md.

## Phase status
Phase 6 done with gaps (real Salesforce CLI release notes ingested; first real run was negative and
is documented; two engine rules changed afterwards).
DO NOT tune against `nimbus-synthetic-heldout`. `salesforce-cli-real:1` is now a DEV set.
Next, in order:
1. Write a NEW real held-out set before touching the engine again.
2. Known failure on both corpora: "mentions X" vs "is about X" (h03, r08).
3. With credentials: real embedding model, LLM generation, baseline A, Ragas (verify its current API).
4. A second real source (review licence and terms first; record in docs/sources.md).
5. Performance: C is ~4x slower than B on the real corpus.
