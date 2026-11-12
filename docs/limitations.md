# Limitations (honest list, updated per phase)

## Not implemented yet
- Semantic and hybrid retrieval, reranking (Phase 2). The API returns 501 for these modes.
- Answer generation, citations, abstention (Phase 3). The Ask page shows evidence only.
- Version comparison, feature history, timelines (Phase 4). `Feature`/`FeatureChange` exist in
  the schema but are unused.
- Evaluation runs, metrics, exports (Phase 5). The dataset is registered; nothing has been run.
- Real Salesforce documentation (Phase 6). Only the fictional Nimbus CRM corpus exists.
- Authentication on administrative endpoints.
- Asynchronous/background ingestion.

## Inherent to the approach
- Applicability is only as good as the metadata. Documents without verified release ranges are
  reported `unknown`; the system cannot repair missing metadata.
- A missing mention is not evidence of removal; the system will not infer removals.
- Lexical retrieval uses PostgreSQL ranking, not BM25; the relaxed OR fallback can surface weak
  matches (flagged `query_mode: relaxed`).
- The seasonal ordering assumes Winter < Spring < Summer within a label year and three releases
  per year; products with patch releases need the `explicit` scheme.
- Only the current revision of each document is searchable.

## Verified in this environment
Phase 1 tests (46) were executed against PostgreSQL 16.x + pgvector 0.8.0 built from source;
the Next.js build was executed with Node 22. Docker Compose and GitHub Actions configurations
are provided but were not executed here.
