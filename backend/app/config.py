"""
Centralized configuration for the RAG chatbot backend.
All settings are loaded from environment variables (see .env.example).
"""
import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "Advanced RAG Chatbot"
    ENVIRONMENT: str = "development"  # development | production
    DEBUG: bool = True

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- CORS (widget must be embeddable on ANY website) ---
    ALLOWED_ORIGINS: str = "*"
    # --- LLM Provider ---
    # One of: "gemini", "openai", "anthropic"
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-2.5-flash"
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_RETRIES: int = 3

    # --- Embeddings (local, free, no API key needed) ---
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Vector store ---
    # NOTE: vectors are stored directly in Postgres (see database.py ->
    # VectorStoreManager) using DATABASE_URL below. This replaced ChromaDB
    # (both local-disk and Chroma Cloud variants), which proved unreliable
    # on Railway's free tier: local disk is ephemeral and wiped on every
    # redeploy, and Chroma Cloud repeatedly hit client/server version
    # mismatches outside our control. Postgres is already required for the
    # bot registry, so reusing it removes an entire external dependency.

    # --- Bot registry + vector store database (persistent across redeploys) ---
    # Auto-injected by Railway once you add the PostgreSQL plugin --
    # no need to set this manually.
    DATABASE_URL: str = ""

    # --- Ingestion ---
    UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150
    MAX_FILE_SIZE_MB: int = 25
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".docx", ".txt", ".md", ".csv"]

    # --- Conversation memory ---
    MAX_HISTORY_TURNS: int = 8
    SESSION_TTL_SECONDS: int = 60 * 60 * 6  # 6 hours

    # --- Retrieval ---
    RETRIEVAL_TOP_K: int = 4

    # --- Security ---
    # API keys are generated per-bot and required by the widget to query it.
    ADMIN_API_KEY: str = "change-this-admin-key"

    # --- Rate limiting ---
    RATE_LIMIT_PER_MINUTE: int = 60

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = str(BASE_DIR / "data" / "logs")


settings = Settings()

# Ensure required directories exist at import time (self-healing on fresh deploys)
for d in [settings.UPLOAD_DIR, settings.LOG_DIR]:
    os.makedirs(d, exist_ok=True)