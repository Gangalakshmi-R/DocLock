-- DocLock PostgreSQL Initial Database Schema

CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size BIGINT NOT NULL,
    storage_path VARCHAR(1024) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'UPLOADING',
    error_message TEXT,
    page_count INT,
    file_hash VARCHAR(64),
    category VARCHAR(50),
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_contents (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT UNIQUE NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    extracted_text TEXT NOT NULL,
    word_count INT
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    page_number INT,
    vector_id VARCHAR(128),
    vector_json TEXT,
    start_char INT,
    end_char INT
);

CREATE TABLE IF NOT EXISTS document_facts (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    fact_type VARCHAR(50) NOT NULL,
    key_name VARCHAR(100) NOT NULL,
    value TEXT NOT NULL,
    page_number INT
);

CREATE TABLE IF NOT EXISTS document_alerts (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    deadline_date DATE NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_conversations (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_facts_doc_id ON document_facts(document_id);
CREATE INDEX IF NOT EXISTS idx_alerts_deadline ON document_alerts(deadline_date);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON chat_messages(conversation_id);
