"""
- BotRegistry: Postgres-backed store for per-bot configuration. Unchanged
  from the previous fix -- this has been working reliably.

- VectorStoreManager: previously ChromaDB (first a local PersistentClient,
  wiped by Railway's ephemeral disk; then Chroma Cloud, which kept
  crashing with client/server schema mismatches -- a bug on Chroma's side,
  entirely outside our control, that kept resurfacing after every
  "matching" version pin).

  Replaced with a small, dependency-free vector store built directly on
  the same Postgres database already powering BotRegistry: each chunk's
  embedding is stored as a plain DOUBLE PRECISION[] array column, and
  similarity search is brute-force cosine similarity computed in Python
  with numpy. For the corpus sizes a single embedded chatbot's knowledge
  base realistically holds (a handful of documents, at most a few
  thousand chunks per bot), this comfortably runs in well under 100ms --
  and it completely removes the external vector-DB dependency, its
  version-compatibility risk, and any need for a Railway Volume or a
  separate Chroma Cloud account.
"""
import json
import secrets
import threading
from typing import List, Optional, Tuple

import numpy as np
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings
from app.utils.exceptions import BotNotFoundError, InvalidAPIKeyError
from app.utils.logger import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()

# Embedding model is loaded once and shared across the whole app (expensive to init).
_embeddings: Optional[HuggingFaceEmbeddings] = None


def get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        _embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
    return _embeddings


class BotRegistry:
    """
    Same public interface as before (create_bot, get_bot, verify_api_key,
    list_bots, delete_bot). Each bot is stored as one row: a unique bot_id
    column plus a JSONB column holding the rest of the bot's data.
    """

    def __init__(self, dsn: str = None):
        self.dsn = dsn or settings.DATABASE_URL
        if not self.dsn:
            raise RuntimeError(
                "DATABASE_URL is not set. Add a PostgreSQL plugin in Railway -- "
                "it injects this automatically."
            )
        self._init_table()

    def _connect(self):
        return psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)

    def _init_table(self):
        with _lock, self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bots (
                    bot_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL
                )
                """
            )
            conn.commit()

    def create_bot(self, name: str, welcome_message: str, primary_color: str, system_prompt: Optional[str]) -> dict:
        bot_id = secrets.token_hex(8)
        api_key = secrets.token_urlsafe(24)
        bot = {
            "bot_id": bot_id,
            "api_key": api_key,
            "name": name,
            "welcome_message": welcome_message,
            "primary_color": primary_color,
            "system_prompt": system_prompt or (
                "You are a helpful, friendly assistant embedded on a company website. "
                "Answer ONLY using the provided context. If the answer isn't in the "
                "context, politely say you don't have that information and suggest "
                "the visitor contact support. Keep answers concise and clear."
            ),
        }
        with _lock, self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bots (bot_id, data) VALUES (%s, %s)",
                (bot_id, json.dumps(bot)),
            )
            conn.commit()
        logger.info(f"Created bot {bot_id} ({name})")
        return bot

    def get_bot(self, bot_id: str) -> dict:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM bots WHERE bot_id = %s", (bot_id,))
            row = cur.fetchone()
        if not row:
            raise BotNotFoundError(bot_id)
        return row["data"]

    def verify_api_key(self, bot_id: str, api_key: str) -> dict:
        bot = self.get_bot(bot_id)
        if not secrets.compare_digest(bot["api_key"], api_key or ""):
            raise InvalidAPIKeyError()
        return bot

    def list_bots(self) -> list:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM bots")
            rows = cur.fetchall()
        return [row["data"] for row in rows]

    def delete_bot(self, bot_id: str):
        with _lock, self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM bots WHERE bot_id = %s", (bot_id,))
            conn.commit()
        # Also clean up that bot's knowledge base -- otherwise orphaned
        # chunks pile up in document_chunks forever.
        vector_store_manager.delete_collection(bot_id)


class VectorStoreManager:
    """
    One logical "collection" per bot_id, implemented as rows in a single
    Postgres table filtered by bot_id -- no external vector DB, no
    extension required, just the same Postgres already used for bots.
    """

    def __init__(self, dsn: str = None):
        self.dsn = dsn or settings.DATABASE_URL
        if not self.dsn:
            raise RuntimeError(
                "DATABASE_URL is not set. Add a PostgreSQL plugin in Railway -- "
                "it injects this automatically."
            )
        self._init_table()

    def _connect(self):
        return psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)

    def _init_table(self):
        with _lock, self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id SERIAL PRIMARY KEY,
                    bot_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB,
                    embedding DOUBLE PRECISION[] NOT NULL
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS document_chunks_bot_id_idx ON document_chunks (bot_id)"
            )
            conn.commit()

    def add_documents(self, bot_id: str, documents: list) -> int:
        if not documents:
            return 0
        embeddings_model = get_embeddings()
        texts = [doc.page_content for doc in documents]
        vectors = embeddings_model.embed_documents(texts)

        with _lock, self._connect() as conn, conn.cursor() as cur:
            for doc, vector in zip(documents, vectors):
                cur.execute(
                    "INSERT INTO document_chunks (bot_id, content, metadata, embedding) "
                    "VALUES (%s, %s, %s, %s)",
                    (bot_id, doc.page_content, Json(doc.metadata or {}), list(vector)),
                )
            conn.commit()
        return len(documents)

    def similarity_search(self, bot_id: str, query: str, k: int = None) -> List[Tuple[Document, Optional[float]]]:
        k = k or settings.RETRIEVAL_TOP_K
        embeddings_model = get_embeddings()
        query_vector = np.array(embeddings_model.embed_query(query))

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content, metadata, embedding FROM document_chunks WHERE bot_id = %s",
                (bot_id,),
            )
            rows = cur.fetchall()

        if not rows:
            return []

        query_norm = np.linalg.norm(query_vector)
        scored = []
        for row in rows:
            vec = np.array(row["embedding"])
            denom = query_norm * np.linalg.norm(vec)
            score = float(np.dot(query_vector, vec) / denom) if denom else 0.0
            doc = Document(page_content=row["content"], metadata=row["metadata"] or {})
            scored.append((doc, score))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]

    def delete_collection(self, bot_id: str):
        try:
            with _lock, self._connect() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM document_chunks WHERE bot_id = %s", (bot_id,))
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not delete document chunks for {bot_id}: {e}")


bot_registry = BotRegistry()
vector_store_manager = VectorStoreManager()