# Retrieval design

## Phase 1: lexical retrieval

### Indexing
Each chunk's `search_vector` is:

```
setweight(to_tsvector('english', chunk_text), 'B')
|| setweight(to_tsvector('english', document_title), 'A')
|| '<technical tokens as a positional tsvector literal with weight A>'
```

Why the third term: PostgreSQL's parser splits `NIMBUS_LIMIT_EXCEEDED_0427` into
`nimbus`, `limit`, `exceeded`, `0427` and stems ordinary words. We extract identifiers
(ERROR_CODES, `Dotted.Names`, snake_case, camelCase, PascalCase, `v2.1`, `Spring '25`) with
regexes (`retrieval/tokens.py`), lower-case them, and write them as `'token':<pos>A`.
`array_to_tsvector` was tried first and rejected: it emits lexemes without positions, which
`ts_rank_cd` scores as zero — the identifier hits were not ranking at all.

### Querying
1. `websearch_to_tsquery('english', q)` (AND semantics) OR-ed with the technical tokens found in
   the query. This is the *strict* form.
2. If it matches nothing, the *relaxed* form (AND → OR) runs. Results carry
   `diagnostics.query_mode = "relaxed"` so downstream components treat them as weak evidence.
3. Rank with `ts_rank_cd(vector, query, 32)` (cover density, normalised to 0–1). Weight A terms
   (title, identifiers) outrank weight B (prose).

### Version filtering is a constraint
```sql
WHERE (revision.applicability_provenance <> 'verified')
   OR ( (from_rel.sequence IS NULL OR from_rel.sequence <= :target)
    AND (to_rel.sequence   IS NULL OR to_rel.sequence   >= :target) )
```
Verified-out-of-range revisions are **excluded**. Unknown/inferred ones are kept and labelled.
`enforce_version=false` disables the exclusion (used by the traditional-RAG baseline in Phase 5)
but still labels every result, so the evaluation can count outdated recommendations.

Only each document's **current revision** is searchable. Historical revisions are retained for
provenance and for the Phase 4 comparison engine.

### Evidence contract
Every result returns: title, source URL, applicability range (labels), applicability status and
provenance, chunk id, revision id, score, rank, trust level, publication date, strategy name and
diagnostics. This contract is shared by all retrievers so Phase 2/3 can fuse and cite uniformly.

## Phase 2 (planned)
- `EmbeddingProvider` protocol; default `sentence-transformers/all-MiniLM-L6-v2` (384-d) to match
  the `vector(384)` column; exact `<=>` cosine search first, HNSW only after measurement.
- Hybrid: Reciprocal Rank Fusion `score = Σ 1/(k + rank_i)`, k=60, over the two ranked lists.
- Optional cross-encoder reranking behind a `Reranker` protocol.
- Version constraint applied identically to all strategies.
