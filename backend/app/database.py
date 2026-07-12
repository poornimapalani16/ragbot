"""
- BotRegistry: lightweight JSON-file-backed store for per-bot configuration
  (name, API key, prompt, styling). Using a flat file (instead of requiring
  Postgres/MySQL) keeps the whole system deployable with zero external
  infra -- a deliberate tradeoff for "easily deployable" per the brief.
  Swap `_load`/`_save` for a real DB later without touching callers.

- VectorStoreManager: wraps ChromaDB, one collection per bot_id, so every
  embedded website's knowledge base stays isolated from every other's.
"""
import json
import os
import secrets
import threading
from typing import Optional

import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings
from app.utils.exceptions import BotNotFoundError, InvalidAPIKeyError
from app.utils.logger import get_logger

logger = get_logger(__name__)

_REGISTRY_PATH = os.path.join(os.path.dirname(settings.CHROMA_PERSIST_DIR), "bots.json")
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
    def __init__(self, path: str = _REGISTRY_PATH):
        self.path = path
        if not os.path.exists(self.path):
            self._save({})

    def _load(self) -> dict:
        try:
            with open(self.path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logger.warning("Bot registry file missing/corrupt, reinitializing empty registry.")
            return {}

    def _save(self, data: dict):
        with _lock:
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.path)  # atomic write, avoids corruption on crash

    def create_bot(self, name: str, welcome_message: str, primary_color: str, system_prompt: Optional[str]) -> dict:
        data = self._load()
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
        data[bot_id] = bot
        self._save(data)
        logger.info(f"Created bot {bot_id} ({name})")
        return bot

    def get_bot(self, bot_id: str) -> dict:
        data = self._load()
        bot = data.get(bot_id)
        if not bot:
            raise BotNotFoundError(bot_id)
        return bot

    def verify_api_key(self, bot_id: str, api_key: str) -> dict:
        bot = self.get_bot(bot_id)
        if not secrets.compare_digest(bot["api_key"], api_key or ""):
            raise InvalidAPIKeyError()
        return bot

    def list_bots(self) -> list:
        return list(self._load().values())

    def delete_bot(self, bot_id: str):
        data = self._load()
        if bot_id in data:
            del data[bot_id]
            self._save(data)


class VectorStoreManager:
    """One Chroma collection per bot_id, using a shared persistent client."""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)

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
