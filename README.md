# VersionProof AI

**Version-aware retrieval for technical documentation. Relevant is not the same as still valid.**

[![CI](https://github.com/lucasoalima/VersionProofAI/actions/workflows/ci.yml/badge.svg)](https://github.com/lucasoalima/VersionProofAI/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791)
![Next.js](https://img.shields.io/badge/Next.js-15-black)
![License](https://img.shields.io/badge/license-MIT-green)

VersionProof AI answers a question that ordinary RAG systems skip: **does this documented solution
apply to the software version I am actually running?** It combines hybrid retrieval with explicit
version-applicability metadata, refuses to answer when the evidence is insufficient, and ships an
evaluation lab that measures whether any of this helps, including when it does not.

![Asking about a removed command on a version after the removal](docs/images/ask-real-after-removal.png)

*Real Salesforce CLI release notes. For version 2.121.7 the answer cites the note that removed the
command; sources that belong to other versions are listed separately and never recommended.*

---

## Contents

- [The problem](#the-problem)
- [How it works](#how-it-works)
- [Screens](#screens)
- [Quick start](#quick-start)
- [A five-minute demo](#a-five-minute-demo)
- [Results](#results)
- [What the system cannot do](#what-the-system-cannot-do)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [Roadmap](#roadmap)
- [Sources and licence](#sources-and-licence)

## The problem

A developer adds a workaround for a platform limitation. Two releases later the platform removes
the limitation. The workaround document is still the best *semantic* match for any question about
that limitation, so a conventional RAG assistant keeps recommending it.

This project started from exactly that experience on a Salesforce implementation: an AI coding
assistant kept proposing a workaround that the platform had made unnecessary. The fix was to read
the release notes by hand. VersionProof AI asks whether a retrieval system can do that step itself.

Vector similarity measures topical closeness, not validity in time:

- The old and the new document are both "about" the feature. The obsolete one often scores higher
  because it shares vocabulary with the question ("limit", "workaround").
- Publication dates do not solve it. A 2023 page can still be correct, and a 2026 page can describe
  a feature that does not exist in the release you run.

## How it works

```mermaid
flowchart LR
  Q[Question + product + target version] --> L[Lexical search<br/>PostgreSQL FTS]
  Q --> S[Semantic search<br/>pgvector]
  L --> F[Reciprocal Rank Fusion]
  S --> F
  F --> C{Applicability<br/>constraint}
  C -- verified, in range --> E[Evidence: applies]
  C -- verified, out of range --> X[Excluded list<br/>explains, never recommends]
  C -- unknown or inferred --> U[Evidence: flagged]
  E --> A{Enough evidence?}
  U --> A
  X --> A
  A -- no --> AB[Abstain]
  A -- yes --> R[Answer + validated citations]
```

| Idea | What it means here |
|---|---|
| **Applicability is metadata with provenance** | Every document revision stores the release range it applies to, marked `verified`, `inferred` or `unknown`. Nothing inferred is stored where a reader would take it as fact. |
| **Version is a constraint, not a ranking bonus** | A revision verified *not* to apply to the target release is removed in SQL. It cannot win by being very similar. |
| **Excluded is not discarded** | Relevant but non-applicable sources come back in a separate list, so the system can say "that exists from 2.135 onward" without recommending it. |
| **Ordering is per product** | `semver`, seasonal names (`Winter '26 < Spring '26`) or an explicit sequence. The core has no Salesforce-specific assumptions. |
| **Identifiers are first-class** | Error codes and API names (`NIMBUS_LIMIT_EXCEEDED_0427`, `Foo.bar()`) are indexed verbatim and weighted above prose. |
| **The verdict never comes from the model** | Abstention, the applies / not-applicable verdict, conflict detection and citation checks are deterministic. The LLM is optional and only writes prose. |
| **Release notes are deltas** | For changelog sources, among applicable entries that cover the question the most recent release leads. This is a heuristic, documented as one. |

## Screens

**Same question, earlier version.** On 2.110.22 the command is deprecated but still present; the
removal note is from the future and moves to the excluded list.

![Same question on an earlier version](docs/images/ask-real-before-removal.png)

**Abstention.** When nothing in the knowledge base covers the question, the system says so.

![Abstaining on a question the corpus does not cover](docs/images/ask-abstain.png)

**Version comparison.** Deterministic, no LLM. A change is `verified` only when the sources support
it; documentation that merely stops applying is reported as `unknown`, never as `removed`.

![Version comparison with side-by-side diff](docs/images/version-comparison.png)

**Evaluation Lab.** Every row is a stored run with its configuration. Nothing is illustrative.

![Evaluation Lab with stored benchmark runs](docs/images/evaluation-lab.png)

**Dashboard and knowledge base.**

![Dashboard](docs/images/dashboard.png)

![Knowledge base with applicability and provenance](docs/images/knowledge-base.png)

## Quick start

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/). No API keys, no
Salesforce credentials.

```bash
git clone https://github.com/lucasoalima/VersionProofAI.git
cd VersionProofAI
docker compose up --build
```

Wait for `Uvicorn running` (backend) and `Ready` (frontend), then open **http://localhost:3000**.

| Service | Address |
|---|---|
| Web app | http://localhost:3000 |
| API (OpenAPI docs at `/docs`) | http://localhost:8000 |
| PostgreSQL | `localhost:5433` (user and password `postgres`) |

Ports 3000 and 8000 must be free. See [Troubleshooting](#troubleshooting) if they are not.

Load the data, in the app under **Knowledge Base** (type the folder name, press *Ingest*):

1. `synthetic`: the fictional Nimbus CRM corpus (12 documents).
2. `real`: the Salesforce CLI release notes snapshot (157 versions).

To use the Evaluation Lab, register the question sets once:

```bash
docker compose exec backend python scripts/seed.py
```

<details>
<summary>Running without Docker</summary>

You need Python 3.12+, Node 22+ and PostgreSQL 16 with the pgvector extension.

```bash
cd backend
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/versionproof
export INGESTION_ROOT=../data EMBEDDING_PROVIDER=hashed
alembic upgrade head && python scripts/seed.py
uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install && npm run dev
```
</details>

## A five-minute demo

1. **Ask Documentation**, product *Salesforce CLI*, version `2.121.7`:
   `Is the org login device command still available?`
   The answer cites the 2.119.8 note that removed the command.
2. Change the version to `2.110.22` and ask again. Now the answer is the 2.103.7 deprecation
   note, and the removal note appears under *Relevant but not applicable*.
3. Product *Nimbus CRM*, version `Spring '25`: `How many scheduled jobs can run concurrently?`
   answers 10. Switch to `Summer '24` and it answers 5. Two documents with the same wording and
   different behaviour, separated only by version.
4. Version `2.150.6`: `How do I configure a Kubernetes ingress for Salesforce CLI?`
   The system abstains.
5. **Version Comparison**, *Nimbus CRM*, `Summer '24` to `Spring '25`: one modified limit with a
   diff, two introductions, and several `unknown` entries that a less careful system would call
   "removed".
6. **Evaluation Lab**: pick a dataset, run *B · traditional RAG* and *C · VersionProof*, compare
   the rows, export JSON or CSV.

## Results

Three engines are compared on the same questions, corpus, retriever and `top_k`:

| | Engine | Version handling |
|---|---|---|
| A | LLM without retrieval | none (requires an LLM; **not run yet**) |
| B | Traditional RAG | retrieves without a version constraint |
| C | VersionProof | constraint, exclusion list, abstention, validated citations |

Measured with hybrid retrieval, `k=5`, extractive answers and the `hashed-bow-v1` embedding.
Reproduce with `python scripts/benchmark_all.py`.

| Dataset | Engine | Outdated source recommended | Citation validity | Applicability accuracy | Correct abstention |
|---|---|---|---|---|---|
| Synthetic held-out (12 q) | B | 0.33 | 0.75 | 0.58 | 0.83 |
| Synthetic held-out (12 q) | **C** | **0.00** | **1.00** | 0.92 | 1.00 |
| Real CLI notes, first run (11 q) | B | 0.43 | 0.91 | 0.82 | 0.91 |
| Real CLI notes, first run (11 q) | **C** | **0.57** | 1.00 | **0.18** | **0.18** |
| Real CLI notes, after two rule changes | **C** | 0.00 | 1.00 | 0.91 | 1.00 |
| Real CLI notes, after changes, *lexical only* | **C** | 0.14 | 1.00 | 0.91 | 1.00 |

**How to read this honestly**

- **The first run on real documentation was a negative result.** The engine tuned on synthetic data
  lost to traditional RAG. Two assumptions broke: "similar titles with different numbers are a
  conflict" (every release note has the same title pattern) and "the product's own name counts as
  topical evidence".
- After fixing those two rules the engine recommends no outdated source on the real set, **but the
  same 11 questions were used to find the fixes**. That row is tuned, not evidence.
- **Retrieval mode matters.** In lexical-only mode the engine still recommends an outdated note for
  one of seven version traps, because the correct note is not retrieved at all. Hybrid is the
  default for that reason.
- One failure is stable across both corpora: a document that merely *mentions* a feature can be
  taken as proof that the feature exists in that version.
- `hashed-bow-v1` is a deterministic bag-of-words embedding, not a semantic model. No real
  embedding model and no LLM have been exercised yet.
- Sample sizes are 11 and 12 questions. Nothing here is a general claim.

Full method, metric definitions and threats to validity:
[docs/evaluation-methodology.md](docs/evaluation-methodology.md).

### Research question

*Does version-aware hybrid retrieval reduce outdated technical recommendations compared with
traditional RAG?* The lab is built so the answer can be "no" or "inconclusive". The current
evidence supports the mechanism on small, author-written sets, and includes one clear negative
run. A held-out set over real documentation is the next required step.

## What the system cannot do

- Establish applicability for documents without verified release metadata. It reports `unknown`.
- Infer that a feature was removed because newer documentation does not mention it.
- Decide which of two conflicting sources is right. It shows both.
- Know when a later release note supersedes an earlier one, beyond the "most recent applicable
  release first" heuristic.
- Guarantee that an answer is correct. Its value is evidence quality, version awareness and
  measurable reliability.

Not implemented: authentication on administrative endpoints, LLM-judged metrics (only a
Ragas-shaped export exists), OpenTelemetry tracing, a cross-encoder reranker, background
ingestion. The complete list is in [docs/limitations.md](docs/limitations.md).

## Configuration

Set in `docker-compose.yml` or the environment (see `.env.example`).

| Variable | Default in Docker | Purpose |
|---|---|---|
| `EMBEDDING_PROVIDER` | `hashed` | `none` (lexical only), `hashed` (offline stand-in), `sentence_transformers` (real model; install with `pip install -e ".[embeddings]"`) |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Must produce 384-dimensional vectors |
| `LLM_PROVIDER` | `none` | `none` gives extractive answers; `anthropic` writes prose from the evidence |
| `LLM_API_KEY`, `LLM_MODEL` | empty | Required when `LLM_PROVIDER` is set |
| `MIN_EVIDENCE_COVERAGE` | `0.5` | Abstention threshold |
| `INGESTION_ROOT` | `../data` | Only files under this directory can be ingested |

After changing the embedding provider, rebuild the vectors with `POST /api/embeddings/build`.

### Importing your own documentation

Put files under `data/` and ingest the folder from **Knowledge Base** or the API:

```bash
curl -X POST localhost:8000/api/ingestion/local \
  -H 'content-type: application/json' -d '{"path":"my-docs"}'
```

Supported: JSON fixtures, Markdown with YAML front matter, plain text with a `.meta.yaml` sidecar
(format examples in `data/synthetic/`). Re-ingesting unchanged content creates nothing; changed
content creates a new revision and keeps the old one. Remote sources must be reviewed and added
to an allowlist first; see [docs/sources.md](docs/sources.md).

## Project layout

```
backend/
  app/ingestion/     loaders, pipeline (revision dedup), URL allowlist
  app/versioning/    ordering strategies, applicability resolution
  app/retrieval/     lexical, semantic, hybrid (RRF), exclusion list
  app/generation/    answer engine, baselines A and B, prompt builder
  app/comparison/    version comparison and timeline
  app/evaluation/    metrics, retrieval and answer benchmark runners
  scripts/           seed, fetch_source, benchmark_*
frontend/            Next.js 15, TypeScript, Tailwind
data/
  synthetic/         fictional Nimbus CRM corpus
  real/              licensed snapshots (Salesforce CLI release notes)
  evaluation/        question sets: synthetic dev, synthetic held-out, real
docs/                design documents
```

Stack: Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL 16 with pgvector and full-text
search, Next.js 15, TypeScript, Tailwind, Docker, GitHub Actions. No orchestration framework:
retrieval and prompting are a few hundred lines of explicit code.

## Testing

```bash
cd backend
pytest -q                              # unit tests; integration tests are skipped, not faked
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/versionproof_test pytest -q
```

102 tests. Integration tests run against a real PostgreSQL with pgvector; CI provisions one on
every push. Create the `versionproof_test` database first if you run them locally.

## Troubleshooting

**`Bind for 127.0.0.1:8000 failed: port is already allocated`** (or 3000). Another project is
using the port. List and stop it, then start again:

```bash
docker ps --format "table {{.Names}}\t{{.Ports}}"
docker stop <container-name>
docker compose up
```

**Backend exits with `failed to resolve host 'db'`.** The containers were created during a failed
start and have a broken network. Recreate them:

```bash
docker compose down
docker compose up
```

**Semantic or hybrid search returns HTTP 501.** `EMBEDDING_PROVIDER` is `none`. Set it to `hashed`
or `sentence_transformers`, restart, and call `POST /api/embeddings/build`.

**The Evaluation Lab has no datasets.** Run `docker compose exec backend python scripts/seed.py`.

**Stopping.** `Ctrl+C` in the terminal, or the stop button in Docker Desktop. `docker compose down
-v` also deletes the database volume.

## Documentation

| Document | Contents |
|---|---|
| [architecture.md](docs/architecture.md) | Components, interfaces, request flow, trade-offs |
| [data-model.md](docs/data-model.md) | Entities, revisions, provenance |
| [versioning-model.md](docs/versioning-model.md) | Ordering strategies, applicability, version comparison |
| [retrieval-design.md](docs/retrieval-design.md) | Lexical indexing, semantic search, RRF, exclusion list |
| [answer-engine.md](docs/answer-engine.md) | Abstention, verdicts, conflicts, citations, prompt-injection boundary |
| [evaluation-methodology.md](docs/evaluation-methodology.md) | Hypothesis, baselines, metrics, all measured results |
| [sources.md](docs/sources.md) | Each documentation source, its licence and the access decision |
| [security.md](docs/security.md) | Security boundaries |
| [limitations.md](docs/limitations.md) | Everything that is missing or unverified |
| [development-guide.md](docs/development-guide.md) | Local setup, migrations, adding sources |
| [AGENTS.md](AGENTS.md) | Rules and status for AI coding agents working on this repository |

## Roadmap

1. A new held-out question set over real documentation, written before touching the engine again.
2. A real embedding model and LLM-written answers; run baseline A.
3. The "mentions X" versus "is about X" failure.
4. Authentication on ingestion and benchmark endpoints.
5. LLM-judged metrics, tracing, a second real documentation source.

## Sources and licence

Code: MIT, see [LICENSE](LICENSE).

`data/real/salesforce-cli/` contains an unmodified snapshot of the Salesforce CLI release notes
from [forcedotcom/cli](https://github.com/forcedotcom/cli), Copyright (c) Salesforce, Inc.,
licensed under Apache-2.0. The licence text and a provenance record (URL, fetch time, SHA-256) are
in that folder. `data/synthetic/` describes **Nimbus CRM, a fictional product**; it is not
Salesforce documentation.

VersionProof AI is an independent portfolio project. It is not affiliated with or endorsed by
Salesforce.
