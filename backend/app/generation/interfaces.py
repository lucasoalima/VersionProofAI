from __future__ import annotations

from typing import Protocol


class LLMUnavailable(RuntimeError):
    """The configured LLM provider cannot be used (missing key, model, dependency or network)."""


class LLMProvider(Protocol):
    name: str
    model_id: str

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str: ...
