"""Request bodies and response serialisers."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app import config
from app.models import Document, DocumentAlert, DocumentFact

RetrievalMode = Literal["hybrid", "vector", "lexical"]


class LoginBody(BaseModel):
    username: str
    password: str


class ChatBody(BaseModel):
    conversationId: Optional[int] = None
    documentId: Optional[int] = None
    message: str = Field(min_length=1, max_length=10000)
    retrievalMode: Optional[RetrievalMode] = None


class RetrieveBody(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    documentId: Optional[int] = None
    mode: RetrievalMode = "hybrid"
    limit: int = Field(default=3, ge=1, le=20)


def document_json(doc: Document) -> dict:
    return {
        "id": doc.id, "filename": doc.filename, "originalFilename": doc.original_filename,
        "contentType": doc.content_type, "size": doc.size, "status": doc.status,
        "errorMessage": doc.error_message, "pageCount": doc.page_count,
        "fileHash": doc.file_hash, "category": doc.category,
        "uploadedAt": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "processedAt": doc.processed_at.isoformat() if doc.processed_at else None,
    }


def fact_json(fact: DocumentFact) -> dict:
    return {"id": fact.id, "documentId": fact.document_id, "type": fact.fact_type, "name": fact.key_name, "value": fact.value}


def alert_status(deadline: date, today: Optional[date] = None) -> tuple[str, int]:
    """Return (status, days_left). OVERDUE < 0 days, DUE_SOON within the alert window, else UPCOMING."""
    today = today or date.today()
    days_left = (deadline - today).days
    if days_left < 0:
        return "OVERDUE", days_left
    if days_left <= config.ALERT_WINDOW_DAYS:
        return "DUE_SOON", days_left
    return "UPCOMING", days_left


def alert_json(alert: DocumentAlert, filename: Optional[str] = None, today: Optional[date] = None) -> dict:
    status, days_left = alert_status(alert.deadline_date, today)
    return {
        "id": alert.id, "documentId": alert.document_id, "filename": filename,
        "title": alert.title, "description": alert.description, "type": alert.alert_type,
        "deadline": alert.deadline_date.isoformat(), "daysLeft": days_left, "status": status,
        "acknowledged": bool(alert.is_acknowledged),
    }
