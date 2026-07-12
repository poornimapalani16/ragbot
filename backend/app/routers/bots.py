from fastapi import APIRouter, Header
from app.config import settings
from app.database import bot_registry, vector_store_manager
from app.models import BotCreateRequest, BotResponse
from app.utils.exceptions import InvalidAPIKeyError
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/bots", tags=["bots"])


def _require_admin(x_admin_key: str | None):
    if x_admin_key != settings.ADMIN_API_KEY:
        raise InvalidAPIKeyError()


def _build_embed_snippet(bot_id: str, api_key: str) -> str:
    return (
        f'<script src="https://YOUR_DEPLOYED_DOMAIN/widget.js" '
        f'data-bot-id="{bot_id}" '
        f'data-api-key="{api_key}" '
        f'data-api-base="https://YOUR_DEPLOYED_BACKEND_URL"></script>'
    )


@router.post("", response_model=BotResponse)
async def create_bot(payload: BotCreateRequest, x_admin_key: str | None = Header(default=None)):
    _require_admin(x_admin_key)
    bot = bot_registry.create_bot(
        name=payload.name,
        welcome_message=payload.welcome_message,
        primary_color=payload.primary_color,
        system_prompt=payload.system_prompt,
    )
    return BotResponse(
        bot_id=bot["bot_id"],
        api_key=bot["api_key"],
        name=bot["name"],
        welcome_message=bot["welcome_message"],
        primary_color=bot["primary_color"],
        embed_snippet=_build_embed_snippet(bot["bot_id"], bot["api_key"]),
    )


@router.get("")
async def list_bots(x_admin_key: str | None = Header(default=None)):
    _require_admin(x_admin_key)
    bots = bot_registry.list_bots()
    # Never leak API keys in a bulk listing endpoint.
    return [{k: v for k, v in b.items() if k != "api_key"} for b in bots]


@router.get("/{bot_id}/config")
async def get_bot_public_config(bot_id: str):
    """Public, non-sensitive config the widget needs to render (no auth required)."""
    bot = bot_registry.get_bot(bot_id)
    return {
        "name": bot["name"],
        "welcome_message": bot["welcome_message"],
        "primary_color": bot["primary_color"],
    }


@router.delete("/{bot_id}")
async def delete_bot(bot_id: str, x_admin_key: str | None = Header(default=None)):
    _require_admin(x_admin_key)
    bot_registry.delete_bot(bot_id)
    vector_store_manager.delete_collection(bot_id)
    return {"success": True, "message": f"Bot {bot_id} deleted."}
