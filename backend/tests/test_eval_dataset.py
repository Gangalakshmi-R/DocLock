"""Guards the evaluation set itself: a typo in a gold 'evidence' phrase would silently corrupt every metric."""
import sys
from pathlib import Path

import pytest

EVAL = Path(__file__).resolve().parents[2] / "eval"
sys.path.insert(0, str(EVAL))

from common import CORPUS_DIR, first_hit_rank, load_dataset, norm, summarize  # noqa: E402

QUESTIONS, UNANSWERABLE = load_dataset()


def test_dataset_shape():
    assert len(QUESTIONS) >= 20 and len(UNANSWERABLE) >= 3
    ids = [q["id"] for q in QUESTIONS + UNANSWERABLE]
    assert len(ids) == len(set(ids))
    styles = {q["style"] for q in QUESTIONS}
    assert styles == {"direct", "paraphrase"}
    assert all(q["answer_any"] and q["question"].endswith("?") for q in QUESTIONS)


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
def test_evidence_appears_exactly_once_in_its_gold_document(q):
    path = CORPUS_DIR / q["doc"]
    assert path.exists(), q["doc"]
    assert norm(path.read_text(encoding="utf-8")).count(norm(q["evidence"])) == 1


def test_every_corpus_file_is_used():
    assert {q["doc"] for q in QUESTIONS} == {p.name for p in CORPUS_DIR.glob("*.txt")}


def test_metric_helpers():
    results = [("a.txt", "nothing here"), ("b.txt", "The Answer is 42"), ("a.txt", "answer is 42")]
    assert first_hit_rank(results, "b.txt", "answer is 42", 3) == 2   # case-insensitive, right document
    assert first_hit_rank(results, "b.txt", "answer is 42", 1) is None  # outside top-k
    assert first_hit_rank(results, "c.txt", "answer is 42", 3) is None  # wrong document never counts
    s = summarize([1, 2, None, 1], 3)
    assert s["hit@1"] == 0.5 and s["hit@3"] == 0.75 and s["mrr@3"] == pytest.approx((1 + 0.5 + 0 + 1) / 4)
