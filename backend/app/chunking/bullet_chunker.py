"""One chunk per top-level bullet. Used for changelog-style sources where every entry is a
self-contained statement about one change; the document heading is repeated in each chunk."""

from __future__ import annotations

import re

from app.chunking.interfaces import Chunk

_BULLET = re.compile(r"^[*-] ", re.MULTILINE)


class BulletChunker:
    name = "bullet"

    def chunk(self, content: str, content_format: str = "release_notes") -> list[Chunk]:
        content = content.replace("\r\n", "\n").strip()
        if not content:
            return []
        starts = [m.start() for m in _BULLET.finditer(content)]
        if not starts:
            return [Chunk(0, None, content)]
        preamble = content[: starts[0]].strip()
        heading = preamble.splitlines()[0].lstrip("# ").strip() if preamble else None
        chunks: list[Chunk] = []
        for i, s in enumerate(starts):
            entry = content[s : starts[i + 1] if i + 1 < len(starts) else len(content)].strip()
            chunks.append(
                Chunk(len(chunks), heading, f"{heading}\n\n{entry}" if heading else entry)
            )
        return chunks
