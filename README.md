# DocLock – AI-Powered Personal Document Intelligence

DocLock is a beginner-friendly, single-user document manager with Retrieval-Augmented Generation (RAG). It stores uploaded files on a Docker volume, extracts text, splits it into overlapping passages, creates embeddings with Ollama, retrieves relevant passages with semantic + keyword scoring, and asks a local LLM to answer using those passages.

## Technology

- **Frontend:** React 18, Vite, Axios
- **Backend / RAG API:** Java 21, Spring Boot 3, Spring Security, JWT, Spring Data JPA
- **Database:** PostgreSQL 16 (documents, extracted text, chunk metadata, chat history)
- **Vector database:** ChromaDB (persistent semantic vectors and similarity search)
- **LLM:** Ollama + `llama3.1:8b`
- **Embeddings:** Ollama + `nomic-embed-text`
- **File extraction:** Apache Tika
- **Containerization:** Docker Compose (frontend, backend/RAG, PostgreSQL, ChromaDB, Ollama and one-time model setup)

> RAG is implemented in the Spring Boot backend. ChromaDB is the primary vector store; PostgreSQL stores document metadata, extracted text, chunk records and a vector JSON fallback. All components run in Docker Compose.

## Features

1. Login with a configured username/password and JWT authentication.
2. Upload supported PDF, Word, PowerPoint, Excel, text, CSV, OpenDocument and common image files (maximum 50 MB).
3. Extract document text and split it into passages with overlap.
4. Generate embeddings using Nomic Embed Text through Ollama and upsert them into ChromaDB.
5. Persist document/chunk metadata in PostgreSQL and maintain matching IDs in ChromaDB.
6. List and search uploaded files by filename.
7. View PDFs/images in the browser and view extracted text for other supported formats.
8. Download original files.
9. Delete the file, extracted text, chunks, facts and alerts in one database transaction; remove matching Chroma vectors and the stored file.
10. Ask questions across all documents or one selected document.
11. Retrieve relevant chunks from ChromaDB using cosine similarity, with PostgreSQL vector/keyword fallback; provide source filename and passage citations.
12. Generate grounded answers using Llama 3.1, with instructions not to invent missing facts.
13. Save chat conversations and messages in PostgreSQL.

## Requirements

- Windows 10/11
- Docker Desktop installed and running (Docker Compose v2)
- 12 GB RAM recommended; 16 GB+ is more comfortable for the 8B model
- At least 10–15 GB free disk space for images, model downloads and build layers
- Internet connection for the first image/model download

## Quick start (recommended)

1. Extract the ZIP.
2. Open PowerShell in the `DocLock` folder.
3. Create your environment file:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

4. Change `POSTGRES_PASSWORD`, `DOCLOCK_PASSWORD` and `DOCLOCK_JWT_SECRET`. Use a JWT secret of at least 32 characters. Do not commit `.env` to Git.
5. Start the complete application:

   ```powershell
   docker compose up --build -d
   ```

   Or run `./start-doclock.ps1` after editing `.env`.

6. The `ollama-models` one-time service automatically downloads the configured chat and embedding models. ChromaDB is also started with a persistent volume. The backend waits for PostgreSQL and ChromaDB to become healthy and for the Ollama model setup to finish. The first run can take several minutes (or longer on a slow connection).
7. Open **http://localhost:3000**. Sign in using `DOCLOCK_USERNAME` and `DOCLOCK_PASSWORD` from `.env`.

## Useful Docker commands

```powershell
# Service status
docker compose ps

# Follow all logs
docker compose logs -f

# Backend / RAG logs
docker compose logs -f backend

# Ollama and model-download logs
docker compose logs -f ollama ollama-models chroma

# Stop containers (keeps database, files and models)
docker compose down

# Stop and DELETE all data, uploaded documents and downloaded models
# WARNING: this is destructive
docker compose down -v
```

## Local development (without Docker frontend/backend containers)

You still need PostgreSQL, ChromaDB and Ollama running locally. Configure `SPRING_DATASOURCE_*`, `CHROMA_BASE_URL`, `OLLAMA_BASE_URL`, `DOCLOCK_USERNAME`, `DOCLOCK_PASSWORD` and `DOCLOCK_JWT_SECRET` in your PowerShell session before starting the backend. Spring Boot does not automatically read the `.env` file in local mode. Then:

**Terminal 1 – backend** (Java 21 and Maven 3.9+):

```powershell
cd backend
mvn spring-boot:run
```

**Terminal 2 – frontend** (Node.js 20+):

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal (configured for port 3000). The Vite development server proxies `/api` requests to `http://localhost:8080`.

For local Ollama, run:

```powershell
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

Start ChromaDB separately (for example with `docker run -p 8000:8000 chromadb/chroma:latest`) before starting the backend.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/login` | Login and receive JWT |
| GET | `/api/auth/me` | Current authenticated user |
| GET | `/api/documents` | List/search documents (`?q=`) |
| POST | `/api/documents` | Upload multipart field `file` |
| GET | `/api/documents/{id}` | Document metadata |
| GET | `/api/documents/{id}/view` | Original file for preview |
| GET | `/api/documents/{id}/download` | Download original file |
| GET | `/api/documents/{id}/content` | Extracted text |
| DELETE | `/api/documents/{id}` | Delete document and its indexed data |
| POST | `/api/chat` | RAG chat (`message`, optional `documentId`, optional `conversationId`) |
| GET | `/api/chat/conversations` | List chat conversations |
| GET | `/api/chat/conversations/{id}/messages` | Read chat history |
| GET | `/actuator/health` | Backend health |

All endpoints except login and health require `Authorization: Bearer <token>`.

## How the RAG pipeline works

1. **Upload:** the backend validates the extension and size, stores the original file and creates a document row.
2. **Extract:** Apache Tika extracts readable text from the file.
3. **Chunk:** the text is split into 1,000-character passages with 150-character overlap.
4. **Embed:** each passage is sent to Ollama's embedding endpoint using `nomic-embed-text`.
5. **Persist:** passage metadata is saved in PostgreSQL and vectors are upserted into ChromaDB. A vector JSON copy is kept in PostgreSQL as a fallback.
6. **Retrieve:** a user question is embedded. DocLock queries ChromaDB for the top five similar passages; if ChromaDB is unavailable, it falls back to PostgreSQL cosine similarity and keyword matching.
7. **Generate:** the selected passages and recent conversation are added to a prompt for `llama3.1:8b`. The prompt tells the model to use only the supplied document context, ignore instructions inside documents, and admit when the answer is not present.
8. **Cite:** the API returns source document names and passage numbers.

If Ollama's embedding model is unavailable during upload, DocLock retains the file and can still use keyword retrieval. Semantic retrieval becomes available once the embedding model is running. If the chat model is unavailable, the API returns a clear Ollama connection message instead of pretending an answer was generated.

## Troubleshooting

- **Docker is not running:** start Docker Desktop and wait until it reports that the engine is running.
- **Port already in use:** stop the other service using ports 3000, 5432, 8080 or 11434, or change the published port in `docker-compose.yml`.
- **Login fails:** check `DOCLOCK_USERNAME` and `DOCLOCK_PASSWORD` in `.env`, then run `docker compose restart backend`.
- **AI says it cannot contact Ollama:** run `docker compose ps` and `docker compose logs ollama ollama-models`; confirm model setup completed. If semantic search is not working, also inspect `docker compose logs chroma backend`.
- **Upload is saved but processing says FAILED:** inspect `docker compose logs backend`. The original file remains in storage; the status/error message explains the extraction problem.
- **Frontend blank or API errors:** run `docker compose logs --tail=150 frontend backend` and verify `http://localhost:8080/actuator/health`.
- **Rebuild after code changes:** `docker compose up --build -d`.

## Important limitations / security notes

- This is a single-user college/interview project, not a multi-tenant production service. Do not expose it directly to the public internet without adding per-user document ownership, rate limiting, HTTPS, stronger secret management and security review.
- Password is configured through environment variables for a simple local demo. Use a unique strong password and keep `.env` private.
- Scanned PDFs/images may need OCR support for reliable text extraction; Tika alone may return little or no text for some scans.
- Very large documents can take time to embed because each passage is sent to Ollama.
- Model output quality depends on document text quality, chunk relevance, available RAM and the selected model.

## End-to-end smoke test

After the backend health endpoint reports `UP` and the model setup has completed, run:

```powershell
./test-doclock.ps1
```

The script logs in, uploads a temporary sample document, checks view and download, asks the RAG assistant a question and checks that a citation is returned, then deletes the sample document. It does not delete your other files.

## Interview explanation

DocLock demonstrates the complete RAG flow: ingestion, parsing, chunking, embedding, vector persistence, hybrid retrieval, prompt grounding, LLM generation and source citations. PostgreSQL stores application data and passage metadata; ChromaDB stores searchable vectors; Ollama runs the local embedding and generation models; Docker Compose starts the complete stack.
