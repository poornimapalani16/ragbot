"""
In-process conversation memory keyed by session_id. Good enough for a
single-instance deployment (Render/Railway free tier, one Docker container).
For multi-instance horizontal scaling, swap this for Redis -- the interface
(`get_history`, `add_turn`) is deliberately small so that's a drop-in change.
"""
import time
import threading
from collections import defaultdict
from typing import List, Tuple

from app.config import settings

_lock = threading.Lock()
_store: dict[str, dict] = {}  # session_id -> {"turns": [...], "last_used": ts}


def _cleanup_expired():
    now = time.time()
    expired = [
        sid for sid, v in _store.items()
        if now - v["last_used"] > settings.SESSION_TTL_SECONDS
    ]
    for sid in expired:
        del _store[sid]


def get_history(session_id: str) -> List[Tuple[str, str]]:
    """Returns list of (role, content) tuples, oldest first."""
    with _lock:
        _cleanup_expired()
        entry = _store.get(session_id)
        return list(entry["turns"]) if entry else []


def add_turn(session_id: str, role: str, content: str):
    with _lock:
        _cleanup_expired()
        if session_id not in _store:
            _store[session_id] = {"turns": [], "last_used": time.time()}
        entry = _store[session_id]
        entry["turns"].append((role, content))
        entry["last_used"] = time.time()
        # Keep only the most recent N turns to bound prompt size / memory use.
        max_items = settings.MAX_HISTORY_TURNS * 2
        if len(entry["turns"]) > max_items:
            entry["turns"] = entry["turns"][-max_items:]


def clear_session(session_id: str):
    with _lock:
        _store.pop(session_id, None)
