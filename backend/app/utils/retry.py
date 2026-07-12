"""
Shared retry decorator. Any call to an external LLM API or embedding
model is wrapped with exponential backoff so transient network errors,
rate limits, or provider hiccups self-recover instead of failing the request.
"""
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging
from app.config import settings

logger = logging.getLogger("retry")


def resilient_call(exceptions=(Exception,)):
    """Decorator factory: retry on given exception types with exponential backoff."""
    return retry(
        reraise=True,
        stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
