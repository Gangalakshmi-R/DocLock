"""Shared helpers for the evaluation scripts (dataset loading and retrieval metrics)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

EVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_DIR / "corpus"


def load_dataset() -> tuple[list[dict], list[dict]]:
    data = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))
    return data["questions"], data["unanswerable"]


def norm(text: str) -> str:
    """Case- and whitespace-insensitive form used for all evidence / keyword matching."""
    return " ".join(text.lower().split())


def first_hit_rank(results: Sequence[tuple[str, str]], gold_doc: str, evidence: str, k: int) -> Optional[int]:
    """1-based rank of the first retrieved passage that comes from the gold document AND contains the evidence
    phrase, looking only at the top *k* results. None = miss. *results* are (document_filename, passage_text)."""
    needle = norm(evidence)
    for rank, (filename, content) in enumerate(results[:k], start=1):
        if filename == gold_doc and needle in norm(content):
            return rank
    return None


def summarize(ranks: Sequence[Optional[int]], k: int) -> dict:
    """hit@1, hit@k and MRR@k over a list of first-hit ranks."""
    n = len(ranks) or 1
    return {
        "n": len(ranks),
        "hit@1": sum(1 for r in ranks if r == 1) / n,
        f"hit@{k}": sum(1 for r in ranks if r is not None) / n,
        f"mrr@{k}": sum(1 / r for r in ranks if r is not None) / n,
    }


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"
