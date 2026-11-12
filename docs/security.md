# Security boundaries

## Implemented in Phase 1
- **Local ingestion is confined to `INGESTION_ROOT`.** `resolve_within_root` resolves symlinks
  and rejects traversal and absolute paths (403). Tested.
- **Resource limits.** `max_document_bytes`, `max_documents_per_job`; oversized files are recorded
  as failures.
- **Loader validation.** Unknown provenance values and missing required metadata are rejected per
  document; one bad document never fails the whole job silently.
- **No secrets in responses.** `capabilities()` reports provider *names*, never keys.
- **CORS** restricted to the frontend origin in non-production.
- **Fail loudly.** `/api/health` returns 503 without a database; semantic mode returns 501 without
  an embedding provider.

## Planned
- **Remote URLs (Phase 6):** scheme/host allowlist, DNS resolution check against private ranges,
  redirect limits, size/time limits, robots and terms review per source.
- **Prompt injection (Phase 3):** retrieved text is data; it is placed in a delimited user-turn
  block, never in the system prompt; the model is instructed to cite only supplied chunk ids and
  citations are validated against the database before display.
- **Output sanitisation:** answers rendered as text, never as HTML.
- **Admin auth:** ingestion and evaluation endpoints behind an API key/role before any
  non-local deployment.

The platform does not guarantee correctness of answers; its value is evidence quality,
version awareness and measurable reliability.
