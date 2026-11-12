import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
log = get_logger("versionproof.http")

app = FastAPI(
    title="VersionProof AI",
    version="0.1.0",
    description="Version-aware documentation retrieval. Phase 2: ingestion + lexical, semantic and hybrid (RRF) retrieval + retrieval benchmarks.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.app_env != "production" else [],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Structured access log with a request id and latency. No bodies, headers or secrets."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = round((time.perf_counter() - t0) * 1000, 2)
    log.info(
        "http_request",
        request_id=rid,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=ms,
    )
    response.headers["x-request-id"] = rid
    response.headers["server-timing"] = f"app;dur={ms}"
    return response


app.include_router(router)
