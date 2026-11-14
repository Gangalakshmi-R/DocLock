"""DocLock API entry point.

Layout:  config -> db/models -> services (chunking, ranking, retrieval, facts, ingestion ...) -> routers -> app
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config, models  # noqa: F401  (models import registers the tables on Base.metadata)
from app.db import Base, engine
from app.routers import alerts, auth, chat, documents, privacy
from app.services import ingestion


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)  # create missing tables; existing v1 databases keep working unchanged
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    recovered = ingestion.recover_interrupted()
    if recovered:
        print(f"Marked {recovered} interrupted document(s) as FAILED after restart.")
    yield


app = FastAPI(title="DocLock API", version="3.0.0", description="Personal document intelligence: RAG, facts and deadline alerts",
              lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(alerts.router)
app.include_router(privacy.router)


@app.get("/actuator/health")
@app.get("/health")
def health():
    return {"status": "UP", "service": "doclock-python-api"}


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"message": detail}, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return JSONResponse(status_code=422, content={"message": f"Invalid request: {where} {first.get('msg', '')}".strip()})
