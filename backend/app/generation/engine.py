"""Evidence-based answer engine.

Pipeline (every step before the LLM is deterministic and runs without credentials):
1. Retrieve results + excluded list for the target version.
2. Evidence sufficiency: lexical term coverage of the question by the best result / best
   excluded hit. Below `min_evidence_coverage` on both -> abstain.
3. Verdict: applies / not_applicable / unknown, derived from evidence status, never from the LLM.
4. Conflict detection between near-duplicate sources that state different numbers.
5. Generation: LLM (if configured) or an extractive answer built from the top evidence.
6. Citation validation: every cited chunk id must be one of the supplied *result* chunks.
   Invalid ids are dropped and reported; an LLM answer with no valid citation becomes an abstention.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.generation.interfaces import LLMProvider, LLMUnavailable
from app.generation.prompt import SYSTEM_PROMPT, build_user_prompt
from app.retrieval.interfaces import Evidence, RetrievalFilters, Retriever
from app.retrieval.service import retrieve_with_exclusions
from app.retrieval.tokens import extract_technical_tokens

_NUM = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")
_WORD = re.compile(r"[a-z0-9]+")
_SENT = re.compile(r"(?<=[.!?])\s+")
_RELEASE_LABEL = re.compile(r"\b(?:winter|spring|summer)\s*'?\d{2,4}\b", re.IGNORECASE)


@dataclass
class Answer:
    answer: str
    target_product: str
    target_version: str | None
    applicability_status: str  # applies | not_applicable | unknown
    abstained: bool
    generation_mode: str  # extractive | llm | none
    model_identifier: str | None
    evidence: list[Evidence]
    excluded: list[Evidence]
    citations: list[str]
    warnings: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


# ---- pure helpers (unit-tested) ---------------------------------------------------------


def title_similarity(a: str, b: str) -> float:
    sa, sb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def detect_conflicts(evidence: list[Evidence], min_title_similarity: float = 0.6) -> list[dict]:
    """Two different documents about the same thing (similar titles) that state different
    numbers are reported as a conflict. Deliberately conservative: it flags, it never resolves."""
    conflicts = []
    seen: set[frozenset[str]] = set()
    for i, a in enumerate(evidence):
        for b in evidence[i + 1 :]:
            pair = frozenset({a.document_id, b.document_id})
            if a.document_id == b.document_id or pair in seen:
                continue
            if title_similarity(a.title, b.title) < min_title_similarity:
                continue
            na, nb = set(_NUM.findall(a.excerpt)), set(_NUM.findall(b.excerpt))
            if na and nb and na != nb:
                seen.add(pair)
                conflicts.append(
                    {
                        "chunk_ids": [a.chunk_id, b.chunk_id],
                        "titles": [a.title, b.title],
                        "differing_values": [sorted(na - nb), sorted(nb - na)],
                    }
                )
    return conflicts


def validate_citations(cited: list[str], allowed: set[str]) -> tuple[list[str], list[str]]:
    valid, invalid = [], []
    for c in cited:
        (valid if c in allowed else invalid).append(c)
    return list(dict.fromkeys(valid)), invalid


def parse_llm_json(raw: str) -> dict | None:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def extractive_summary(e: Evidence, max_sentences: int = 2) -> str:
    body = e.excerpt
    if e.heading and body.startswith(e.heading):
        body = body[len(e.heading) :]
    body = re.sub(r"\s+", " ", body).strip()
    return " ".join(_SENT.split(body)[:max_sentences])


# ---- engine ------------------------------------------------------------------------------


class AnswerEngine:
    def __init__(self, db: Session, retriever: Retriever, llm: LLMProvider | None = None):
        self.db = db
        self.retriever = retriever
        self.llm = llm

    TECH_WEIGHT = 3.0

    def _query_terms(self, question: str, target_version: str | None = None) -> dict[str, float]:
        """Question terms with weights: stemmed content words = 1, technical identifiers = 3.
        Release labels are removed first: the target version is a constraint, not topical evidence
        (otherwise every document valid for that release would look relevant)."""
        if target_version:
            question = re.sub(re.escape(target_version), " ", question, flags=re.IGNORECASE)
        question = _RELEASE_LABEL.sub(" ", question)
        lex = (
            self.db.execute(
                text("SELECT tsvector_to_array(to_tsvector('english', :q))"), {"q": question}
            ).scalar()
            or []
        )
        terms = {t: 1.0 for t in lex}
        terms.update({t: self.TECH_WEIGHT for t in extract_technical_tokens(question)})
        return terms

    def _coverage(self, terms: dict[str, float], e: Evidence) -> float:
        """Weighted share of question terms present anywhere in the evidence's *document revision*
        (an answer often spans several chunks of one document)."""
        if not terms:
            return 0.0
        rows = self.db.execute(
            text(
                "SELECT tsvector_to_array(search_vector) FROM document_chunks WHERE revision_id = CAST(:id AS uuid)"
            ),
            {"id": e.revision_id},
        ).scalars()
        lex: set[str] = set()
        for r in rows:
            lex.update(r or [])
        return sum(w for t, w in terms.items() if t in lex) / sum(terms.values())

    def answer(self, question: str, filters: RetrievalFilters, top_k: int = 5) -> Answer:
        t0 = time.perf_counter()
        outcome = retrieve_with_exclusions(self.retriever, question, filters, top_k)
        retrieval_ms = (time.perf_counter() - t0) * 1000
        results, excluded = outcome.results, outcome.excluded
        warnings: list[str] = []
        unresolved: list[str] = []

        terms = self._query_terms(question, filters.target_version)
        cov_results = max((self._coverage(terms, e) for e in results[:3]), default=0.0)
        cov_excluded = max((self._coverage(terms, e) for e in excluded[:3]), default=0.0)
        threshold = settings.min_evidence_coverage
        diagnostics = {
            "retrieval_latency_ms": round(retrieval_ms, 2),
            "coverage_results": round(cov_results, 3),
            "coverage_excluded": round(cov_excluded, 3),
            "min_evidence_coverage": threshold,
            "retrieval_strategy": self.retriever.name,
        }

        def done(**kw) -> Answer:
            diagnostics["end_to_end_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return Answer(
                target_product=filters.product_slug,
                target_version=filters.target_version,
                evidence=results,
                excluded=excluded,
                warnings=warnings,
                unresolved_questions=unresolved,
                diagnostics=diagnostics,
                **kw,
            )

        if not filters.target_version:
            warnings.append("No target version was supplied; applicability cannot be assessed.")
            unresolved.append("Which release are you running?")

        # -- abstention: nothing sufficiently on-topic --------------------------------------
        if cov_results < threshold and cov_excluded < threshold:
            warnings.append(
                "Insufficient evidence: no indexed source covers the question well enough."
            )
            return done(
                answer="The knowledge base does not contain enough evidence to answer this question.",
                applicability_status="unknown",
                abstained=True,
                generation_mode="none",
                model_identifier=None,
                citations=[],
            )

        # -- verdict: results are insufficient and only other-version documentation is on-topic --------------------------
        if cov_results < threshold <= cov_excluded:
            top = excluded[0]
            rng = f"{top.effective_from or 'unknown'} to {top.effective_to or 'later releases'}"
            warnings.append(
                f"Relevant documentation exists only for other releases ({rng}); it is not a recommendation for {filters.target_version}."
            )
            return done(
                answer=(
                    f"Not applicable to {filters.target_version}. The matching documentation "
                    f'("{top.title}") is verified for {rng}. {extractive_summary(top)}'
                ),
                applicability_status="not_applicable",
                abstained=False,
                generation_mode="extractive",
                model_identifier=None,
                citations=[],
            )

        # Evidence that individually covers the question, best-covering first (rank breaks ties).
        scored = sorted(
            ((self._coverage(terms, e), e) for e in results), key=lambda t: (-t[0], t[1].rank)
        )
        usable = [e for c, e in scored if c >= threshold] or [scored[0][1]]
        conflicts = detect_conflicts(usable)
        statuses = {e.applicability_status.value for e in usable}
        if "applies" in statuses:
            verdict = "applies"
        else:
            verdict = "unknown"
            warnings.append(
                "No source with verified applicability to the target version; treat the answer as unverified."
            )
        if conflicts:
            warnings.append("Sources conflict; both are shown and neither is preferred.")
            unresolved.append("Which of the conflicting sources reflects your release?")
        if excluded:
            warnings.append(
                f"{len(excluded)} related source(s) apply only to other releases and were excluded from the answer."
            )

        allowed = {e.chunk_id for e in results}

        # -- LLM generation (optional) ------------------------------------------------------
        if self.llm is not None:
            try:
                raw = self.llm.complete(
                    SYSTEM_PROMPT,
                    build_user_prompt(
                        question,
                        filters.product_slug,
                        filters.target_version,
                        usable,
                        excluded,
                        warnings,
                    ),
                )
            except LLMUnavailable as exc:
                warnings.append(f"LLM unavailable ({exc}); falling back to an extractive answer.")
                raw = None
            if raw is not None:
                obj = parse_llm_json(raw)
                if obj is None:
                    warnings.append(
                        "LLM output was not valid JSON; falling back to an extractive answer."
                    )
                else:
                    valid, invalid = validate_citations(
                        [str(c) for c in obj.get("citations", [])], allowed
                    )
                    if invalid:
                        warnings.append(
                            f"{len(invalid)} citation(s) did not match supplied evidence and were removed."
                        )
                    diagnostics["invalid_citations"] = invalid
                    unresolved += [str(q) for q in obj.get("unresolved_questions", [])][:5]
                    if obj.get("abstain"):
                        return done(
                            answer=str(obj.get("answer") or "Insufficient evidence."),
                            applicability_status="unknown",
                            abstained=True,
                            generation_mode="llm",
                            model_identifier=self.llm.model_id,
                            citations=valid,
                            conflicts=conflicts,
                        )
                    if not valid:
                        warnings.append(
                            "LLM answer had no valid citation and was discarded as ungrounded."
                        )
                        return done(
                            answer="No grounded answer could be produced from the available evidence.",
                            applicability_status="unknown",
                            abstained=True,
                            generation_mode="llm",
                            model_identifier=self.llm.model_id,
                            citations=[],
                            conflicts=conflicts,
                        )
                    return done(
                        answer=str(obj.get("answer", "")),
                        applicability_status=verdict,
                        abstained=False,
                        generation_mode="llm",
                        model_identifier=self.llm.model_id,
                        citations=valid,
                        conflicts=conflicts,
                    )

        # -- extractive answer (no LLM) -----------------------------------------------------
        if conflicts:
            a, b = conflicts[0]["titles"]
            body = f'Sources disagree and their applicability to {filters.target_version or "your release"} is not established: "{a}" vs "{b}".'
            cited = conflicts[0]["chunk_ids"]
            return done(
                answer=body,
                applicability_status="unknown",
                abstained=True,
                generation_mode="extractive",
                model_identifier=None,
                citations=cited,
                conflicts=conflicts,
            )
        top = usable[0]
        prefix = {
            "applies": f"For {filters.target_version}: ",
            "unknown": "Unverified for the target version: ",
        }[verdict]
        return done(
            answer=prefix + extractive_summary(top) + f" [{top.title}]",
            applicability_status=verdict,
            abstained=False,
            generation_mode="extractive",
            model_identifier=None,
            citations=[top.chunk_id],
            conflicts=conflicts,
        )
