# Limitations (honest list, updated per phase)

## Not implemented yet
- A real embedding model was not exercised in the development environment (no model download
  possible); semantic/hybrid were validated with the deterministic `hashed-bow-v1` provider.
- No cross-encoder reranker implementation yet (protocol only).
- No approximate vector index (deliberate; see retrieval-design.md).
- The LLM path was tested only with a scripted fake provider; the Anthropic client has not been
  run against the real API. Baselines A (no retrieval) and B (traditional RAG + generation) and
  Ragas metrics are Phase 5.
- Abstention/verdict rules were tuned on the 10-question dev set. One held-out run (12 q) exists;
  it exposed a known failure: lexical coverage cannot tell a document *about* a feature from one
  that *mentions* it (h03). Not fixed, to keep the held-out split honest.
- Baseline A and Ragas scoring have never been executed; OpenTelemetry and cost accounting are
  not implemented.
- Conflict detection covers numeric disagreement between similarly titled documents only.
- Extractive answers quote the source; they do not synthesise across documents.
- Version comparison is pattern-based (English change verbs, sentence-local) and pairs documents
  by title similarity; `Feature`/`FeatureChange` are not populated (events are computed on read).
  Only current revisions are compared, not historical revisions of the same document.
- LLM baselines (A and B with generation), Ragas metrics, citation validity, abstention rate
  (Phase 5). Retrieval-only benchmarks exist and have been run.
- Real documentation is limited to one source (Salesforce CLI release notes). Platform release
  notes and product docs are not ingested (website terms; see docs/sources.md).
- No real held-out question set: the 11 real questions became a dev set after the first run.
- Release notes are deltas: applicability ranges are open-ended and supersession is approximated by
  "most recent applicable release first", a heuristic.
- The engine has corpus-shape rules (changelog handling, ubiquitous-term threshold of 25% with a
  100-chunk minimum) chosen by judgement, not learned or validated broadly.
- Authentication on administrative endpoints.
- Asynchronous/background ingestion.

- Lexical-only retrieval misses the correct release note for at least one real question and then
  answers from an outdated one (see evaluation-methodology.md). Use hybrid.

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
Phase 1–6 tests (102) were executed against PostgreSQL 16.x + pgvector 0.8.0 built from source;
the Next.js build was executed with Node 22. GitHub Actions and Docker Compose have since been
run successfully by the repository owner. The UI was exercised with a headless browser to
produce the README screenshots.
