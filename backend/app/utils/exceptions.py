"""
Custom exceptions + centralized handlers so that every failure mode
returns a clean, predictable JSON error instead of a raw 500 crash trace.
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for all handled application errors."""

    def __init__(self, message: str, status_code: int = 400, details: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class BotNotFoundError(AppError):
    def __init__(self, bot_id: str):
        super().__init__(f"Bot '{bot_id}' was not found.", status.HTTP_404_NOT_FOUND)


class InvalidAPIKeyError(AppError):
    def __init__(self):
        super().__init__("Invalid or missing API key.", status.HTTP_401_UNAUTHORIZED)


class UnsupportedFileTypeError(AppError):
    def __init__(self, ext: str):
        super().__init__(f"Unsupported file type '{ext}'.", status.HTTP_400_BAD_REQUEST)


class FileTooLargeError(AppError):
    def __init__(self, max_mb: int):
        super().__init__(f"File exceeds max size of {max_mb} MB.", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)


class IngestionError(AppError):
    def __init__(self, reason: str):
        super().__init__(f"Failed to ingest document: {reason}", status.HTTP_422_UNPROCESSABLE_ENTITY)


class LLMProviderError(AppError):
    def __init__(self, reason: str):
        super().__init__(f"The AI model is temporarily unavailable: {reason}", status.HTTP_503_SERVICE_UNAVAILABLE)


class RateLimitExceededError(AppError):
    def __init__(self):
        super().__init__("Too many requests. Please slow down.", status.HTTP_429_TOO_MANY_REQUESTS)


async def app_error_handler(request: Request, exc: AppError):
    logger.error(f"AppError on {request.url.path}: {exc.message} | details={exc.details}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message, "details": exc.details},
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    # Catch-all so the API never returns a raw stack trace to a client website.
    logger.exception(f"Unhandled exception on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "An unexpected error occurred. Our team has been notified.",
        },
    )


def register_exception_handlers(app):
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
