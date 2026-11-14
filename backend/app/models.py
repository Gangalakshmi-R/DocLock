"""SQLAlchemy models. Table layout is unchanged from v1, so existing databases keep working."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow

# SQLite only auto-increments INTEGER primary keys; PostgreSQL keeps BIGINT.
BigId = BigInteger().with_variant(Integer, "sqlite")

# Document lifecycle: QUEUED -> EXTRACTING -> INDEXING -> ANALYZING -> PROCESSED | FAILED
TERMINAL_STATUSES = {"PROCESSED", "FAILED"}


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="UPLOADING")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64))
    category: Mapped[Optional[str]] = mapped_column(String(50))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class DocumentContent(Base):
    __tablename__ = "document_contents"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[Optional[int]] = mapped_column(Integer)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    vector_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    vector_json: Mapped[Optional[str]] = mapped_column(Text)
    start_char: Mapped[Optional[int]] = mapped_column(Integer)
    end_char: Mapped[Optional[int]] = mapped_column(Integer)


class DocumentFact(Base):
    """Structured facts extracted from a document (dates, amounts, ...)."""
    __tablename__ = "document_facts"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    fact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    key_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)


class DocumentAlert(Base):
    """Deadline / expiry reminders derived from document facts."""
    __tablename__ = "document_alerts"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    deadline_date: Mapped[date] = mapped_column(Date, nullable=False)
    alert_type: Mapped[Optional[str]] = mapped_column(String(50))
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=utcnow)


class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations_json: Mapped[Optional[str]] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
