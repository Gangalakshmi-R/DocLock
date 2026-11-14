"""Central configuration. Everything is read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.engine import URL


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASE_CONNECTION = DATABASE_URL
else:
    DATABASE_CONNECTION = URL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "doclock_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "doclock"),
    )

# --- Auth -------------------------------------------------------------------
USERNAME = os.getenv("DOCLOCK_USERNAME", "admin")
PASSWORD = os.getenv("DOCLOCK_PASSWORD", "")
JWT_SECRET = os.getenv("DOCLOCK_JWT_SECRET", "")
JWT_EXPIRATION_MS = int(os.getenv("DOCLOCK_JWT_EXPIRATION", "86400000"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("DOCLOCK_LOGIN_MAX_ATTEMPTS", "8"))
LOGIN_WINDOW_SECONDS = int(os.getenv("DOCLOCK_LOGIN_WINDOW_SECONDS", "300"))

# --- Storage / upload ---------------------------------------------------------
STORAGE_DIR = Path(os.getenv("DOCLOCK_STORAGE_DIR", "/var/doclock/storage")).resolve()
MAX_FILE_SIZE = int(os.getenv("DOCLOCK_MAX_FILE_SIZE", str(50 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".txt", ".rtf", ".ppt", ".pptx", ".xls", ".xlsx",
    ".csv", ".html", ".htm", ".xml", ".odt", ".ods", ".odp", ".png", ".jpg",
    ".jpeg", ".gif", ".bmp", ".tif", ".tiff",
}
# Types the browser may render inline. Everything else is always served as a download.
INLINE_PREVIEW_TYPES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}
PLAIN_TEXT_EXTENSIONS = {".txt", ".csv"}  # read directly, no Tika round-trip

# --- External services ----------------------------------------------------------
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "512"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_GENERATION_TIMEOUT = int(os.getenv("OLLAMA_GENERATION_TIMEOUT", "300"))
CHROMA_URL = os.getenv("CHROMA_BASE_URL", "http://chroma:8000").rstrip("/")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "doclock_vectors")
TIKA_URL = os.getenv("TIKA_URL", "http://tika:9998").rstrip("/")

# --- OCR ---------------------------------------------------------------------------
OCR_ENABLED = _bool("DOCLOCK_OCR_ENABLED", True)
OCR_LANG = os.getenv("DOCLOCK_OCR_LANG", "eng+tam")
OCR_DPI = int(os.getenv("DOCLOCK_OCR_DPI", "220"))
OCR_MIN_PAGE_CHARS = int(os.getenv("DOCLOCK_OCR_MIN_PAGE_CHARS", "30"))
OCR_TIMEOUT_SECONDS = int(os.getenv("DOCLOCK_OCR_TIMEOUT_SECONDS", "90"))

# --- RAG tuning -----------------------------------------------------------------
CHUNK_SIZE = int(os.getenv("DOCLOCK_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("DOCLOCK_CHUNK_OVERLAP", "150"))
EMBED_BATCH_SIZE = int(os.getenv("DOCLOCK_EMBED_BATCH_SIZE", "16"))
# Variable names match the v2.0 .env (DOCLOCK_RETRIEVAL_TOP_K, DOCLOCK_MAX_CONTEXT_CHARS); the older short names still work.
RETRIEVAL_TOP_K = int(os.getenv("DOCLOCK_RETRIEVAL_TOP_K", os.getenv("DOCLOCK_TOP_K", "5")))
DEFAULT_RETRIEVAL_MODE = os.getenv("DOCLOCK_RETRIEVAL_MODE", "hybrid")  # hybrid | vector | lexical
CONTEXT_CHAR_BUDGET = int(os.getenv("DOCLOCK_MAX_CONTEXT_CHARS", os.getenv("DOCLOCK_CONTEXT_CHARS", "9000")))

# --- Document intelligence ---------------------------------------------------------
LLM_FACTS_ENABLED = _bool("DOCLOCK_LLM_FACTS", True)
DATES_DAY_FIRST = _bool("DOCLOCK_DATES_DAY_FIRST", True)  # 03/04/2026 -> 3 April (Indian/UK style)
ALERT_WINDOW_DAYS = int(os.getenv("DOCLOCK_ALERT_WINDOW_DAYS", "30"))

# --- HTTP ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    x.strip()
    for x in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if x.strip()
]

if not PASSWORD:
    print("WARNING: DOCLOCK_PASSWORD is empty. Set it in your .env before using the app.")
if len(JWT_SECRET) < 32:
    print("WARNING: DOCLOCK_JWT_SECRET should be at least 32 characters. Set a strong secret in .env.")
