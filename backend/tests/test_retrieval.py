"""Retrieval strategies against a real (SQLite) database with fake embeddings."""
import json

from sqlalchemy import select

from app import config
from app.db import SessionLocal, utcnow
from app.models import Document, DocumentChunk
from app.services import embeddings, retrieval, vectorstore

PASSAGES = {
    "rent": "The tenant shall pay a monthly rent of rupees eighteen thousand five hundred by the fifth day of every month.",
    "pets": "Keeping pets or animals inside the apartment is strictly prohibited without written consent.",
    "deposit": "A refundable security deposit equal to three months rent is held by the landlord during the lease.",
}


def seed(db, with_vectors=True):
    doc = Document(filename="f.txt", original_filename="lease.txt", content_type="text/plain", size=1,
                   storage_path="x", status="PROCESSED", uploaded_at=utcnow())
    db.add(doc)
    db.flush()
    for i, text in enumerate(PASSAGES.values()):
        vec = embeddings.embed(text)
        db.add(DocumentChunk(document_id=doc.id, chunk_index=i, content=text, vector_id=f"v{i}",
                             vector_json=json.dumps(vec) if with_vectors else None))
        if with_vectors:
            vectorstore.upsert_batch([{"id": f"v{i}", "vector": vec, "text": text, "document_id": doc.id,
                                       "filename": "lease.txt", "chunk_index": i}])
    db.commit()
    return doc


def top(db, question, mode, **kw):
    vec = embeddings.embed(question) if mode != "lexical" else []
    hits = retrieval.retrieve(db, question, vec, kw.get("document_id"), kw.get("limit", 3), mode)
    return [h.chunk.content[:12] for h in hits]


def test_every_mode_finds_the_right_passage(chroma):
    with SessionLocal() as db:
        seed(db)
        for mode in ("lexical", "vector", "hybrid"):
            assert top(db, "monthly rent amount tenant pays", mode)[0].startswith("The tenant"), mode
            assert top(db, "are pets or animals allowed", mode)[0].startswith("Keeping pets"), mode


def test_lexical_returns_nothing_without_term_overlap(chroma):
    with SessionLocal() as db:
        seed(db)
        assert top(db, "quantum chromodynamics lagrangian", "lexical") == []


def test_limit_and_document_scope_are_respected(chroma):
    with SessionLocal() as db:
        doc = seed(db)
        assert len(top(db, "rent deposit pets", "hybrid", limit=2)) == 2
        assert top(db, "rent", "hybrid", document_id=doc.id + 999) == []


def test_hybrid_falls_back_to_keywords_when_embeddings_are_unavailable(chroma):
    with SessionLocal() as db:
        seed(db)
        hits = retrieval.retrieve(db, "monthly rent", [], None, 3, "hybrid")  # empty query vector = embedding failed
        assert hits and hits[0].chunk.content.startswith("The tenant")


def test_vector_mode_falls_back_to_stored_vectors_when_chroma_is_down(chroma, monkeypatch):
    monkeypatch.setattr(vectorstore, "query", lambda *a, **k: [])
    with SessionLocal() as db:
        seed(db)
        assert top(db, "are pets or animals allowed", "vector")[0].startswith("Keeping pets")


def test_chunks_without_vectors_are_still_found_by_hybrid(chroma, monkeypatch):
    monkeypatch.setattr(vectorstore, "query", lambda *a, **k: [])
    with SessionLocal() as db:
        seed(db, with_vectors=False)
        assert top(db, "security deposit three months", "hybrid")[0].startswith("A refundable")


def test_scores_are_reported(chroma):
    with SessionLocal() as db:
        seed(db)
        hits = retrieval.retrieve(db, "monthly rent", embeddings.embed("monthly rent"), None, 3, "hybrid")
        assert all(h.score and h.score > 0 for h in hits)
        assert config.RETRIEVAL_TOP_K >= 1 and db.scalars(select(DocumentChunk)).all()
