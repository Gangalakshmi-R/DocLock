"""Retrieval over indexed passages with three selectable strategies.

* ``vector``  - semantic search: ChromaDB first, cosine over vectors stored in PostgreSQL as a fallback.
* ``lexical`` - BM25 keyword search over the stored passages (needs no model at all).
* ``hybrid``  - reciprocal-rank fusion of both rankings (default). It still works if embeddings are
                unavailable, because it simply degrades to BM25.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentChunk
from app.services import ranking, vectorstore


@dataclass
class Hit:
    chunk: DocumentChunk
    score: Optional[float]


def _load_candidates(db: Session, document_id: Optional[int]) -> list[DocumentChunk]:
    stmt = select(DocumentChunk).order_by(DocumentChunk.id.asc())
    if document_id is not None:
        stmt = stmt.where(DocumentChunk.document_id == document_id)
    return list(db.scalars(stmt).all())


def _stored_vector(chunk: DocumentChunk) -> list[float]:
    if not chunk.vector_json:
        return []
    try:
        return [float(x) for x in json.loads(chunk.vector_json)]
    except (ValueError, TypeError):
        return []


def _vector_ranking(db: Session, query_vector: list[float], document_id: Optional[int], pool: int,
                    candidates: Optional[list[DocumentChunk]] = None) -> list[DocumentChunk]:
    """Best-first chunks by semantic similarity."""
    if not query_vector:
        return []
    ids = vectorstore.query(query_vector, document_id, pool)
    if ids:
        found = db.scalars(select(DocumentChunk).where(DocumentChunk.vector_id.in_(ids))).all()
        by_id = {c.vector_id: c for c in found}
        ordered = [by_id[v] for v in ids if v in by_id]
        if ordered:
            return ordered
    # Fallback: brute-force cosine over the vectors persisted in PostgreSQL.
    pool_chunks = candidates if candidates is not None else _load_candidates(db, document_id)
    scored = [(ranking.cosine(query_vector, _stored_vector(c)), c) for c in pool_chunks]
    scored = [(s, c) for s, c in scored if s > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:pool]]


def _lexical_ranking(candidates: list[DocumentChunk], query: str) -> list[tuple[DocumentChunk, float]]:
    scores = ranking.bm25_scores(query, [c.content for c in candidates])
    return [(candidates[i], scores[i]) for i in ranking.rank_by_score(scores)]


def retrieve(db: Session, question: str, query_vector: list[float], document_id: Optional[int],
             limit: int = 3, mode: str = "hybrid", lexical_query: Optional[str] = None) -> list[Hit]:
    lexical_query = lexical_query or question
    pool = max(limit * 4, 12)

    if mode == "lexical":
        return [Hit(c, s) for c, s in _lexical_ranking(_load_candidates(db, document_id), lexical_query)[:limit]]

    if mode == "vector":
        chunks = _vector_ranking(db, query_vector, document_id, limit)[:limit]
        return [Hit(c, ranking.cosine(query_vector, _stored_vector(c)) or None) for c in chunks]

    # hybrid
    candidates = _load_candidates(db, document_id)
    by_pk = {c.id: c for c in candidates}
    vector_ranked = [c.id for c in _vector_ranking(db, query_vector, document_id, pool, candidates) if c.id in by_pk]
    lexical_ranked = [c.id for c, _ in _lexical_ranking(candidates, lexical_query)][:pool]
    fused = ranking.reciprocal_rank_fusion([vector_ranked, lexical_ranked])
    return [Hit(by_pk[pk], score) for pk, score in fused[:limit]]
