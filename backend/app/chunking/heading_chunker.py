"""Deterministic Markdown heading chunker with a size cap.

Splits on ATX headings, then splits oversized sections on paragraph boundaries. Pure and
deterministic so chunk identity (checksum) is stable across re-ingestion.
"""

from __future__ import annotations

import re

from app.chunking.interfaces import Chunk

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


class HeadingChunker:
    name = "heading"

    def __init__(self, max_chars: int = 1500, min_chars: int = 40):
        self.max_chars = max_chars
        self.min_chars = min_chars

    def _split_oversized(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text]
        parts: list[str] = []
        current = ""
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if not para:
                continue
            if current and len(current) + len(para) + 2 > self.max_chars:
                parts.append(current)
                current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current:
            parts.append(current)
        return parts

    def chunk(self, content: str, content_format: str = "markdown") -> list[Chunk]:
        content = content.replace("\r\n", "\n").strip()
        if not content:
            return []
        sections: list[tuple[str | None, str]] = []
        if content_format == "markdown":
            last = 0
            heading: str | None = None
            for m in _HEADING.finditer(content):
                body = content[last : m.start()].strip()
                if body:
                    sections.append((heading, body))
                heading = m.group(2).strip()
                last = m.end()
            tail = content[last:].strip()
            if tail or not sections:
                sections.append((heading, tail or content))
        else:
            sections.append((None, content))

        chunks: list[Chunk] = []
        for heading, body in sections:
            for piece in self._split_oversized(body):
                piece = piece.strip()
                if len(piece) < self.min_chars and chunks:
                    prev = chunks[-1]
                    chunks[-1] = Chunk(prev.ordinal, prev.heading, f"{prev.content}\n\n{piece}")
                    continue
                text = f"{heading}\n\n{piece}" if heading else piece
                chunks.append(Chunk(len(chunks), heading, text))
        return chunks
