"""Answer-level benchmark (extractive unless LLM_PROVIDER is configured).

EMBEDDING_PROVIDER=hashed python scripts/benchmark_answers.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.embeddings.providers import get_embedding_provider
from app.evaluation.answer_runner import run_answer_benchmark
from app.generation.engine import AnswerEngine
from app.generation.providers import get_llm_provider
from app.models import EvaluationDataset
from app.retrieval.factory import build_retriever

if __name__ == "__main__":
    with SessionLocal() as db:
        ds = db.scalar(select(EvaluationDataset).order_by(EvaluationDataset.created_at))
        if ds is None:
            sys.exit("no dataset registered; run scripts/seed.py")
        llm = get_llm_provider()
        modes = ["lexical"] + (["semantic", "hybrid"] if get_embedding_provider() else [])
        print(
            f"dataset={ds.name}:{ds.version} generation={'llm:' + llm.model_id if llm else 'extractive'}"
        )
        for mode in modes:
            run = run_answer_benchmark(db, ds, AnswerEngine(db, build_retriever(db, mode), llm))
            print(f"{run.strategy:32}", {k: v for k, v in run.metrics.items() if k != "questions"})
            for q in run.per_question:
                if not (q["abstention_correct"] and q["applicability_correct"]):
                    print(
                        f"   miss {q['id']} case{q['case']}: verdict={q['verdict']} expected={q['expected']} abstained={q['abstained']} should={q['should_abstain']}"
                    )
