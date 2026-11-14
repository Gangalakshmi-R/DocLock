"""End-to-end API tests: upload -> background ingestion -> facts/alerts -> retrieval -> chat -> delete."""
import json
from datetime import date, timedelta

import pytest
import requests
from sqlalchemy import select

from app import config
from app.db import SessionLocal
from app.models import Document, DocumentAlert, DocumentChunk, DocumentFact
from app.services import embeddings, extraction, ingestion, llm

from conftest import upload

SOON = date.today() + timedelta(days=10)
LATER = date.today() + timedelta(days=200)
POLICY = (
    "Health Insurance Policy\n\n"
    f"Policy expiry date: {SOON.strftime('%d %B %Y')}\n"
    f"Premium renewal date: {LATER.isoformat()}\n"
    "Annual premium: ₹14,850\n\n"
    "Waiting period for pre-existing diseases is 24 months. Pets are not covered.\n"
)


def wait_processed(client, auth, doc_id):
    # TestClient runs BackgroundTasks before returning, so this normally succeeds on the first read.
    doc = client.get(f"/api/documents/{doc_id}", headers=auth).json()
    assert doc["status"] == "PROCESSED", doc
    return doc


def test_upload_returns_202_and_the_document_is_processed_in_the_background(client, auth):
    r = upload(client, auth, "policy.txt", POLICY)
    assert r.status_code == 202
    assert r.json()["status"] == "QUEUED"
    doc = wait_processed(client, auth, r.json()["id"])
    assert doc["processedAt"] and doc["errorMessage"] is None
    assert client.get(f"/api/documents/{doc['id']}/content", headers=auth).json()["content"].startswith("Health Insurance")


def test_ingestion_creates_chunks_facts_and_alerts(client, auth, chroma):
    doc_id = upload(client, auth, "policy.txt", POLICY).json()["id"]
    wait_processed(client, auth, doc_id)

    with SessionLocal() as db:
        assert db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc_id)).all()
        assert db.scalars(select(DocumentFact).where(DocumentFact.document_id == doc_id)).all()
    assert chroma.rows  # vectors were upserted

    facts = client.get(f"/api/documents/{doc_id}/facts", headers=auth).json()["facts"]
    names = {(f["type"], f["name"]) for f in facts}
    assert ("DATE", "policy_expiry_date") in names and ("AMOUNT", "annual_premium") in names

    body = client.get("/api/alerts", headers=auth).json()
    kinds = {a["type"]: a for a in body["alerts"]}
    assert set(kinds) == {"EXPIRY", "RENEWAL"}
    assert kinds["EXPIRY"]["status"] == "DUE_SOON" and kinds["EXPIRY"]["daysLeft"] == 10
    assert kinds["RENEWAL"]["status"] == "UPCOMING"
    assert kinds["EXPIRY"]["filename"] == "policy.txt"
    assert body["summary"] == {"overdue": 0, "dueSoon": 1, "upcoming": 1}
    assert [a["deadline"] for a in body["alerts"]] == sorted(a["deadline"] for a in body["alerts"])


def test_alert_acknowledge_and_filters(client, auth):
    doc_id = upload(client, auth, "policy.txt", POLICY).json()["id"]
    alerts = client.get("/api/alerts", headers=auth).json()["alerts"]
    expiry = next(a for a in alerts if a["type"] == "EXPIRY")

    r = client.patch(f"/api/alerts/{expiry['id']}", headers=auth, json={"acknowledged": True})
    assert r.status_code == 200 and r.json()["acknowledged"] is True
    assert [a["type"] for a in client.get("/api/alerts", headers=auth).json()["alerts"]] == ["RENEWAL"]
    assert len(client.get("/api/alerts?includeAcknowledged=true", headers=auth).json()["alerts"]) == 2
    assert client.get("/api/alerts?withinDays=30&includeAcknowledged=true", headers=auth).json()["summary"]["dueSoon"] == 1
    assert len(client.get("/api/alerts?withinDays=30&includeAcknowledged=true", headers=auth).json()["alerts"]) == 1
    assert client.patch("/api/alerts/99999", headers=auth, json={"acknowledged": True}).status_code == 404
    assert doc_id


def test_duplicate_upload_is_rejected_but_a_failed_one_may_be_retried(client, auth):
    first = upload(client, auth, "a.txt", POLICY)
    assert first.status_code == 202
    dup = upload(client, auth, "copy-of-a.txt", POLICY)
    assert dup.status_code == 409 and "already uploaded" in dup.json()["message"]

    with SessionLocal() as db:  # mark the first as FAILED -> the same bytes may be uploaded again
        db.get(Document, first.json()["id"]).status = "FAILED"
        db.commit()
    assert upload(client, auth, "a-again.txt", POLICY).status_code == 202


@pytest.mark.parametrize("name,data,status", [("virus.exe", b"MZ", 400), ("empty.txt", b"", 400), ("big.txt", b"x" * 60, 413)])
def test_upload_validation(client, auth, monkeypatch, name, data, status):
    monkeypatch.setattr(config, "MAX_FILE_SIZE", 50)
    r = client.post("/api/documents", headers=auth, files={"file": (name, data, "text/plain")})
    assert r.status_code == status


def test_path_traversal_in_filename_is_neutralised(client, auth):
    r = upload(client, auth, "../../etc/passwd.txt", "hello")
    assert r.status_code == 202
    assert r.json()["originalFilename"] == "passwd.txt"
    assert ".." not in r.json()["filename"] and "/" not in r.json()["filename"]


def test_extraction_failure_marks_document_failed_and_cleans_up(client, auth, monkeypatch):
    def boom(path):
        raise RuntimeError("Apache Tika extraction failed: connection refused")
    monkeypatch.setattr(extraction, "extract_text", boom)
    doc = client.get(f"/api/documents/{upload(client, auth, 'x.txt', 'abc').json()['id']}", headers=auth).json()
    assert doc["status"] == "FAILED" and "Tika" in doc["errorMessage"]
    with SessionLocal() as db:
        assert db.scalars(select(DocumentChunk)).all() == []


def test_embedding_outage_still_indexes_for_keyword_search(client, auth, monkeypatch):
    monkeypatch.setattr(embeddings, "embed_batch", lambda texts: [[] for _ in texts])
    monkeypatch.setattr(embeddings, "embed", lambda text: [])
    doc_id = upload(client, auth, "policy.txt", POLICY).json()["id"]
    doc = client.get(f"/api/documents/{doc_id}", headers=auth).json()
    assert doc["status"] == "PROCESSED" and "keywords only" in doc["errorMessage"]
    hits = client.post("/api/retrieve", headers=auth, json={"question": "waiting period pre-existing diseases", "mode": "hybrid"}).json()
    assert hits["results"] and "24 months" in hits["results"][0]["content"]


def test_empty_text_document_is_flagged(client, auth):
    doc_id = upload(client, auth, "blank.txt", "   \n  ").json()["id"]
    doc = client.get(f"/api/documents/{doc_id}", headers=auth).json()
    assert doc["status"] == "PROCESSED" and "No readable text" in doc["errorMessage"]


def test_analysis_failure_does_not_fail_the_document(client, auth, monkeypatch):
    monkeypatch.setattr(ingestion.facts, "extract_facts", lambda text: (_ for _ in ()).throw(RuntimeError("bug")))
    doc_id = upload(client, auth, "policy.txt", POLICY).json()["id"]
    assert wait_processed(client, auth, doc_id)["status"] == "PROCESSED"


def test_interrupted_documents_are_recovered_on_startup(client, auth):
    from app.db import utcnow
    with SessionLocal() as db:
        db.add(Document(filename="s", original_filename="stuck.txt", content_type="text/plain", size=1,
                        storage_path="x", status="INDEXING", uploaded_at=utcnow()))
        db.commit()
    assert ingestion.recover_interrupted() == 1
    with SessionLocal() as db:
        stuck = db.scalars(select(Document).where(Document.original_filename == "stuck.txt")).one()
        assert stuck.status == "FAILED" and "restart" in stuck.error_message


# ---------------------------------------------------------------------------- retrieval + chat
def test_retrieve_endpoint_supports_all_modes(client, auth):
    upload(client, auth, "policy.txt", POLICY)
    upload(client, auth, "lease.txt", "The tenant pays monthly rent of eighteen thousand five hundred rupees.")
    for mode in ("hybrid", "vector", "lexical"):
        r = client.post("/api/retrieve", headers=auth, json={"question": "monthly rent the tenant pays", "mode": mode, "limit": 2})
        assert r.status_code == 200 and r.json()["mode"] == mode
        assert r.json()["results"][0]["filename"] == "lease.txt", mode
    assert client.post("/api/retrieve", headers=auth, json={"question": "x", "mode": "bogus"}).status_code == 422


def test_chat_returns_answer_with_citations_and_saves_history(client, auth):
    upload(client, auth, "policy.txt", POLICY)
    r = client.post("/api/chat", headers=auth, json={"message": "What is the waiting period for pre-existing diseases?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("ANSWER based on:") and body["retrievalMode"] == config.DEFAULT_RETRIEVAL_MODE
    cite = body["citations"][0]
    assert cite["filename"] == "policy.txt" and cite["chunk"] == 1 and "snippet" in cite

    second = client.post("/api/chat", headers=auth, json={"message": "And the premium?", "conversationId": body["conversationId"]}).json()
    assert second["conversationId"] == body["conversationId"]
    msgs = client.get(f"/api/chat/conversations/{body['conversationId']}/messages", headers=auth).json()
    assert [m["role"] for m in msgs] == ["USER", "ASSISTANT", "USER", "ASSISTANT"]
    assert isinstance(msgs[1]["citations"], list) and msgs[1]["citations"][0]["filename"] == "policy.txt"
    assert client.get("/api/chat/conversations", headers=auth).json()[0]["id"] == body["conversationId"]


def test_chat_with_nothing_relevant_does_not_call_the_llm(client, auth, monkeypatch):
    monkeypatch.setattr(llm, "generate_answer", lambda *a: pytest.fail("LLM must not be called with no context"))
    r = client.post("/api/chat", headers=auth, json={"message": "quantum chromodynamics", "retrievalMode": "lexical"})
    assert r.status_code == 200 and "couldn't find" in r.json()["answer"] and r.json()["citations"] == []


def test_chat_scoped_to_one_document(client, auth):
    a = upload(client, auth, "a.txt", "Alpha document about gardening tomatoes.").json()["id"]
    upload(client, auth, "b.txt", "Beta document about gardening cucumbers.")
    r = client.post("/api/chat", headers=auth, json={"message": "gardening", "documentId": a, "retrievalMode": "lexical"}).json()
    assert {c["documentId"] for c in r["citations"]} == {a}


def test_chat_reports_503_when_ollama_is_down(client, auth, monkeypatch):
    upload(client, auth, "policy.txt", POLICY)
    def down(*a):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(llm, "generate_answer", down)
    r = client.post("/api/chat", headers=auth, json={"message": "premium"})
    assert r.status_code == 503 and "Ollama" in r.json()["message"]


def test_chat_unknown_conversation_and_blank_message(client, auth):
    assert client.post("/api/chat", headers=auth, json={"message": "hi", "conversationId": 999}).status_code == 404
    assert client.post("/api/chat", headers=auth, json={"message": ""}).status_code == 422
    assert client.get("/api/chat/conversations/999/messages", headers=auth).status_code == 404


# ---------------------------------------------------------------------------- files: view / download / delete
def test_view_forces_download_for_non_previewable_types_and_download_always_attaches(client, auth):
    doc_id = upload(client, auth, "page.html", "<script>alert(1)</script>", "text/html").json()["id"]
    view = client.get(f"/api/documents/{doc_id}/view", headers=auth)
    assert view.headers["content-disposition"].startswith("attachment")
    assert view.headers["content-type"].startswith("application/octet-stream")
    assert view.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/api/documents/{doc_id}/download", headers=auth).content == b"<script>alert(1)</script>"


def test_pdf_and_images_may_render_inline(client, auth):
    doc_id = upload(client, auth, "scan.pdf", "%PDF-1.4 fake", "application/pdf").json()["id"]
    view = client.get(f"/api/documents/{doc_id}/view", headers=auth)
    assert view.headers["content-disposition"].startswith("inline") and view.headers["content-type"] == "application/pdf"


def test_delete_removes_everything_including_vectors_and_file(client, auth, chroma):
    doc_id = upload(client, auth, "policy.txt", POLICY).json()["id"]
    path = next(config.STORAGE_DIR.glob("*policy.txt"))
    assert path.exists() and chroma.rows
    assert client.delete(f"/api/documents/{doc_id}", headers=auth).status_code == 204
    assert not path.exists() and not chroma.rows
    with SessionLocal() as db:
        for model in (DocumentChunk, DocumentFact, DocumentAlert):
            assert db.scalars(select(model)).all() == []
    assert client.get(f"/api/documents/{doc_id}", headers=auth).status_code == 404
    assert client.get("/api/alerts", headers=auth).json()["alerts"] == []


def test_search_by_filename_and_404s(client, auth):
    upload(client, auth, "Rental Agreement.txt", "lease")
    upload(client, auth, "Insurance.txt", "policy")
    names = [d["originalFilename"] for d in client.get("/api/documents?q=rental", headers=auth).json()]
    assert names == ["Rental Agreement.txt"]
    for path in ("", "/content", "/facts", "/view", "/download"):
        assert client.get(f"/api/documents/424242{path}", headers=auth).status_code == 404
    assert client.delete("/api/documents/424242", headers=auth).status_code == 404
