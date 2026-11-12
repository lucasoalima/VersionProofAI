from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(
    title="VersionProof AI",
    version="0.1.0",
    description="Version-aware documentation retrieval. Phase 1: ingestion + lexical retrieval.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.app_env != "production" else [],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
