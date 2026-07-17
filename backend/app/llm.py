"""
LLM provider abstraction. Reads LLM_PROVIDER from settings and returns a
LangChain chat model, so switching providers is a one-line .env change
and never requires touching the RAG pipeline code.
"""
from functools import lru_cache

from app.config import settings
from app.utils.exceptions import LLMProviderError
from app.utils.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_chat_model():
    provider = settings.LLM_PROVIDER.lower()
    try:
        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            if not settings.GOOGLE_API_KEY:
                raise LLMProviderError("GOOGLE_API_KEY is not set in the environment.")
            return ChatGoogleGenerativeAI(
                model=settings.LLM_MODEL or "gemini-2.5-flash",
                google_api_key=settings.GOOGLE_API_KEY,
                temperature=settings.LLM_TEMPERATURE,
            )
        elif provider == "openai":
            from langchain_openai import ChatOpenAI
            if not settings.OPENAI_API_KEY:
                raise LLMProviderError("OPENAI_API_KEY is not set in the environment.")
            return ChatOpenAI(
                model=settings.LLM_MODEL or "gpt-4o-mini",
                api_key=settings.OPENAI_API_KEY,
                temperature=settings.LLM_TEMPERATURE,
            )
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            if not settings.ANTHROPIC_API_KEY:
                raise LLMProviderError("ANTHROPIC_API_KEY is not set in the environment.")
            return ChatAnthropic(
                model=settings.LLM_MODEL or "claude-sonnet-5",
                api_key=settings.ANTHROPIC_API_KEY,
                temperature=settings.LLM_TEMPERATURE,
            )
        else:
            raise LLMProviderError(f"Unknown LLM_PROVIDER '{provider}'. Use gemini, openai, or anthropic.")
    except LLMProviderError:
        raise
    except Exception as e:
        logger.error(f"Failed to initialize LLM provider '{provider}': {e}")
        raise LLMProviderError(str(e))
