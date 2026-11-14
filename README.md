# DocLock – AI-Powered Personal Document Assistant

DocLock is a private, self-hosted AI document management platform that helps users securely store, manage and understand their personal documents.

It uses AI to answer questions from uploaded documents, extract important information, track deadlines and protect sensitive personal data.

## Features

- **Document Management:** Upload, view, preview, download and delete documents.
- **AI Document Chat:** Ask questions about uploaded documents and receive answers with source references.
- **Smart Information Extraction:** Extract important dates, amounts and other details.
- **Deadline Alerts:** Get notifications about upcoming deadlines and document expiry dates.
- **Privacy Protection:** Detect and mask sensitive information such as Aadhaar, PAN, GSTIN and phone numbers.
- **Document Analysis:** Identify document types and highlight missing information.
- **Answer Verification:** Check whether numbers and dates in AI-generated answers are supported by the original documents.
- **Hybrid Search:** Combine keyword and vector search for better document retrieval.
- **Background Processing:** Process uploaded documents asynchronously.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React 18, Vite |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Vector Database | ChromaDB |
| LLM | Ollama – Llama 3.1 8B |
| Embeddings | Nomic Embed Text |
| Document Extraction | Apache Tika |
| AI Architecture | RAG |
| Deployment | Docker Compose |
| Testing | Pytest |

## Project Architecture

DocLock follows a Retrieval-Augmented Generation (RAG) architecture.

1. Users upload their documents.
2. The backend extracts the document content.
3. The content is divided into smaller chunks.
4. Embeddings are generated and stored in ChromaDB.
5. When a user asks a question, relevant information is retrieved.
6. The LLM generates an answer based on the retrieved content.
7. Source references and answer verification are provided.

## Installation and Setup

### Requirements

- Python 3.11+
- Docker Desktop
- Node.js
- Git

### Run the Project

Clone the repository:

```bash
git clone <repository-url>
cd DocLock
```

Create the environment file:

```bash
cp .env.example .env
```

Configure the required credentials in `.env`.

Start the application:

```bash
docker compose up --build -d
```

Wait for the Ollama models to download:

```bash
docker compose logs -f ollama-models
```

Open the application:

**http://localhost:3000**

Log in using the username and password configured in your environment file.

## Running Tests

Navigate to the backend:

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

The project includes 149 automated tests covering document processing, retrieval, authentication, privacy scanning, alerts and AI answer verification.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/login` | User authentication |
| POST / GET | `/api/documents` | Upload and list documents |
| GET | `/api/documents/{id}` | View document details |
| GET | `/api/documents/{id}/facts` | Extracted information |
| POST | `/api/chat` | AI document chat |
| POST | `/api/retrieve` | Document retrieval |
| GET | `/api/alerts` | View deadline alerts |
| GET | `/api/privacy` | Privacy report |

## Project Structure

```text
DocLock/
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   ├── services/
│   │   ├── models/
│   │   └── main.py
│   └── tests/
├── frontend/
│   └── src/
├── eval/
├── samples/
├── docs/
├── docker-compose.yml
└── .env.example
```

## Future Enhancements

- OCR support for scanned documents.
- Tamil and regional language support.
- Multi-user authentication and access control.
- Improved document intelligence.
- Background task queue for large document processing.

## Current Limitations

- Currently supports a single configured user account.
- Background processing can be interrupted if the application restarts.
- Extracted information should be verified against the original document.
- OCR support for scanned documents is a planned enhancement.

---

**Developed by Gangalakshmi Raja**

*DocLock – Your documents, your privacy, your AI assistant.*
