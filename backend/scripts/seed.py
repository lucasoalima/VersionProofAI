"""Ingest the synthetic corpus and register the synthetic evaluation dataset.

cd backend && python scripts/seed.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.ingestion.pipeline import IngestionPipeline
from app.models import EvaluationDataset

DATA = Path(__file__).resolve().parents[2] / "data"

if __name__ == "__main__":
    with SessionLocal() as db:
        res = IngestionPipeline(db).ingest_path(DATA / "synthetic")
        print("ingestion:", json.dumps(res.as_dict(), indent=2))
        spec = json.loads((DATA / "evaluation" / "synthetic_v1.json").read_text())
        existing = db.scalar(
            select(EvaluationDataset).where(
                EvaluationDataset.name == spec["name"], EvaluationDataset.version == spec["version"]
            )
        )
        if existing is None:
            db.add(
                EvaluationDataset(
                    name=spec["name"],
                    version=spec["version"],
                    description=spec["description"],
                    is_synthetic=spec["is_synthetic"],
                    split=spec["split"],
                    records=spec["records"],
                )
            )
            db.commit()
            print(
                f"registered evaluation dataset {spec['name']} v{spec['version']} ({len(spec['records'])} records)"
            )
        else:
            print("evaluation dataset already registered")
