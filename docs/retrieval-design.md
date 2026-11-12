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

## Phase 2: semantic and hybrid retrieval

### Embeddings
`EmbeddingProvider` protocol (`embed(texts) -> vectors`, `model_id`, `dimensions`). Providers:
`sentence_transformers` (default model `all-MiniLM-L6-v2`, 384-d, normalised) and `hashed`
(`hashed-bow-v1`: a deterministic hashed bag-of-words + character 3-grams used for tests and
offline work; it measures lexical overlap, not meaning, and is labelled as such on every run).
`build_embeddings()` is idempotent per `model_id`; chunks embedded by a different model are
re-embedded, and `SemanticRetriever` only considers chunks whose `embedding_model` matches the
active provider, so two vector spaces are never mixed.

### Semantic search
Exact cosine nearest-neighbour (`embedding <=> query`) with a sequential scan. No HNSW/IVFFlat
index yet: on the synthetic corpus p50 latency is single-digit milliseconds, and an approximate
index would trade recall for nothing. The decision is revisited with measurements on a real
corpus.

### Hybrid search
Reciprocal Rank Fusion: `score(d) = Σ_i 1/(60 + rank_i(d))` over the lexical and semantic
lists, each asked for `3 × top_k` candidates. Diagnostics carry `component_ranks` per result.
An optional `Reranker` protocol re-orders the fused list and never adds candidates.

### Shared constraint
All three strategies build their SQL through `retrieval/base.py`, so category, date, trust and
version filters are applied identically. Fusion therefore cannot resurrect an excluded revision.

### The exclusion list
Excluding verified-not-applicable revisions is right for recommendations and wrong for
explanations: "can I use `@AsyncTrigger` on Winter '25?" needs the Spring '25 document to say
*no, introduced later*. `retrieval/service.py` therefore returns `results` (constrained) plus
`excluded` (up to 3 relevant hits verified NOT applicable to the target), computed by a second,
unconstrained pass. The two lists never merge; the API and the evaluation runner carry both.
Cost: the constrained path runs two queries (p50 roughly doubles on the synthetic corpus).
