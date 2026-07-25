"""
LLM client — supports Volcengine Ark (Doubao) and DeepSeek.
Active provider is controlled by settings.LLM_PROVIDER.
"""
from typing import Iterator, List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ArkLLMClient:
    """Volcengine Ark LLM client (doubao endpoint)."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            from app.config import settings
            self._client = OpenAI(
                base_url=settings.LLM_BASE_URL,
                api_key=settings.ARK_API_KEY,
            )
        return self._client

    def chat(self, messages, *, model=None, temperature=None, max_tokens=None) -> str:
        from app.config import settings
        completion = self._get_client().chat.completions.create(
            model=model or settings.LLM_MODEL,
            messages=messages,
            temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
            max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
        )
        return completion.choices[0].message.content

    def chat_stream(self, messages, *, model=None, temperature=None, max_tokens=None) -> Iterator[str]:
        from app.config import settings
        stream = self._get_client().chat.completions.create(
            model=model or settings.LLM_MODEL,
            messages=messages,
            temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
            max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class DeepSeekLLMClient:
    """DeepSeek LLM client (OpenAI-compatible)."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            from app.config import settings
            self._client = OpenAI(
                base_url=settings.DEEPSEEK_BASE_URL,
                api_key=settings.DEEPSEEK_API_KEY,
            )
        return self._client

    def chat(self, messages, *, model=None, temperature=None, max_tokens=None) -> str:
        from app.config import settings
        completion = self._get_client().chat.completions.create(
            model=model or settings.DEEPSEEK_MODEL,
            messages=messages,
            temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
            max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
        )
        return completion.choices[0].message.content

    def chat_stream(self, messages, *, model=None, temperature=None, max_tokens=None) -> Iterator[str]:
        from app.config import settings
        stream = self._get_client().chat.completions.create(
            model=model or settings.DEEPSEEK_MODEL,
            messages=messages,
            temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
            max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# 类型别名，方便 generator.py 等模块做类型注解
LLMClient = ArkLLMClient | DeepSeekLLMClient

_llm_client = None


def get_llm_client():
    global _llm_client
    if _llm_client is None:
        from app.config import settings
        provider = settings.LLM_PROVIDER.lower()
        if provider == "deepseek":
            _llm_client = DeepSeekLLMClient()
            logger.info("[LLMClient] Using DeepSeek provider")
        else:
            _llm_client = ArkLLMClient()
            logger.info("[LLMClient] Using Ark (Doubao) provider")
    return _llm_client


llm_client = get_llm_client()

