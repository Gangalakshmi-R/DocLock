<h1 align="center">🔐 DocLock</h1>

<p align="center"><b>A private, self-hosted AI assistant for your personal documents.</b><br>
It reads your insurance policies, rent agreements and fee circulars, answers questions with cited sources,<br>
<b>double-checks every number it states</b>, <b>warns you before things expire</b>, and <b>masks your Aadhaar/PAN</b>.<br>
Everything runs locally. No document ever leaves your machine.</p>

<p align="center">
  <img alt="tests" src="https://img.shields.io/badge/tests-149%20passing-brightgreen">
  <img alt="python" src="https://img.shields.io/badge/Python-3.11+-blue">
  <img alt="fastapi" src="https://img.shields.io/badge/FastAPI-backend-009688">
  <img alt="react" src="https://img.shields.io/badge/React-18-61dafb">
  <img alt="docker" src="https://img.shields.io/badge/Docker-compose-2496ed">
  <img alt="llm" src="https://img.shields.io/badge/LLM-Llama%203.1%208B%20(local)-purple">
</p>

<p align="center"><img src="docs/demo.gif" alt="DocLock demo" width="900"></p>

> **About the demo media:** the GIF and screenshots are real captures of the real app (real backend, real extraction, alerts, privacy scan and answer check). Only the LLM and embedding calls are stubbed so they could be recorded without a GPU, so the answer *wording* is canned. Re-record on your own stack with `python docs/record_demo.py --password "<yours>"`.

---

## Why this project

Important papers (insurance, lease, college fees, warranties) are scattered, long, and full of dates and amounts people miss. Generic "chat with your PDF" tools have three problems: they send private documents to a cloud, they sometimes state wrong numbers confidently, and they never *tell you* that something is about to expire.

DocLock is built around those three problems.

## What makes it different

| | Feature | What it does |
|---|---|---|
| ✅ | **Answer trust check** | Every number and date in the LLM's answer is checked against the passages it was given. The UI shows *“3 of 4 figures verified”* and names any figure it could not find. Deterministic, no second LLM call. |
| ⏰ | **Deadline & expiry alerts** | Dates, amounts and deadlines are extracted (regex + LLM JSON, **grounded against the document text so invented values are dropped**), turned into OVERDUE / DUE SOON / UPCOMING alerts, and exportable to Google/Apple/Outlook calendar as `.ics`. |
| 🛡️ | **India-specific privacy scan** | Finds Aadhaar (validated with the **Verhoeff checksum**, so random 12-digit numbers are ignored), PAN, GSTIN, IFSC, mobile and email. Only *masked* values are ever returned, and any document has a one-click redacted copy. |
| 🧾 | **Document type + checklist** | Classifies the document (insurance, rental, fee circular, ...), explains which words decided it, and lists expected clauses that are **missing** (waiting period? exclusions? notice period?). |
| 🔎 | **Hybrid retrieval** | Vector search + BM25 keyword search fused with reciprocal rank fusion; degrades gracefully to keywords if embeddings are down. Selectable per question. |
| ⚙️ | **Async ingestion** | Upload returns instantly; extraction, embedding and analysis run in the background with a live progress bar. |
| 🧪 | **Measured, not claimed** | 149 automated tests and a benchmark (28 questions, 4 documents) used to justify design choices. |

## Screenshots

<table>
  <tr>
    <td width="50%"><b>Dashboard: deadlines, calendar export, privacy scan</b><br><img src="docs/screenshots/01-dashboard.png"></td>
    <td width="50%"><b>Extracted facts (dates and amounts)</b><br><img src="docs/screenshots/02-extracted-facts.png"></td>
  </tr>
  <tr>
    <td><b>Document type and "what's missing" checklist</b><br><img src="docs/screenshots/03-insights-checklist.png"></td>
    <td><b>Privacy scan: identifiers shown masked only</b><br><img src="docs/screenshots/04-privacy-masked-ids.png"></td>
  </tr>
  <tr>
    <td><b>Answer check: figures found in the sources ✔</b><br><img src="docs/screenshots/05-answer-verified.png" width="60%"></td>
    <td><b>Answer check: a wrong figure is caught ✖</b> (the stubbed model says 18 months; no document contains it)<br><img src="docs/screenshots/06-answer-flagged.png" width="60%"></td>
  </tr>
</table>

## Architecture

<p align="center"><img src="docs/architecture.png" alt="Architecture" width="900"></p>

**Ingestion and query pipeline**

<p align="center"><img src="docs/pipeline.png" alt="Pipeline" width="900"></p>

**Stack:** React 18 + Vite · FastAPI · PostgreSQL · ChromaDB · Ollama (Llama 3.1 8B, Nomic embeddings) · Apache Tika · Docker Compose · pytest.

## Evaluation: one design choice, measured

*Question: what chunk size should the RAG pipeline use?* BM25 retrieval, top-3, 24 answerable questions (direct + paraphrased) over 4 documents. A question is a *hit* when a retrieved passage comes from the right document and contains the gold evidence. Reproduce: `python eval/offline_chunk_experiment.py`.

| chunk size | LLM context (chars) | hit@1 | hit@3 | MRR@3 | hit@3 paraphrased |
|---|---:|---:|---:|---:|---:|
| 200 | 457 | 50% | 62% | 0.56 | 27% |
| 500 | 1123 | 58% | 83% | 0.69 | 64% |
| 800 | 1711 | 67% | 92% | 0.78 | 82% |
| **1000 (chosen)** | 2346 | 75% | 96% | 0.83 | 91% |
| 1500 | 3267 | 88% | 96% | 0.92 | 91% |
| 3000 | 5495 | 100% | 100% | 1.00 | 100% |

**Conclusion:** bigger chunks score higher, but the metric ignores their cost. At 3000 characters each document is a single chunk, so "hit" only means BM25 picked the right document, and the model must read ~5,500 characters per question. **1000 characters keeps 96% hit@3 at less than half that context**, so it is the default. Heavy overlap hurts (250-char overlap on 500-char chunks drops hit@3 to 67%) because near-duplicate chunks crowd the top-3. With 24 questions, one question ≈ 4 points, so differences under ~10 points are noise.

`eval/run_eval.py` runs the same benchmark against the live stack to compare **lexical vs vector vs hybrid** retrieval and score generated answers (keyword correctness, grounding, refusal on unanswerable questions, latency).

## Quick start

Requires Docker Desktop (about 10 GB free disk, 8 GB+ RAM). Ollama runs inside Docker and pulls the models on first start.

```bash
cp .env.example .env          # set the three CHANGE_ME values
docker compose up --build -d
docker compose logs -f ollama-models   # first run only: wait for both models to download
```

Open **http://localhost:3000** and log in with `DOCLOCK_USERNAME` / `DOCLOCK_PASSWORD` from `.env`.
To store a **hashed** password instead of plain text: `python backend/hash_password.py` (PBKDF2-SHA256, 310k rounds), then paste the output into `.env` (escape each `$` as `$$` in compose files).
Try it with the files in `eval/corpus/` and `samples/synthetic_kyc.txt` (fake Aadhaar/PAN to demo the privacy scan).

Windows helpers: `start-doclock.ps1`, `STOP-DOCLOCK.ps1`, `test-doclock.ps1` (end-to-end smoke test).

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest
```

149 tests, no network or GPU needed (SQLite plus fakes for Ollama, Chroma and Tika). They cover chunking, BM25/RRF ranking, all three retrieval modes and their fallbacks, date and amount extraction, grounding of LLM output, alert logic, auth (hashing, JWT, expiry, rate limiting), the Verhoeff checksum (against its published worked example), answer verification, `.ics` output, and the full upload → process → facts → chat API flow.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/login` | JWT login (rate-limited) |
| POST / GET | `/api/documents` | Upload (202, background processing) / list with status |
| GET | `/api/documents/{id}` · `/content` · `/facts` · `/view` · `/download` | Details, text, facts, preview, file |
| GET | `/api/documents/{id}/insights` · `/redacted` | Type + checklist + masked identifiers · redacted text |
| POST | `/api/retrieve` | Retrieval only (`lexical` / `vector` / `hybrid`) |
| POST | `/api/chat` | Grounded answer, citations, and `verification` |
| GET / PATCH | `/api/alerts` · `/api/alerts/{id}` | Deadlines + summary · dismiss/restore |
| GET | `/api/alerts/calendar.ics` | Deadlines as an iCalendar file |
| GET | `/api/privacy` | Vault-wide privacy report (counts, masked) |

## Project structure

```
backend/app/        config, db, models, schemas, security, main
  routers/          auth, documents, chat, alerts, privacy
  services/         chunking, extraction, embeddings, vectorstore, retrieval, ranking, llm, facts,
                    ingestion, verify (answer check), pii, doctype, calendar_ics
backend/tests/      pytest suite (149 tests)
frontend/src/       React app
eval/               corpus, questions.json, offline_chunk_experiment.py, run_eval.py
samples/            synthetic_kyc.txt (fake identifiers for the privacy demo)
docs/               diagrams (.mmd sources), demo.gif, screenshots, record_demo.py
```

## Engineering decisions worth discussing

- **Hybrid retrieval:** embeddings handle paraphrase, BM25 handles exact numbers and names; reciprocal rank fusion needs no score calibration.
- **Grounding LLM-extracted facts:** every value the LLM returns must appear in the document text or it is discarded, which turns a hallucination risk into a checkable output.
- **Deterministic answer check instead of an LLM judge:** cheap, reproducible, and explainable; it targets the failure that matters most for personal documents (wrong figures).
- **Verhoeff checksum for Aadhaar:** removes most false positives from plain 12-digit numbers without any ML.
- **Privacy by design:** identifiers are detected on demand and returned masked; raw values are never stored in a separate table or shown in reports.
- **Chunk size 1000, not the highest-scoring 3000:** the benchmark ignores context cost, so the table reports it explicitly.

## Limitations (honest)

- Single user; one configured account. Not multi-tenant.
- Background tasks run in-process (FastAPI `BackgroundTasks`). A restart marks interrupted documents FAILED; a task queue (Celery/RQ) is the production answer.
- Extraction is heuristic. Regex + LLM can miss or misclassify dates, so the UI says "verify against the original". Scanned documents need OCR (not included).

## Roadmap

Task queue for ingestion · OCR for scanned documents · multi-user isolation · LLM-as-judge and a larger benchmark · semantic (not just numeric) claim checking · regional-language (Tamil) documents.

---

<p align="center">Built by Gangalakshmi Raja</p>