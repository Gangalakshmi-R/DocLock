from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Document, DocumentContent
from app.security import current_user
from app.services import pii

router = APIRouter(prefix="/api/privacy", tags=["privacy"], dependencies=[Depends(current_user)])


@router.get("")
def privacy_report(db: Session = Depends(get_db)):
    """Which documents in the vault contain personal identifiers, and how many of each kind (values masked)."""
    rows = db.execute(select(Document.id, Document.original_filename, DocumentContent.extracted_text)
                      .join(DocumentContent, DocumentContent.document_id == Document.id)
                      .order_by(Document.uploaded_at.desc())).all()
    documents, totals = [], {}
    for doc_id, filename, text in rows:
        summary = pii.summarise(text)
        if summary["total"]:
            documents.append({"documentId": doc_id, "filename": filename, "total": summary["total"], "counts": summary["counts"]})
            for kind, n in summary["counts"].items():
                totals[kind] = totals.get(kind, 0) + n
    return {"documentsScanned": len(rows), "documentsWithPii": len(documents), "totals": totals, "documents": documents,
            "labels": pii.KINDS}
