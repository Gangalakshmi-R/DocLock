# Offline experiment: chunking vs. keyword (BM25) retrieval

24 answerable questions over 4 documents, corpus-wide retrieval, top-3. A question is a *hit* when a retrieved passage comes from the right document and contains the gold evidence phrase. No model is involved; reproduce with `python eval/offline_chunk_experiment.py`.

## Chunk size (overlap = 15% of size)

| chunk size | chunks | avg chars | LLM context (chars) | hit@1 | hit@3 | MRR@3 | hit@3 direct | hit@3 paraphrase |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 200 (overlap 15%) | 71 | 157 | 457 | 50% | 62% | 0.56 | 92% | 27% |
| 300 (overlap 15%) | 49 | 228 | 668 | 50% | 67% | 0.58 | 100% | 27% |
| 500 (overlap 15%) | 27 | 402 | 1123 | 58% | 83% | 0.69 | 100% | 64% |
| 800 (overlap 15%) | 19 | 576 | 1711 | 67% | 92% | 0.78 | 100% | 82% |
| 1000 (overlap 15%) | 13 | 807 | 2346 | 75% | 96% | 0.83 | 100% | 91% |
| 1500 (overlap 15%) | 9 | 1140 | 3267 | 88% | 96% | 0.92 | 100% | 91% |
| 3000 (overlap 15%) | 4 | 2284 | 5495 | 100% | 100% | 1.00 | 100% | 100% |

## Chunk overlap (chunk size fixed at 500)

| overlap | chunks | avg chars | LLM context (chars) | hit@1 | hit@3 | MRR@3 | hit@3 direct | hit@3 paraphrase |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 chars | 24 | 379 | 1135 | 71% | 79% | 0.74 | 100% | 55% |
| 50 chars | 26 | 394 | 1118 | 58% | 92% | 0.73 | 100% | 82% |
| 100 chars | 30 | 391 | 1129 | 62% | 88% | 0.73 | 100% | 73% |
| 150 chars | 34 | 401 | 1177 | 71% | 88% | 0.79 | 100% | 73% |
| 250 chars | 97 | 333 | 1056 | 67% | 67% | 0.67 | 100% | 27% |

## How to read this

- **Bigger chunks look better on hit@k, but the metric does not charge for their cost.** At 3000 characters every document is a single chunk, so 'hit' only means BM25 picked the right document. The *LLM context* column shows what the price is: more text per question for the model to read (and at 3000 it approaches the context window). That is why the default stays at 1000 characters rather than the largest value.
- **Heavy overlap hurts.** At 250 characters of overlap on 500-character chunks, neighbouring chunks are near-duplicates that fill the top-3, so fewer distinct passages are retrieved.
- **Paraphrased questions are where keyword search struggles** (low `paraphrase` columns). That gap is what embeddings and hybrid retrieval are for; measure it with `eval/run_eval.py` against the running stack.
- **Small sample:** 24 questions means one question is about 4 percentage points. Treat differences under roughly 10 points (for example 0 vs 50 overlap) as noise, not as a finding.
