"""Background ingestion: extract -> chunk -> embed -> index -> analyse, with visible progress.

Runs *after* the upload response has been sent (FastAPI BackgroundTasks), so uploading a large PDF no
longer blocks the request. The UI polls the document's ``status``:

    QUEUED -> EXTRACTING -> INDEXING -> ANALYZING -> PROCESSED   (or FAILED)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import config
from app.db import SessionLocal, utcnow
from app.models import Document, DocumentAlert, DocumentChunk, DocumentContent, DocumentFact
from app.services import doctype, embeddings, extraction, facts, vectorstore
from app.services.chunking import split_chunks

NO_TEXT_WARNING = "No readable text was extracted. The original file is still available to view/download. Scanned files may require OCR."
NO_EMBED_WARNING = "Embeddings were unavailable, so this document is searchable by keywords only. Re-upload once Ollama is running for semantic search."


def _set_status(db: Session, doc: Document, status: str) -> None:
    doc.status = status
    db.commit()


def _index_chunks(db: Session, doc: Document, text: str) -> tuple[int, int]:
    """Chunk, embed (in batches) and store passages. Returns (chunk_count, embedded_count)."""
    chunks = split_chunks(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    vectors = embeddings.embed_batch([c[0] for c in chunks]) if chunks else []
    # OCR/text-PDF extraction inserts stable [Page N] markers. Persist the page for each
    # chunk so retrieval citations can point users back to the original scanned page.
    page_markers = [(match.start(), int(match.group(1)))
                    for match in re.finditer(r"(?m)^\[Page (\d+)\]\s*$", text)]

    def page_for_offset(offset: int):
        page_number = None
        for marker_offset, number in page_markers:
            if marker_offset > offset:
                break
            page_number = number
        return page_number

    rows: list[DocumentChunk] = []
    upserts: list[dict] = []
    for index, ((chunk_text, start, end), vector) in enumerate(zip(chunks, vectors)):
        vector_id = f"doc-{doc.id}-chunk-{index}"
        rows.append(DocumentChunk(document_id=doc.id, chunk_index=index, content=chunk_text, vector_id=vector_id,
                                  vector_json=json.dumps(vector) if vector else None,
                                  page_number=page_for_offset(start), start_char=start, end_char=end))
        if vector:
            upserts.append({"id": vector_id, "vector": vector, "text": chunk_text, "document_id": doc.id,
                            "filename": doc.original_filename, "chunk_index": index})
    db.add_all(rows)
    db.flush()
    for i in range(0, len(upserts), 64):
        vectorstore.upsert_batch(upserts[i:i + 64])
    return len(chunks), sum(1 for v in vectors if v)


def _analyse(db: Session, doc: Document, text: str) -> None:
    """Populate document_facts / document_alerts. Never raises: analysis is a bonus, not a requirement."""
    try:
        doc.category = doctype.classify(text, doc.original_filename).key
        extracted = facts.extract_facts(text)
        db.execute(delete(DocumentFact).where(DocumentFact.document_id == doc.id))
        db.execute(delete(DocumentAlert).where(DocumentAlert.document_id == doc.id))
        for f in extracted:
            db.add(DocumentFact(document_id=doc.id, fact_type=f.fact_type, key_name=f.key_name, value=f.value))
        for a in facts.alerts_from_facts(extracted):
            db.add(DocumentAlert(document_id=doc.id, title=a["title"], description=a["description"],
                                 deadline_date=a["deadline_date"], alert_type=a["alert_type"], created_at=utcnow()))
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"Fact analysis failed for document {doc.id}: {exc}")


def _cleanup_partial(db: Session, document_id: int) -> None:
    partial = db.scalars(select(DocumentChunk.vector_id).where(DocumentChunk.document_id == document_id)).all()
    vectorstore.delete([v for v in partial if v])
    for model in (DocumentChunk, DocumentContent, DocumentFact, DocumentAlert):
        db.execute(delete(model).where(model.document_id == document_id))


def process_document(document_id: int) -> None:
    """Entry point used by the upload route. Opens its own DB session (the request's is already closed)."""
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        try:
            _set_status(db, doc, "EXTRACTING")
            source_path = Path(doc.storage_path)
            # OCR is automatic for PDFs and raster images. Other formats retain the existing
            # Tika/plain-text extraction path. Keep extract_text as the compatibility hook
            # used by existing integrations and tests.
            if source_path.suffix.lower() == ".pdf" or source_path.suffix.lower() in extraction.IMAGE_EXTENSIONS:
                extraction_result = extraction.extract_document(source_path)
            else:
                extraction_result = extraction.ExtractionResult(extraction.extract_text(source_path))
            text = extraction_result.text
            if extraction_result.page_count is not None:
                doc.page_count = extraction_result.page_count
            if extraction_result.ocr_used:
                print(
                    f"OCR completed for document {doc.id}; "
                    f"pages: {', '.join(map(str, extraction_result.ocr_pages)) or 'unknown'}"
                )
            db.add(DocumentContent(document_id=doc.id, extracted_text=text, word_count=len(text.split())))
            db.commit()

            _set_status(db, doc, "INDEXING")
            chunk_count, embedded = _index_chunks(db, doc, text)
            db.commit()

            _set_status(db, doc, "ANALYZING")
            _analyse(db, doc, text)

            doc.error_message = (NO_TEXT_WARNING if chunk_count == 0 else NO_EMBED_WARNING if embedded == 0 else None)
            doc.status = "PROCESSED"
            doc.processed_at = utcnow()
            db.commit()
        except Exception as exc:
            db.rollback()
            current = db.get(Document, document_id)
            if current is not None:
                _cleanup_partial(db, document_id)
                current.status = "FAILED"
                current.error_message = str(exc)[:1500]
                db.commit()


def recover_interrupted() -> int:
    """On startup, mark documents left mid-processing by a restart as FAILED so the UI never spins forever."""
    with SessionLocal() as db:
        stuck = db.scalars(select(Document).where(Document.status.notin_(["PROCESSED", "FAILED"]))).all()
        for doc in stuck:
            _cleanup_partial(db, doc.id)
            doc.status = "FAILED"
            doc.error_message = "Processing was interrupted by a server restart. Delete and upload the document again."
        db.commit()
        return len(stuck)
