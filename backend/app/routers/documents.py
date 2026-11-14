from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import config
from app.db import get_db, utcnow
from app.models import Document, DocumentAlert, DocumentChunk, DocumentContent, DocumentFact
from app.schemas import document_json, fact_json
from app.security import current_user
from app.services import doctype, ingestion, pii, vectorstore

router = APIRouter(prefix="/api/documents", tags=["documents"], dependencies=[Depends(current_user)])


def get_document_or_404(db: Session, document_id: int) -> Document:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.get("")
def list_documents(q: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    stmt = select(Document).order_by(Document.uploaded_at.desc(), Document.id.desc())
    if q and q.strip():
        stmt = stmt.where(Document.original_filename.ilike(f"%{q.strip()}%"))
    return [document_json(doc) for doc in db.scalars(stmt).all()]


@router.post("", status_code=202)
async def upload_document(background: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Store the file and return immediately (202). Text extraction, embedding and fact analysis run in the
    background; poll GET /api/documents/{id} until ``status`` is PROCESSED or FAILED."""
    original = Path(file.filename or "document").name
    suffix = Path(original).suffix.lower()
    if suffix not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type. Upload PDF, Office, text or image files.")
    if len(original) > 250:
        raise HTTPException(status_code=400, detail="Filename is too long.")
    data = await file.read(config.MAX_FILE_SIZE + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Please select a non-empty file.")
    if len(data) > config.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File is too large. Maximum upload size is {config.MAX_FILE_SIZE // (1024 * 1024)} MB.")

    file_hash = hashlib.sha256(data).hexdigest()
    duplicate = db.scalar(select(Document).where(Document.file_hash == file_hash, Document.status != "FAILED"))
    if duplicate:
        raise HTTPException(status_code=409, detail=f"This file was already uploaded as '{duplicate.original_filename}'.")

    stored_name = f"{uuid.uuid4()}_{re.sub(r'[^a-zA-Z0-9._-]', '_', original)}"
    saved_path = config.STORAGE_DIR / stored_name
    saved_path.write_bytes(data)
    doc = Document(filename=stored_name, original_filename=original,
                   content_type=file.content_type or "application/octet-stream", size=len(data),
                   storage_path=str(saved_path), status="QUEUED", file_hash=file_hash, uploaded_at=utcnow())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    background.add_task(ingestion.process_document, doc.id)
    return document_json(doc)


@router.get("/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db)):
    return document_json(get_document_or_404(db, document_id))


def _text_of(db: Session, document_id: int) -> str:
    get_document_or_404(db, document_id)
    content = db.scalar(select(DocumentContent).where(DocumentContent.document_id == document_id))
    return content.extracted_text if content else ""


@router.get("/{document_id}/insights")
def document_insights(document_id: int, db: Session = Depends(get_db)):
    """Detected document type, a checklist of expected clauses, and masked personal identifiers."""
    doc = get_document_or_404(db, document_id)
    text = _text_of(db, document_id)
    kind = doctype.classify(text, doc.original_filename)
    return {"type": kind.key, "typeLabel": kind.label, "confidence": kind.confidence, "matched": list(kind.matched),
            "checklist": doctype.checklist(kind.key, text), "pii": pii.summarise(text)}


@router.get("/{document_id}/redacted")
def document_redacted(document_id: int, db: Session = Depends(get_db)):
    """Extracted text with Aadhaar / PAN / phone / email etc. masked, safe to copy or share."""
    return {"text": pii.redact(_text_of(db, document_id))}


@router.get("/{document_id}/content")
def document_content(document_id: int, db: Session = Depends(get_db)):
    get_document_or_404(db, document_id)
    content = db.scalar(select(DocumentContent).where(DocumentContent.document_id == document_id))
    return {"content": content.extracted_text if content else ""}


@router.get("/{document_id}/facts")
def document_facts(document_id: int, db: Session = Depends(get_db)):
    get_document_or_404(db, document_id)
    rows = db.scalars(select(DocumentFact).where(DocumentFact.document_id == document_id).order_by(DocumentFact.id)).all()
    return {"facts": [fact_json(f) for f in rows]}


def _stored_file(doc: Document) -> Path:
    path = Path(doc.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The stored document file is missing.")
    return path


@router.get("/{document_id}/view")
def view_document(document_id: int, db: Session = Depends(get_db)):
    doc = get_document_or_404(db, document_id)
    path = _stored_file(doc)
    # Only PDFs and raster images may render inline. Anything else (HTML, XML, Office files...) is forced to
    # download so an uploaded file can never execute in the app's origin.
    inline = Path(doc.original_filename).suffix.lower() in config.INLINE_PREVIEW_TYPES
    return FileResponse(path, media_type=doc.content_type if inline else "application/octet-stream",
                        filename=doc.original_filename, content_disposition_type="inline" if inline else "attachment",
                        headers={"X-Content-Type-Options": "nosniff"})


@router.get("/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db)):
    doc = get_document_or_404(db, document_id)
    return FileResponse(_stored_file(doc), media_type="application/octet-stream", filename=doc.original_filename,
                        content_disposition_type="attachment", headers={"X-Content-Type-Options": "nosniff"})


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = get_document_or_404(db, document_id)
    path = Path(doc.storage_path)
    vector_ids = db.scalars(select(DocumentChunk.vector_id).where(DocumentChunk.document_id == document_id)).all()
    vectorstore.delete([v for v in vector_ids if v])
    for model in (DocumentChunk, DocumentContent, DocumentFact, DocumentAlert):
        db.execute(delete(model).where(model.document_id == document_id))
    db.delete(doc)
    db.commit()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"File cleanup warning: {exc}")
    return Response(status_code=204)
