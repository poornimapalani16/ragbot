"""
Entrypoint for the Advanced RAG Chatbot backend.

Run locally:    uvicorn app.main:app --reload
Run in Docker:  see Dockerfile / docker-compose.yml
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import health, bots, ingest, chat
from app.utils.exceptions import register_exception_handlers
from app.utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise-grade embeddable RAG chatbot API",
    version="1.0.0",
)

# --- CORS: the widget must be embeddable from ANY customer website ---
origins = ["*"] if settings.ALLOWED_ORIGINS.strip() == "*" else [
    o.strip() for o in settings.ALLOWED_ORIGINS.split(",")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,  # must be False when allow_origins is "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(bots.router)
app.include_router(ingest.router)
app.include_router(chat.router)


@app.on_event("startup")
async def on_startup():
    logger.info(f"{settings.APP_NAME} starting in '{settings.ENVIRONMENT}' mode "
                f"(LLM provider: {settings.LLM_PROVIDER})")
    if settings.ADMIN_API_KEY == "change-this-admin-key":
        logger.warning(
            "SECURITY WARNING: ADMIN_API_KEY is still the default value. "
            "Set a strong secret in your environment before going to production."
        )


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "status": "running",
        "docs": "/docs",
    }
