# Development guide

## Prerequisites
Python 3.12+, Node 22+, PostgreSQL 16 with pgvector (or Docker).

## Backend
```bash
cd backend
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/versionproof
alembic upgrade head
python scripts/seed.py            # synthetic corpus + evaluation dataset
uvicorn app.main:app --reload
```
Tests: `pytest -q` (unit) · `TEST_DATABASE_URL=... pytest -q` (unit + integration).
The integration fixture downgrades to base and upgrades to head once per session, then
truncates all tables per test. Lint/format: `ruff check app tests && ruff format app tests`.

## Frontend
```bash
cd frontend && npm install && npm run dev   # NEXT_PUBLIC_API_URL defaults to http://localhost:8000
```
Server components fetch through `API_INTERNAL_URL` (docker network); client components through
`NEXT_PUBLIC_API_URL`.

## Adding a product or documents
Write a JSON fixture (see `data/synthetic/nimbus-crm/nimbus-docs.json`) or Markdown files with
front matter. Required fields: `product`, `external_id`, `title`. Register releases once per
fixture under `releases`; refer to them by label in `effective_from`/`effective_to`.

## Migrations
`alembic revision --autogenerate -m "..."` then review: add `CREATE EXTENSION IF NOT EXISTS
vector` for fresh databases and `DROP TYPE` statements for enums in `downgrade()`.
