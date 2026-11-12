"""Technical token extraction.

PostgreSQL's default text-search parser splits `INVALID_FIELD`, `Apex.LimitException`
or `v2.1` into fragments and stems ordinary words. For technical documentation that loses
exactly the tokens engineers search for. We extract such identifiers separately and index
them verbatim (lower-cased) via array_to_tsvector, alongside the stemmed body.
"""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b"),  # ERROR_CODE_0427, INVALID_FIELD
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b"),  # Apex.LimitException
    re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"),  # snake_case_identifier
    re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b"),  # camelCase
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b"),  # PascalCase
    re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b"),  # 2.1, v3.0.1
    re.compile(r"\b(?:winter|spring|summer)\s*'?\d{2,4}\b", re.IGNORECASE),  # Spring '25
]
_SEASON_RE = re.compile(r"^(winter|spring|summer)\s*'?\s*(\d{2,4})$", re.IGNORECASE)

MAX_TOKENS = 200


def _canonical(tok: str) -> str:
    m = _SEASON_RE.match(tok)
    if m:
        yy = m.group(2)[-2:]
        return f"{m.group(1).lower()}{yy}"
    return tok.lower()


def extract_technical_tokens(text: str) -> list[str]:
    found: dict[str, None] = {}
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            found.setdefault(_canonical(m.group(0)), None)
            if len(found) >= MAX_TOKENS:
                return list(found)
    return list(found)


def technical_tsvector_literal(tokens: list[str], weight: str = "A") -> str:
    """Build a tsvector literal with positions so ts_rank_cd counts these lexemes.

    array_to_tsvector() emits position-less lexemes, which ts_rank_cd scores as zero; a
    literal such as `'nimbus_limit_exceeded_0427':1A 'foo.bar':2A` keeps both position and weight.
    """
    parts = []
    for i, tok in enumerate(tokens, start=1):
        safe = tok.replace("\\", "\\\\").replace("'", "''")
        parts.append(f"'{safe}':{i}{weight}")
    return " ".join(parts)


def technical_tsquery_literal(tokens: list[str]) -> str:
    safe = ["'" + t.replace("\\", "\\\\").replace("'", "''") + "'" for t in tokens]
    return " | ".join(safe)
