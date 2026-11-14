#!/usr/bin/env python
"""Offline design-choice experiment: how do chunk size and chunk overlap affect retrieval?

Needs NO running services and NO models: it chunks the evaluation corpus with DocLock's own chunker and
retrieves with DocLock's own BM25 (the 'lexical' strategy), then scores hit@1 / hit@3 / MRR@3 against the
gold evidence in eval/questions.json. Fully reproducible:

    python eval/offline_chunk_experiment.py            # prints tables, writes eval/offline_results.md

Retrieval is corpus-wide (all four documents are searched together), like asking an unscoped question in the app.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services import ranking  # noqa: E402
from app.services.chunking import split_chunks  # noqa: E402
from common import CORPUS_DIR, EVAL_DIR, first_hit_rank, load_dataset, pct, summarize  # noqa: E402

K = 3


def build_index(chunk_size: int, overlap: int) -> list[tuple[str, str]]:
    index: list[tuple[str, str]] = []
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        index.extend((path.name, chunk) for chunk, _, _ in split_chunks(text, chunk_size, overlap))
    return index


def evaluate(chunk_size: int, overlap: int, questions: list[dict]) -> dict:
    index = build_index(chunk_size, overlap)
    contents = [c for _, c in index]
    ranks_all, ranks_by_style, context_sizes = [], {"direct": [], "paraphrase": []}, []
    for q in questions:
        scores = ranking.bm25_scores(q["question"], contents)
        top = [(index[i][0], contents[i]) for i in ranking.rank_by_score(scores)[:K]]
        context_sizes.append(sum(len(c) for _, c in top))
        rank = first_hit_rank(top, q["doc"], q["evidence"], K)
        ranks_all.append(rank)
        ranks_by_style[q["style"]].append(rank)
    result = summarize(ranks_all, K)
    result["chunks"] = len(index)
    result["avg_chars"] = sum(len(c) for c in contents) / max(len(contents), 1)
    result["context_chars"] = sum(context_sizes) / max(len(context_sizes), 1)  # text the LLM must read per question
    for style, ranks in ranks_by_style.items():
        result[f"hit@{K} ({style})"] = summarize(ranks, K)[f"hit@{K}"]
    return result


def table(rows: list[tuple[str, dict]], first_col: str) -> str:
    head = f"| {first_col} | chunks | avg chars | LLM context (chars) | hit@1 | hit@{K} | MRR@{K} | hit@{K} direct | hit@{K} paraphrase |"
    lines = [head, "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for label, r in rows:
        lines.append(f"| {label} | {r['chunks']} | {r['avg_chars']:.0f} | {r['context_chars']:.0f} | {pct(r['hit@1'])} | {pct(r[f'hit@{K}'])} | "
                     f"{r[f'mrr@{K}']:.2f} | {pct(r[f'hit@{K} (direct)'])} | {pct(r[f'hit@{K} (paraphrase)'])} |")
    return "\n".join(lines)


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    questions, _ = load_dataset()

    sizes = [200, 300, 500, 800, 1000, 1500, 3000]
    size_rows = [(f"{s} (overlap 15%)", evaluate(s, round(s * 0.15), questions)) for s in sizes]
    overlaps = [0, 50, 100, 150, 250]
    overlap_rows = [(f"{o} chars", evaluate(500, o, questions)) for o in overlaps]

    md = [
        "# Offline experiment: chunking vs. keyword (BM25) retrieval",
        "",
        f"{len(questions)} answerable questions over 4 documents, corpus-wide retrieval, top-{K}. "
        "A question is a *hit* when a retrieved passage comes from the right document and contains the gold evidence phrase. "
        "No model is involved; reproduce with `python eval/offline_chunk_experiment.py`.",
        "",
        "## Chunk size (overlap = 15% of size)",
        "",
        table(size_rows, "chunk size"),
        "",
        "## Chunk overlap (chunk size fixed at 500)",
        "",
        table(overlap_rows, "overlap"),
        "",
        "## How to read this",
        "",
        "- **Bigger chunks look better on hit@k, but the metric does not charge for their cost.** At 3000 characters every "
        "document is a single chunk, so 'hit' only means BM25 picked the right document. The *LLM context* column shows what "
        "the price is: more text per question for the model to read (and at 3000 it approaches the context window). "
        "That is why the default stays at 1000 characters rather than the largest value.",
        "- **Heavy overlap hurts.** At 250 characters of overlap on 500-character chunks, neighbouring chunks are near-duplicates "
        "that fill the top-3, so fewer distinct passages are retrieved.",
        "- **Paraphrased questions are where keyword search struggles** (low `paraphrase` columns). That gap is what "
        "embeddings and hybrid retrieval are for; measure it with `eval/run_eval.py` against the running stack.",
        "- **Small sample:** 24 questions means one question is about 4 percentage points. Treat differences under roughly "
        "10 points (for example 0 vs 50 overlap) as noise, not as a finding.",
        "",
    ]
    out = "\n".join(md)
    print(out)
    (EVAL_DIR / "offline_results.md").write_text(out, encoding="utf-8")
    print(f"\nWritten to {EVAL_DIR / 'offline_results.md'}")


if __name__ == "__main__":
    main()
