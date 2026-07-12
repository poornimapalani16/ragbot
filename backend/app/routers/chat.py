import time
from collections import defaultdict, deque

from fastapi import APIRouter, Header, Request

from app.config import settings
from app.database import bot_registry
from app.models import ChatRequest, ChatResponse, SourceChunk
from app.rag_graph import run_rag
from app.utils.exceptions import InvalidAPIKeyError, RateLimitExceededError
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["chat"])

# --- Minimal in-process rate limiter (per bot_id) ---
_request_log: dict[str, deque] = defaultdict(deque)


def _check_rate_limit(bot_id: str):
    now = time.time()
    window = _request_log[bot_id]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= settings.RATE_LIMIT_PER_MINUTE:
        raise RateLimitExceededError()
    window.append(now)


def _authenticate(bot_id: str, x_api_key: str | None):
    if not x_api_key:
        raise InvalidAPIKeyError()
    return bot_registry.verify_api_key(bot_id, x_api_key)


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest, x_api_key: str | None = Header(default=None)):
    _check_rate_limit(payload.bot_id)
    bot = _authenticate(payload.bot_id, x_api_key)

    result = run_rag(
        bot_id=payload.bot_id,
        session_id=payload.session_id,
        question=payload.message,
        system_prompt=bot["system_prompt"],
    )

    sources = [
        SourceChunk(content=d["content"][:300], source=d["source"], score=d["score"])
        for d in result["context_docs"]
    ]

    return ChatResponse(reply=result["answer"], sources=sources, session_id=payload.session_id)
