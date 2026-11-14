"""Test harness: SQLite instead of PostgreSQL, and fakes for every external service
(Ollama, ChromaDB, Apache Tika), so the whole suite runs offline in a few seconds."""
from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

# Environment must be set BEFORE the app package is imported (config reads it at import time).
_TMP = Path(tempfile.mkdtemp(prefix="doclock-tests-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
    "DOCLOCK_USERNAME": "tester",
    "DOCLOCK_PASSWORD": "correct-horse-battery",
    "DOCLOCK_JWT_SECRET": "x" * 48,
    "DOCLOCK_STORAGE_DIR": str(_TMP / "storage"),
    "DOCLOCK_LOGIN_MAX_ATTEMPTS": "5",
    "DOCLOCK_LLM_FACTS": "false",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import login_limiter  # noqa: E402
from app.services import embeddings, extraction, llm, vectorstore  # noqa: E402

DIM = 128


def fake_vector(text: str) -> list[float]:
    """Deterministic bag-of-words hashing vector: similar wording -> similar vectors (good enough for tests)."""
    vec = [0.0] * DIM
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % DIM] += 1.0
    return vec


class FakeChroma:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def upsert_batch(self, items):
        for i in items:
            self.rows[i["id"]] = i
        return True

    def query(self, vector, document_id, limit):
        from app.services.ranking import cosine
        scored = [(cosine(vector, r["vector"]), vid) for vid, r in self.rows.items()
                  if document_id is None or r["document_id"] == document_id]
        scored.sort(reverse=True)
        return [vid for s, vid in scored[:limit] if s > 0]

    def delete(self, ids):
        for i in ids:
            self.rows.pop(i, None)


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """Clean DB + storage + fakes for every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    for f in config.STORAGE_DIR.glob("*"):
        f.unlink()
    login_limiter.reset()

    chroma = FakeChroma()
    monkeypatch.setattr(embeddings, "embed_batch", lambda texts: [fake_vector(t) if t.strip() else [] for t in texts])
    monkeypatch.setattr(embeddings, "embed", lambda text: fake_vector(text) if text.strip() else [])
    monkeypatch.setattr(vectorstore, "upsert_batch", chroma.upsert_batch)
    monkeypatch.setattr(vectorstore, "query", chroma.query)
    monkeypatch.setattr(vectorstore, "delete", chroma.delete)
    monkeypatch.setattr(extraction, "extract_text", lambda path: Path(path).read_text(encoding="utf-8"))
    monkeypatch.setattr(llm, "generate_answer", lambda question, context, history: f"ANSWER based on: {context[:60]}")
    yield chroma


@pytest.fixture()
def chroma(fresh_state):
    return fresh_state


@pytest.fixture()
def client():
    with TestClient(app) as c:  # context manager runs the lifespan (create tables, recover interrupted docs)
        yield c


@pytest.fixture()
def auth(client):
    r = client.post("/api/auth/login", json={"username": "tester", "password": "correct-horse-battery"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def upload(client, auth, name: str, text: str, content_type: str = "text/plain"):
    return client.post("/api/documents", headers=auth, files={"file": (name, text.encode("utf-8"), content_type)})
