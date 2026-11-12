# Limitations (honest list, updated per phase)

## Not implemented yet
- A real embedding model was not exercised in the development environment (no model download
  possible); semantic/hybrid were validated with the deterministic `hashed-bow-v1` provider.
- No cross-encoder reranker implementation yet (protocol only).
- No approximate vector index (deliberate; see retrieval-design.md).
- The LLM path was tested only with a scripted fake provider; the Anthropic client has not been
  run against the real API. Baselines A (no retrieval) and B (traditional RAG + generation) and
  Ragas metrics are Phase 5.
- Abstention/verdict thresholds were tuned on the 10-question dev set; no held-out validation.
- Conflict detection covers numeric disagreement between similarly titled documents only.
- Extractive answers quote the source; they do not synthesise across documents.
- Version comparison is pattern-based (English change verbs, sentence-local) and pairs documents
  by title similarity; `Feature`/`FeatureChange` are not populated (events are computed on read).
  Only current revisions are compared, not historical revisions of the same document.
- LLM baselines (A and B with generation), Ragas metrics, citation validity, abstention rate
  (Phase 5). Retrieval-only benchmarks exist and have been run.
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
- Retrieval never returns an empty list for a nonsense question in semantic/hybrid mode
  (cosine always ranks something); abstention requires a relevance threshold (Phase 3).
- The constrained path issues two queries to build the excluded list; latency roughly doubles.

## Verified in this environment
Phase 1–4 tests (82) were executed against PostgreSQL 16.x + pgvector 0.8.0 built from source;
the Next.js build was executed with Node 22. Docker Compose and GitHub Actions configurations
are provided but were not executed here.
