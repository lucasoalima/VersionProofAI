from __future__ import annotations

import httpx

from app.core.config import settings
from app.generation.interfaces import LLMProvider, LLMUnavailable


class AnthropicProvider:
    """Minimal Messages API client. No SDK dependency; key is read from settings and never logged."""

    name = "anthropic"

    def __init__(self, api_key: str, model_id: str, timeout: float = 60.0):
        if not api_key:
            raise LLMUnavailable("LLM_API_KEY is not set")
        if not model_id:
            raise LLMUnavailable("LLM_MODEL is not set")
        self._key = api_key
        self.model_id = model_id
        self._timeout = timeout

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model_id,
                    "max_tokens": max_tokens,
                    "temperature": 0,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=self._timeout,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"LLM request failed: {type(exc).__name__}") from exc
        return "".join(
            b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text"
        )


def get_llm_provider() -> LLMProvider | None:
    p = settings.llm_provider
    if p == "none":
        return None
    if p == "anthropic":
        return AnthropicProvider(settings.llm_api_key or "", settings.llm_model)
    raise LLMUnavailable(f"unknown LLM_PROVIDER {p!r}")
