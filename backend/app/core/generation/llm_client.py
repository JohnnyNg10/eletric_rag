"""
Volcengine Ark LLM client (OpenAI-compatible interface).

Ark is OpenAI-compatible; uses openai.OpenAI with Ark base_url.
The volcenginesdkarkruntime PyPI package is a reserved placeholder — do not use it.
"""
from typing import Iterator, List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class LLMClient:
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

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Non-streaming chat completion.

        Returns:
            Assistant message content string.
        """
        from app.config import settings

        completion = self._get_client().chat.completions.create(
            model=model or settings.LLM_MODEL,
            messages=messages,
            temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
            max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
        )
        return completion.choices[0].message.content

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Iterator[str]:
        """
        Streaming chat — yields content delta strings as they arrive.
        """
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


# Singleton
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


llm_client = get_llm_client()
