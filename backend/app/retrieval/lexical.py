"""Lexical retrieval over PostgreSQL full-text search.

Query construction mirrors indexing: `websearch_to_tsquery('english', q)` OR-ed with the
verbatim technical tokens extracted from the query. The strict (AND) form runs first; if it
yields nothing, a relaxed (OR) form runs so that paraphrased questions still surface
candidates. `diagnostics.query_mode` records which one produced the results.

Ranking: ts_rank_cd with normalisation 32 (rank/(rank+1)); title and technical identifiers are
weight A, body text weight B, so an exact identifier hit outranks a stemmed body match.
"""

from __future__ import annotations

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.retrieval.base import base_statement, load_product, row_to_evidence, target_sequence
from app.retrieval.interfaces import Evidence, RetrievalFilters
from app.retrieval.tokens import extract_technical_tokens, technical_tsquery_literal


class LexicalRetriever:
    name = "lexical"

    def __init__(self, db: Session):
        self.db = db

    def _tsquery_texts(self, query: str, tokens: list[str]) -> tuple[str, str]:
        strict = (
            self.db.execute(
                text("SELECT websearch_to_tsquery('english', :q)::text"), {"q": query}
            ).scalar()
            or ""
        )
        relaxed = strict.replace(" & ", " | ")
        tech = technical_tsquery_literal(tokens)
        if tech:
            strict = f"({strict}) | {tech}" if strict else tech
            relaxed = f"({relaxed}) | {tech}" if relaxed else tech
        return strict, relaxed

    def retrieve(self, query: str, filters: RetrievalFilters, top_k: int) -> list[Evidence]:
        product = load_product(self.db, filters.product_slug)
        target_seq = target_sequence(self.db, product, filters.target_version)
        tokens = extract_technical_tokens(query)
        strict, relaxed = self._tsquery_texts(query, tokens)
        if not strict:
            return []
        rows, mode = self._run(strict, product, filters, target_seq, top_k), "strict"
        if not rows and relaxed != strict:
            rows, mode = self._run(relaxed, product, filters, target_seq, top_k), "relaxed"
        diag = {"technical_tokens_in_query": tokens, "query_mode": mode}
        return [row_to_evidence(r, i, target_seq, self.name, diag) for i, r in enumerate(rows, 1)]

    def _run(self, tsq_text: str, product, filters, target_seq, top_k):
        tsq = func.cast(tsq_text, TSQUERY)
        rank = func.ts_rank_cd(DocumentChunk.search_vector, tsq, 32)
        stmt = (
            base_statement(rank, product, filters, target_seq)
            .where(DocumentChunk.search_vector.op("@@")(tsq))
            .order_by(rank.desc(), Document.title, DocumentChunk.ordinal)
            .limit(top_k)
        )
        return list(self.db.execute(stmt))
