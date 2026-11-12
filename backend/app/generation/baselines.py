"""Comparison baselines for the Evaluation Lab. They share the Answer model with AnswerEngine.

A. NoRetrievalEngine    - the LLM answers from internal knowledge. Requires an LLM.
B. TraditionalRagEngine - retrieves WITHOUT a version constraint and answers from the top
   results. No applicability verdict, no coverage-based abstention, no exclusion list: this is
   what a conventional RAG pipeline does. Because it presents its answer as valid for the
   question asked, its verdict is recorded as "applies" whenever it answers.
"""

from __future__ import annotations

import time
from dataclasses import replace

from sqlalchemy.orm import Session

from app.generation.engine import Answer, extractive_summary, parse_llm_json, validate_citations
from app.generation.interfaces import LLMProvider, LLMUnavailable
from app.generation.prompt import SYSTEM_PROMPT, build_user_prompt
from app.retrieval.interfaces import RetrievalFilters, Retriever

NO_RETRIEVAL_SYSTEM = (
    "You are a technical assistant. Answer the question for the stated product and version from your "
    'own knowledge. Respond with one JSON object: {"answer": str, "abstain": bool}. Set abstain to '
    "true if you do not know."
)


class TraditionalRagEngine:
    label = "traditional_rag"

    def __init__(self, db: Session, retriever: Retriever, llm: LLMProvider | None = None):
        self.db, self.retriever, self.llm = db, retriever, llm

    def answer(self, question: str, filters: RetrievalFilters, top_k: int = 5) -> Answer:
        t0 = time.perf_counter()
        results = self.retriever.retrieve(question, replace(filters, enforce_version=False), top_k)
        diag = {
            "retrieval_latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "retrieval_strategy": self.retriever.name,
        }
        common = dict(
            target_product=filters.product_slug,
            target_version=filters.target_version,
            evidence=results,
            excluded=[],
            diagnostics=diag,
        )

        def done(**kw) -> Answer:
            diag["end_to_end_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return Answer(**common, **kw)

        if not results:
            return done(
                answer="No documents were retrieved.",
                applicability_status="unknown",
                abstained=True,
                generation_mode="none",
                model_identifier=None,
                citations=[],
            )
        if self.llm is not None:
            try:
                obj = parse_llm_json(
                    self.llm.complete(
                        SYSTEM_PROMPT,
                        build_user_prompt(
                            question, filters.product_slug, filters.target_version, results, [], []
                        ),
                    )
                )
            except LLMUnavailable:
                obj = None
            if obj is not None:
                valid, invalid = validate_citations(
                    [str(c) for c in obj.get("citations", [])], {e.chunk_id for e in results}
                )
                diag["invalid_citations"] = invalid
                abstained = bool(obj.get("abstain"))
                return done(
                    answer=str(obj.get("answer", "")),
                    applicability_status="unknown" if abstained else "applies",
                    abstained=abstained,
                    generation_mode="llm",
                    model_identifier=self.llm.model_id,
                    citations=valid,
                )
        top = results[0]
        return done(
            answer=extractive_summary(top) + f" [{top.title}]",
            applicability_status="applies",
            abstained=False,
            generation_mode="extractive",
            model_identifier=None,
            citations=[top.chunk_id],
        )


class NoRetrievalEngine:
    label = "no_retrieval"
    retriever = None

    def __init__(self, llm: LLMProvider):
        if llm is None:
            raise LLMUnavailable(
                "Baseline A (LLM without retrieval) requires a configured LLM provider."
            )
        self.llm = llm

    def answer(self, question: str, filters: RetrievalFilters, top_k: int = 5) -> Answer:
        t0 = time.perf_counter()
        user = f"Product: {filters.product_slug}\nTarget version: {filters.target_version or 'not specified'}\nQuestion: {question}"
        obj = parse_llm_json(self.llm.complete(NO_RETRIEVAL_SYSTEM, user)) or {}
        abstained = bool(obj.get("abstain")) or not obj.get("answer")
        return Answer(
            answer=str(obj.get("answer", "")),
            target_product=filters.product_slug,
            target_version=filters.target_version,
            applicability_status="unknown" if abstained else "applies",
            abstained=abstained,
            generation_mode="llm",
            model_identifier=self.llm.model_id,
            evidence=[],
            excluded=[],
            citations=[],
            warnings=["Answer produced without retrieval; no evidence or citations exist."],
            diagnostics={
                "end_to_end_latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "retrieval_strategy": "none",
            },
        )
