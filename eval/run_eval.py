#!/usr/bin/env python
"""Evaluate a RUNNING DocLock stack (retrieval strategies + answer quality + refusal behaviour).

    python eval/run_eval.py                                  # uses DOCLOCK_USERNAME / DOCLOCK_PASSWORD from the environment
    python eval/run_eval.py --password 'my-password' --base-url http://localhost:8080
    python eval/run_eval.py --skip-generation                # retrieval only (fast, no LLM calls)
    python eval/run_eval.py --reset --out eval/results-chunk500.md   # delete + re-upload the corpus (after changing DOCLOCK_CHUNK_SIZE)

What it measures
  Retrieval (per strategy: vector / lexical / hybrid)   hit@1, hit@k, MRR@k, split into direct vs paraphrased questions.
                                                        A hit = a top-k passage from the gold document that contains the gold evidence phrase.
  Answers  (strategy given by --gen-mode)               Accuracy: the answer contains an expected keyword (a cheap proxy; read a few answers yourself).
                                                        Grounding: the gold document is among the cited sources.
  Refusal  (unanswerable questions)                     The assistant should say the documents do not contain the answer instead of inventing one.
  Latency                                               Mean / p95 seconds per chat call.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CORPUS_DIR, EVAL_DIR, first_hit_rank, load_dataset, norm, pct, summarize  # noqa: E402

ABSTAIN_PHRASES = (
    "do not contain enough information", "does not contain enough information", "not enough information", "couldn't find",
    "could not find", "can't find", "cannot find", "no information", "not mentioned", "doesn't contain", "does not contain",
    "do not contain", "not provided", "not specified", "not stated", "no mention", "doesn't mention", "does not mention",
)


class Api:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base = base_url.rstrip("/") + "/api"
        self.http = requests.Session()
        r = self.http.post(f"{self.base}/auth/login", json={"username": username, "password": password}, timeout=30)
        if r.status_code != 200:
            sys.exit(f"Login failed ({r.status_code}): {r.text}")
        self.http.headers["Authorization"] = f"Bearer {r.json()['token']}"

    def documents(self) -> list[dict]:
        r = self.http.get(f"{self.base}/documents", timeout=30)
        r.raise_for_status()
        return r.json()

    def upload(self, path: Path) -> requests.Response:
        with path.open("rb") as fh:
            return self.http.post(f"{self.base}/documents", files={"file": (path.name, fh, "text/plain")}, timeout=120)

    def delete(self, doc_id: int) -> None:
        self.http.delete(f"{self.base}/documents/{doc_id}", timeout=60).raise_for_status()

    def retrieve(self, question: str, mode: str, k: int) -> list[dict]:
        r = self.http.post(f"{self.base}/retrieve", json={"question": question, "mode": mode, "limit": k}, timeout=120)
        r.raise_for_status()
        return r.json()["results"]

    def chat(self, question: str, mode: str) -> dict:
        r = self.http.post(f"{self.base}/chat", json={"message": question, "retrievalMode": mode}, timeout=600)
        r.raise_for_status()
        return r.json()


def ensure_corpus(api: Api, reset: bool, timeout: int) -> None:
    files = sorted(CORPUS_DIR.glob("*.txt"))
    existing = {d["originalFilename"]: d for d in api.documents()}
    if reset:
        for f in files:
            if f.name in existing:
                api.delete(existing[f.name]["id"])
        existing = {k: v for k, v in existing.items() if k not in {f.name for f in files}}
    for f in files:
        if f.name in existing:
            continue
        r = api.upload(f)
        if r.status_code == 409:
            print(f"  note: {f.name} already exists under another name ({r.json().get('message')})")
        elif r.status_code != 202:
            sys.exit(f"Upload of {f.name} failed ({r.status_code}): {r.text}")
        else:
            print(f"  uploaded {f.name}")
    deadline = time.time() + timeout
    wanted = {f.name for f in files}
    while True:
        docs = {d["originalFilename"]: d for d in api.documents() if d["originalFilename"] in wanted}
        failed = [n for n, d in docs.items() if d["status"] == "FAILED"]
        if failed:
            sys.exit(f"Processing failed for {failed}: {[docs[n]['errorMessage'] for n in failed]}")
        pending = [n for n, d in docs.items() if d["status"] != "PROCESSED"]
        if not pending and len(docs) == len(wanted):
            return
        if time.time() > deadline:
            sys.exit(f"Timed out waiting for documents to finish processing: {pending}")
        print(f"  waiting for {len(pending) or len(wanted) - len(docs)} document(s) to finish processing...")
        time.sleep(3)


def eval_retrieval(api: Api, questions: list[dict], modes: list[str], k: int) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for mode in modes:
        ranks, by_style, latencies = [], {"direct": [], "paraphrase": []}, []
        for q in questions:
            t0 = time.time()
            results = api.retrieve(q["question"], mode, k)
            latencies.append(time.time() - t0)
            rank = first_hit_rank([(r["filename"], r["content"]) for r in results], q["doc"], q["evidence"], k)
            ranks.append(rank)
            by_style[q["style"]].append(rank)
        s = summarize(ranks, k)
        s["direct"] = summarize(by_style["direct"], k)[f"hit@{k}"]
        s["paraphrase"] = summarize(by_style["paraphrase"], k)[f"hit@{k}"]
        s["latency"] = statistics.mean(latencies)
        out[mode] = s
        print(f"  {mode:8s} hit@1={pct(s['hit@1'])} hit@{k}={pct(s[f'hit@{k}'])} mrr={s[f'mrr@{k}']:.2f}")
    return out


def eval_generation(api: Api, questions: list[dict], unanswerable: list[dict], mode: str) -> dict:
    correct, grounded, latencies, rows = 0, 0, [], []
    for q in questions:
        t0 = time.time()
        res = api.chat(q["question"], mode)
        latencies.append(time.time() - t0)
        answer = norm(res["answer"])
        ok = any(norm(kw) in answer for kw in q["answer_any"])
        cited = any(c["filename"] == q["doc"] for c in res["citations"])
        correct += ok
        grounded += cited
        rows.append((q["id"], ok, cited, res["answer"].replace("\n", " ")[:140]))
        print(f"  {q['id']:7s} answer_ok={'Y' if ok else 'N'} cited_gold_doc={'Y' if cited else 'N'}")
    abstained = 0
    for q in unanswerable:
        t0 = time.time()
        res = api.chat(q["question"], mode)
        latencies.append(time.time() - t0)
        refused = any(p in norm(res["answer"]) for p in ABSTAIN_PHRASES)
        abstained += refused
        rows.append((q["id"], refused, None, res["answer"].replace("\n", " ")[:140]))
        print(f"  {q['id']:7s} refused={'Y' if refused else 'N'}")
    latencies.sort()
    return {
        "accuracy": correct / len(questions), "grounded": grounded / len(questions),
        "refusal": abstained / max(len(unanswerable), 1),
        "latency_mean": statistics.mean(latencies), "latency_p95": latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))],
        "rows": rows, "n": len(questions), "n_unanswerable": len(unanswerable),
    }


def write_report(path: Path, args, retrieval: dict, generation: dict | None, k: int) -> None:
    lines = [
        "# DocLock evaluation results", "",
        f"Run: {datetime.now():%Y-%m-%d %H:%M} · API: `{args.base_url}` · top-k = {k} · "
        f"questions: {retrieval[next(iter(retrieval))]['n']} answerable"
        + (f" + {generation['n_unanswerable']} unanswerable" if generation else ""), "",
        "## Retrieval strategies", "",
        f"| strategy | hit@1 | hit@{k} | MRR@{k} | hit@{k} direct | hit@{k} paraphrase | mean latency |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, s in retrieval.items():
        lines.append(f"| {mode} | {pct(s['hit@1'])} | {pct(s[f'hit@{k}'])} | {s[f'mrr@{k}']:.2f} | {pct(s['direct'])} | "
                     f"{pct(s['paraphrase'])} | {s['latency']:.2f}s |")
    if generation:
        g = generation
        lines += [
            "", f"## Answer quality (retrieval strategy: `{args.gen_mode}`)", "",
            "| metric | result |", "|---|---:|",
            f"| answers containing the expected keyword | {pct(g['accuracy'])} |",
            f"| gold document cited as a source | {pct(g['grounded'])} |",
            f"| unanswerable questions correctly refused | {pct(g['refusal'])} |",
            f"| mean / p95 chat latency | {g['latency_mean']:.1f}s / {g['latency_p95']:.1f}s |",
            "", "Keyword matching is a cheap proxy for correctness; read the sample below and spot-check.", "",
            "<details><summary>Per-question outcomes</summary>", "", "| id | ok | cited gold doc | answer (truncated) |", "|---|---|---|---|",
        ]
        for qid, ok, cited, text in g["rows"]:
            lines.append(f"| {qid} | {'yes' if ok else 'no'} | {'-' if cited is None else ('yes' if cited else 'no')} | {text.replace('|', '/')} |")
        lines += ["", "</details>"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=os.getenv("DOCLOCK_API", "http://localhost:8080"))
    p.add_argument("--username", default=os.getenv("DOCLOCK_USERNAME", "admin"))
    p.add_argument("--password", default=os.getenv("DOCLOCK_PASSWORD", ""))
    p.add_argument("--modes", default="vector,lexical,hybrid", help="comma-separated retrieval strategies to compare")
    p.add_argument("--gen-mode", default="hybrid", help="retrieval strategy used for the answer-quality run")
    p.add_argument("-k", type=int, default=3)
    p.add_argument("--skip-generation", action="store_true", help="retrieval metrics only (no LLM calls)")
    p.add_argument("--reset", action="store_true", help="delete and re-upload the corpus (use after changing chunking settings)")
    p.add_argument("--timeout", type=int, default=900, help="seconds to wait for document processing")
    p.add_argument("--out", default=str(EVAL_DIR / "results.md"))
    args = p.parse_args()
    if not args.password:
        sys.exit("Provide --password or set DOCLOCK_PASSWORD.")

    questions, unanswerable = load_dataset()
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    print(f"Connecting to {args.base_url} ...")
    api = Api(args.base_url, args.username, args.password)
    print("Preparing the evaluation corpus ...")
    ensure_corpus(api, args.reset, args.timeout)
    print(f"Retrieval ({len(questions)} questions, k={args.k}) ...")
    retrieval = eval_retrieval(api, questions, modes, args.k)
    generation = None
    if not args.skip_generation:
        print(f"Answer quality + refusals (strategy: {args.gen_mode}) ...")
        generation = eval_generation(api, questions, unanswerable, args.gen_mode)
    out = Path(args.out)
    write_report(out, args, retrieval, generation, args.k)
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()
