# DocLock — 5-minute Generative AI interview explanation

## 1. What does the application do?

DocLock is a personal document management application. A user uploads documents, and the application extracts text, indexes it and lets the user ask natural-language questions about the uploaded files.

## 2. Which technologies did I use?

- Frontend: React, Vite and Axios.
- Backend: Java 21, Spring Boot REST APIs and Spring Data JPA.
- Database: PostgreSQL for document metadata, extracted text, chunk records and chat history.
- Vector database: ChromaDB for semantic vector storage and similarity search.
- Document extraction: Apache Tika.
- Embeddings: Ollama with `nomic-embed-text`.
- LLM: Ollama with `llama3.1:8b`.
- Authentication: JWT.
- Local deployment: Docker Compose (frontend, backend/RAG, PostgreSQL, ChromaDB, Ollama and model setup containers).

## 3. Explain the RAG pipeline

1. The user uploads a PDF, Word, PowerPoint, Excel or text document.
2. Spring Boot stores the original file and Apache Tika extracts its text.
3. The text is divided into chunks of about 1,000 characters with 150 characters of overlap.
4. Nomic Embed Text converts each chunk into a vector embedding.
5. PostgreSQL stores each chunk and its vector representation.
6. When the user asks a question, DocLock embeds the question and compares it with stored chunk vectors using cosine similarity. It also scores keyword overlap.
7. The best matching passages are added to a prompt with the question.
8. Llama 3.1 generates an answer using the retrieved context. The API returns source filenames and passage numbers.

This is Retrieval-Augmented Generation: retrieval finds relevant external context before the LLM generates its response.

## 4. Why use chunking and overlap?

A complete document may be too large to send to an LLM in one prompt. Chunking creates smaller searchable units. Overlap preserves context that might otherwise be lost when a sentence or topic crosses a chunk boundary.

## 5. Why embeddings?

Keyword search only finds exact or similar words. Embeddings represent semantic meaning, so a question can retrieve a passage even when the wording is different. DocLock combines semantic similarity and keyword matching.

## 6. What happens if the answer is not in a document?

If no relevant passage is retrieved, DocLock returns a message saying it could not find the information instead of asking the LLM to guess. The prompt also instructs the model to use only the supplied document context.

## 7. Demo sequence

1. Start Docker Desktop.
2. Run `docker compose up --build -d`.
3. Wait for the `ollama-models` setup service to download `llama3.1:8b` and `nomic-embed-text`.
4. Open `http://localhost:3000` and sign in using credentials from `.env`.
5. Upload a text-based PDF or DOCX and wait for status `PROCESSED`.
6. Click **View** to preview PDF/text or see extracted text for Office documents.
7. Ask a question whose answer is clearly present in the document.
8. Show the generated answer and retrieved source citations.
9. Delete the document and show that it disappears from the list and retrieval index.

## 8. Be accurate about the implementation

ChromaDB is the primary vector store. PostgreSQL keeps document/chunk records and a JSON vector fallback so retrieval can continue if ChromaDB is unavailable. Scanned PDF/image OCR is not configured. It is a local academic/demo project with one configured login, not a production multi-user vault.
