<h1 align="center">🔐 DocLock</h1>

<p align="center"><b>A private, self-hosted AI assistant for your personal documents.</b><br>
Ask questions with cited answers, verify every number, get deadline alerts, and mask Aadhaar/PAN.<br>
Everything runs locally. No document leaves your machine.</p>

<p align="center">
  <img alt="tests" src="https://img.shields.io/badge/tests-152%20passing-brightgreen">
  <img alt="python" src="https://img.shields.io/badge/Python-3.11+-blue">
  <img alt="fastapi" src="https://img.shields.io/badge/FastAPI-backend-009688">
  <img alt="react" src="https://img.shields.io/badge/React-18-61dafb">
  <img alt="docker" src="https://img.shields.io/badge/Docker-compose-2496ed">
</p>

<p align="center"><img src="docs/demo.gif" alt="DocLock demo" width="800"></p>

## Features

- **Cited Q&A (RAG):** hybrid search (vector + BM25, rank-fused) over one or all documents, with multi-turn chat and source citations.
- **Answer trust check:** every number and date in an answer is checked against the retrieved passages, and unverified figures are flagged. No second LLM call.
- **Deadline and expiry alerts:** dates and amounts are extracted (regex + LLM, grounded in the text) into OVERDUE / DUE SOON / UPCOMING alerts, exportable as a `.ics` calendar file.
- **Privacy scan:** detects Aadhaar (Verhoeff-validated), PAN, GSTIN, IFSC, phone and email. Values are shown masked only, with a one-click redacted copy.
- **Document type and checklist:** classifies the document (insurance, rental, fee circular, etc.) and lists expected clauses that are missing.
- **Automatic OCR:** scanned PDFs and images are read with Tesseract (English + Tamil).
- **Async ingestion:** uploads return instantly and process in the background with live status.
- **Secure login:** JWT, PBKDF2-hashed password option, login rate limiting.

## Tech stack

React 18 + Vite · FastAPI · PostgreSQL · ChromaDB · Ollama (Llama 3.1 8B, Nomic embeddings) · Apache Tika · PyMuPDF · Tesseract · Docker Compose


## Main API endpoints

| Path | Purpose |
|---|---|
| `POST /api/auth/login` | Log in |
| `POST /api/documents` | Upload (processed in background) |
| `POST /api/chat` | Cited answer + verification |
| `GET /api/alerts` · `/api/alerts/calendar.ics` | Deadlines · calendar export |
| `GET /api/privacy` | Vault-wide privacy report |
| `GET /api/documents/{id}/insights` | Type, checklist, masked IDs |


<p align="center">Built by Gangalakshmi Raja</p>
