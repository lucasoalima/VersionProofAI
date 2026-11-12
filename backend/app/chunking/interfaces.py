from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    heading: str | None
    content: str


class Chunker(Protocol):
    name: str

    def chunk(self, content: str, content_format: str) -> list[Chunk]: ...
