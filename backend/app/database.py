"""
- BotRegistry: Postgres-backed store for per-bot configuration
  (name, API key, prompt, styling). Previously a flat JSON file, but that
  lived on Railway's ephemeral disk and got wiped on every redeploy.
  Now backed by Railway's Postgres plugin (DATABASE_URL is auto-injected
  once you add the Postgres service in Railway) -- a real, persistent store,
  while keeping the exact same public interface (`get_bot`, `create_bot`,
  etc.) so nothing else in the app needs to change.

- VectorStoreManager: wraps ChromaDB. Previously a local PersistentClient
  (also wiped on redeploy since Railway's app disk is ephemeral and no
  Volume was available on the plan). Now uses Chroma Cloud, a hosted
  Chroma instance, so vector data survives restarts/redeploys the same
  way Postgres does for bot metadata.
"""
import json
import os
import secrets
import threading
from typing import Optional

import chromadb
import psycopg2
from psycopg2.extras import RealDictCursor
from langchain_chroma import Chroma
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
    list_bots, delete_bot) -- only the storage backend changed, from a
    local JSON file to Postgres. Each bot is stored as one row: a unique
    bot_id column plus a JSONB column holding the rest of the bot's data,
    which keeps this class simple and avoids a rigid schema migration
    every time a new bot field gets added later.
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


class VectorStoreManager:
    """
    One Chroma collection per bot_id, same as before. Now backed by
    Chroma Cloud (a hosted Chroma instance) instead of a local
    PersistentClient, so collections survive Railway restarts/redeploys.
    """

    def __init__(self):
        self.client = chromadb.CloudClient(
            tenant=settings.CHROMA_TENANT,
            database=settings.CHROMA_DATABASE,
            api_key=settings.CHROMA_API_KEY,
        )

    def get_store(self, bot_id: str) -> Chroma:
        return Chroma(
            client=self.client,
            collection_name=f"bot_{bot_id}",
            embedding_function=get_embeddings(),
        )

    def add_documents(self, bot_id: str, documents: list) -> int:
        if not documents:
            return 0
        store = self.get_store(bot_id)
        store.add_documents(documents)
        return len(documents)

    def similarity_search(self, bot_id: str, query: str, k: int = None):
        store = self.get_store(bot_id)
        k = k or settings.RETRIEVAL_TOP_K
        try:
            return store.similarity_search_with_relevance_scores(query, k=k)
        except Exception:
            # Fallback for chroma versions/edge cases where relevance scoring
            # isn't available -- degrade gracefully instead of erroring out.
            results = store.similarity_search(query, k=k)
            return [(doc, None) for doc in results]

    def delete_collection(self, bot_id: str):
        try:
            self.client.delete_collection(f"bot_{bot_id}")
        except Exception as e:
            logger.warning(f"Could not delete collection for {bot_id}: {e}")


bot_registry = BotRegistry()
vector_store_manager = VectorStoreManager()