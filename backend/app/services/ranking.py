"""Pure ranking helpers: tokenisation, BM25, cosine similarity and reciprocal-rank fusion.

Deliberately free of database / network imports so the evaluation scripts can reuse them offline.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Hashable, Sequence

_TOKEN = re.compile(r"[\w]+(?:[-'][\w]+)*", re.UNICODE)
_STOPWORDS = frozenset(
    "a an and are as at be by do does for from has have how i in is it its of on or that the this to was were what when "
    "where which who whom whose why will with you your my our their his her there than then these those can could should would".split()
)


def tokenize(text: str) -> list[str]:
    """Lower-cased word tokens with stopwords and 1-character tokens removed."""
    return [t for t in (m.group(0).lower() for m in _TOKEN.finditer(text)) if len(t) > 1 and t not in _STOPWORDS]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def bm25_scores(query: str, documents: Sequence[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Okapi BM25 score of *query* against each document (same order as *documents*)."""
    q_terms = list(dict.fromkeys(tokenize(query)))
    tokenised = [tokenize(d) for d in documents]
    if not q_terms or not tokenised:
        return [0.0] * len(documents)
    n_docs = len(tokenised)
    avg_len = (sum(len(t) for t in tokenised) / n_docs) or 1.0
    doc_freq = {term: sum(1 for toks in tokenised if term in toks) for term in q_terms}

    scores: list[float] = []
    for toks in tokenised:
        counts = Counter(toks)
        length = len(toks) or 1
        score = 0.0
        for term in q_terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n_docs - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * length / avg_len))
        scores.append(score)
    return scores


def rank_by_score(scores: Sequence[float], min_score: float = 0.0) -> list[int]:
    """Indices ordered best-first, dropping anything at or below *min_score*. Stable for ties."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [i for i in order if scores[i] > min_score]


def reciprocal_rank_fusion(rankings: Sequence[Sequence[Hashable]], k: int = 60) -> list[tuple[Hashable, float]]:
    """Fuse several best-first rankings into one. Score = sum over rankings of 1 / (k + rank)."""
    fused: dict[Hashable, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda pair: pair[1], reverse=True)
