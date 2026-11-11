# Final Review Checklist

## Implemented in this release

- [x] React frontend and Spring Boot backend are both Dockerized.
- [x] PostgreSQL database runs in Docker with a persistent named volume.
- [x] Ollama LLM and embedding server run in Docker with persistent model storage.
- [x] ChromaDB runs in Docker with a persistent vector collection.
- [x] A one-time Docker service downloads the configured Llama and Nomic models.
- [x] RAG ingestion: text extraction, overlapping chunks and embeddings.
- [x] RAG retrieval: ChromaDB semantic similarity with PostgreSQL semantic/keyword fallback.
- [x] Grounded LLM prompt and source filename/passage citations.
- [x] Upload, list, filename search, view, download and delete endpoints.
- [x] Deletion removes related database rows in the same transaction and deletes the file after commit.
- [x] JWT login, API error responses and health endpoint.
- [x] Beginner-oriented README, PowerShell startup and troubleshooting instructions.

## Checks completed in this environment

- [x] ZIP source extracted and project files reviewed.
- [x] `frontend/package.json` parses as valid JSON.
- [x] `backend/pom.xml` parses as valid XML.
- [x] `docker-compose.yml` parses as valid YAML and contains all six application services.
- [x] Plain JavaScript files pass Node syntax checks.

## Checks that still require the user's Windows + Docker environment

- [ ] Build the Spring Boot container (Maven dependencies must be downloaded).
- [ ] Build the React container (npm dependencies must be downloaded).
- [ ] Start PostgreSQL, ChromaDB and Ollama containers.
- [ ] Confirm model downloads finish successfully.
- [ ] Perform an end-to-end upload, view, download and delete test.
- [ ] Ask a question whose answer is in an uploaded document and verify the citation.

A project ZIP cannot truthfully be labelled 100% runtime-verified until these end-to-end checks pass on a machine with Docker and the required model downloads available.
