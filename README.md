# DocLock – AI-Powered Personal Document Intelligence

DocLock is an AI-powered personal document management platform built around Retrieval-Augmented Generation (RAG). Users upload documents, DocLock extracts and chunks their text, creates embeddings with Ollama, retrieves relevant passages from ChromaDB, and asks a local LLM to answer using the retrieved document context with source citations.

## Technology stack

- **Frontend:** React 18, Vite, Axios (unchanged)
- **Backend / RAG API:** Python 3.11, FastAPI, Pydantic, SQLAlchemy, JWT
- **Database:** PostgreSQL 16
- **Vector database:** ChromaDB (persistent)
- **LLM:** Ollama + Llama 3.1 8B
- **Embeddings:** Ollama + Nomic Embed Text
- **Document extraction:** Apache Tika Server
- **Containerization:** Docker Compose

## Features

- JWT-protected single-user login.
- Upload PDF, Word, PowerPoint, Excel, CSV, text, OpenDocument and common image formats (50 MB maximum).
- Extract text through Apache Tika; split text into 1,000-character passages with 150-character overlap.
- Generate embeddings using Nomic Embed Text through Ollama.
- Persist vector records in ChromaDB and passage metadata / vector fallback in PostgreSQL.
- Search, preview, download and delete documents.
- Ask questions across all documents or a selected document.
- Retrieve with ChromaDB semantic search and PostgreSQL cosine/keyword fallback.
- Generate grounded answers with Llama 3.1 and return source filename / passage citations.
- Store conversation and message history in PostgreSQL.

## Requirements

- Windows 10/11, Docker Desktop with Compose v2
- 16 GB RAM recommended for Llama 3.1 8B; more memory improves the experience
- 15–20 GB free disk space for images, models and build layers
- Internet connection for initial image and model downloads

## Quick start (Windows PowerShell)

1. Extract the ZIP and open PowerShell in the `DocLock` folder.
2. Create your local environment file:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

3. Replace all `CHANGE_ME` values. Use a strong PostgreSQL password, a strong DocLock login password, and a random JWT secret of at least 32 characters. Never commit `.env`.
4. Start Docker Desktop and wait until its engine is running.
5. Start the complete stack:

   ```powershell
   docker compose up --build -d
   ```

   Or run `./start-doclock.ps1` after configuring `.env`.
6. The `ollama-models` one-shot service downloads `llama3.1:8b` and `nomic-embed-text`. The first startup may take a while.
7. Open **http://localhost:3000** and sign in using `DOCLOCK_USERNAME` and `DOCLOCK_PASSWORD` from `.env`.

## Useful commands

```powershell
# Service status
docker compose ps

# Follow all logs
docker compose logs -f

# FastAPI backend logs
docker compose logs -f backend

# Ollama and model setup logs
docker compose logs -f ollama ollama-models

# ChromaDB and Apache Tika logs
docker compose logs -f chroma tika

# Stop containers (preserves volumes)
docker compose down

# WARNING: permanently deletes database, uploaded files, Chroma vectors and Ollama models
docker compose down -v
```

## Local backend development (optional)

PostgreSQL, ChromaDB, Ollama and Apache Tika must be running. Create a Python virtual environment and set the environment variables used in `.env` in your PowerShell session; Python does not automatically load `.env` here.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

The Vite development server runs at `http://localhost:3000` and proxies `/api` to `http://localhost:8080`.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/login` | Login and receive JWT |
| GET | `/api/auth/me` | Current authenticated user |
| GET | `/api/documents?q=` | List/search documents |
| POST | `/api/documents` | Upload multipart field `file` |
| GET | `/api/documents/{id}` | Document metadata |
| GET | `/api/documents/{id}/view` | Original file preview |
| GET | `/api/documents/{id}/download` | Download original file |
| GET | `/api/documents/{id}/content` | Extracted text |
| DELETE | `/api/documents/{id}` | Delete document and indexed data |
| POST | `/api/chat` | RAG chat (`message`, optional `documentId`, optional `conversationId`) |
| GET | `/api/chat/conversations` | List conversations |
| GET | `/api/chat/conversations/{id}/messages` | Conversation history |
| GET | `/actuator/health` | Backend health |

All endpoints except login and health require `Authorization: Bearer <token>`.

## RAG pipeline

1. FastAPI validates and stores the uploaded file.
2. Apache Tika extracts readable text.
3. The text is split into overlapping passages.
4. Ollama creates passage embeddings with Nomic Embed Text.
5. Passage metadata and fallback vectors are stored in PostgreSQL; vectors are upserted to ChromaDB.
6. A question is embedded and ChromaDB returns the most relevant passages. PostgreSQL cosine similarity plus keyword matching is used when Chroma is unavailable or no mapped results are found.
7. The retrieved context and recent chat history are sent to Llama 3.1 8B through Ollama.
8. The API returns the answer and authoritative source citations.

If Ollama embeddings are unavailable during upload, the original file and extracted text remain saved; keyword retrieval can still be used. If Ollama generation is unavailable, the chat API returns a clear service error rather than fabricating an answer.

## Smoke test

After `docker compose ps` shows the backend healthy and the model setup has completed, run:

```powershell
./test-doclock.ps1
```

The script logs in, uploads a temporary text file, checks preview and download, asks a RAG question, verifies citations and deletes only its temporary test document.

## Security and limitations

- This is a single-user college/interview project, not a multi-tenant production service.
- Do not expose it publicly without HTTPS, stronger access controls, rate limiting, secure secret management, backups and a security review.
- Keep `.env` private. Rotate credentials and JWT secrets if exposed or committed.
- OCR quality for scanned documents depends on the Tika image/OCR capabilities available in the configured Tika image.
- Llama 3.1 8B can be slow on CPU-only hardware and needs significant memory.
- Docker Compose uses persistent named volumes. Back up PostgreSQL, uploaded-file and ChromaDB volumes before destructive changes.

## Interview explanation

DocLock demonstrates document ingestion, parsing, chunking, embedding generation, vector persistence, hybrid retrieval, prompt grounding, local LLM inference and source citations. FastAPI orchestrates the RAG workflow; PostgreSQL stores application data and passage metadata; ChromaDB provides vector similarity search; Ollama runs local embedding and generation models; Apache Tika extracts document text; Docker Compose integrates the services.
