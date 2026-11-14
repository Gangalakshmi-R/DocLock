from __future__ import annotations

import json
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.db import get_db, utcnow
from app.models import ChatConversation, ChatMessage, Document
from app.schemas import ChatBody, RetrieveBody
from app.security import current_user
from app.services import embeddings, llm, retrieval, verify

router = APIRouter(prefix="/api", tags=["chat"], dependencies=[Depends(current_user)])

SNIPPET_CHARS = 220


def _citation(doc: Document, hit: retrieval.Hit) -> dict:
    return {
        "documentId": doc.id, "filename": doc.original_filename, "chunk": hit.chunk.chunk_index + 1,
        "score": round(hit.score, 4) if hit.score is not None else None,
        "snippet": hit.chunk.content[:SNIPPET_CHARS],
    }


def _context_and_citations(db: Session, hits: list[retrieval.Hit]) -> tuple[str, list[dict]]:
    parts: list[str] = []
    citations: list[dict] = []
    used = 0
    for hit in hits:
        doc = db.get(Document, hit.chunk.document_id)
        if not doc:
            continue
        remaining = config.CONTEXT_CHAR_BUDGET - used
        if remaining <= 0:
            break
        passage = f"\n[Source: {doc.original_filename}, passage {hit.chunk.chunk_index + 1}]\n{hit.chunk.content}\n"
        parts.append(passage[:remaining])
        used += min(len(passage), remaining)
        citations.append(_citation(doc, hit))
    return "\n".join(parts), citations


@router.post("/retrieve")
def retrieve_passages(body: RetrieveBody, db: Session = Depends(get_db)):
    """Retrieval only (no generation). Fast, and what the evaluation harness uses to compare strategies."""
    question = body.question.strip()
    vector = embeddings.embed(question) if body.mode != "lexical" else []
    hits = retrieval.retrieve(db, question, vector, body.documentId, body.limit, body.mode)
    results = []
    for hit in hits:
        doc = db.get(Document, hit.chunk.document_id)
        if doc:
            results.append({**_citation(doc, hit), "content": hit.chunk.content})
    return {"mode": body.mode, "results": results}


@router.post("/chat")
def chat(body: ChatBody, db: Session = Depends(get_db)):
    question = body.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Please enter a question.")
    mode = body.retrievalMode or config.DEFAULT_RETRIEVAL_MODE

    if body.conversationId is None:
        conversation = ChatConversation(title=question[:70], created_at=utcnow(), updated_at=utcnow())
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    else:
        conversation = db.get(ChatConversation, body.conversationId)
        if not conversation:
            raise HTTPException(status_code=404, detail="Chat conversation not found.")

    previous = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation.id)
                          .order_by(ChatMessage.timestamp.asc(), ChatMessage.id.asc())).all()
    db.add(ChatMessage(conversation_id=conversation.id, role="USER", content=question, timestamp=utcnow()))
    db.commit()

    # Follow-up questions ("and what about the deposit?") need the earlier turns to retrieve well.
    search_question = question
    lexical_query = question
    if previous:
        recent = "\n".join(f"{m.role}: {m.content[:350]}" for m in previous[-4:])
        search_question = f"{recent}\nCurrent question: {question}"
        last_user = next((m.content for m in reversed(previous) if m.role == "USER"), "")
        lexical_query = f"{last_user[:300]} {question}".strip()

    query_vector = embeddings.embed(search_question) if mode != "lexical" else []
    hits = retrieval.retrieve(db, search_question, query_vector, body.documentId, config.RETRIEVAL_TOP_K, mode, lexical_query)
    context, citations = _context_and_citations(db, hits)
    verification = None

    if not citations:
        answer = ("I couldn't find relevant information in your uploaded documents. Please upload a document containing this "
                  "information or ask using terms found in your files." if body.documentId is None
                  else "I couldn't find relevant information for this question in the selected document.")
    else:
        try:
            answer = llm.generate_answer(question, context, previous)
        except requests.RequestException as exc:
            raise HTTPException(status_code=503, detail=f"Cannot contact Ollama. Check that the chat model is running. Details: {exc}")
        # Trust layer: every figure/date in the answer must appear in the passages the model was given.
        verification = verify.verify_answer(answer, [h.chunk.content for h in hits])

    conversation.updated_at = utcnow()
    db.add(ChatMessage(conversation_id=conversation.id, role="ASSISTANT", content=answer,
                       citations_json=json.dumps({"citations": citations, "verification": verification}), timestamp=utcnow()))
    db.commit()
    return {"conversationId": conversation.id, "answer": answer, "citations": citations, "verification": verification, "retrievalMode": mode}


@router.get("/chat/conversations")
def conversations(db: Session = Depends(get_db)):
    rows = db.scalars(select(ChatConversation).order_by(ChatConversation.updated_at.desc())).all()
    return [{"id": c.id, "title": c.title, "createdAt": c.created_at.isoformat(), "updatedAt": c.updated_at.isoformat()} for c in rows]


def _parse_stored(raw: Optional[str]) -> tuple[list, Optional[dict]]:
    """citations_json holds {"citations": [...], "verification": {...}}; older rows hold a bare list."""
    try:
        data = json.loads(raw) if raw else []
    except ValueError:
        return [], None
    if isinstance(data, dict):
        return data.get("citations") or [], data.get("verification")
    return data, None


@router.get("/chat/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: int, db: Session = Depends(get_db)):
    if not db.get(ChatConversation, conversation_id):
        raise HTTPException(status_code=404, detail="Chat conversation not found.")
    rows = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
                      .order_by(ChatMessage.timestamp.asc(), ChatMessage.id.asc())).all()
    out = []
    for m in rows:
        citations, verification = _parse_stored(m.citations_json)
        out.append({"id": m.id, "role": m.role, "content": m.content, "citations": citations, "verification": verification,
                    "timestamp": m.timestamp.isoformat()})
    return out
