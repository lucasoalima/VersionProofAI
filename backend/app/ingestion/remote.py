"""Remote fetching for documentation sources, restricted to an explicit allowlist.

SSRF posture: only https, only exact allowlisted hosts AND path prefixes, no redirects, no
user-supplied hosts at runtime (the allowlist is code, reviewed with each new source), bounded
size and time. A URL that is not allowlisted is rejected before any network call.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

MAX_BYTES = 5_000_000
TIMEOUT_S = 30.0


@dataclass(frozen=True)
class AllowedSource:
    host: str
    path_prefix: str
    license: str
    note: str


# Each entry was reviewed for licence and automated-access terms; see docs/sources.md.
ALLOWLIST: tuple[AllowedSource, ...] = (
    AllowedSource(
        host="raw.githubusercontent.com",
        path_prefix="/forcedotcom/cli/main/releasenotes/",
        license="Apache-2.0",
        note="Salesforce CLI release notes (forcedotcom/cli). The CLI itself fetches them from this path.",
    ),
)


class UrlNotAllowed(PermissionError):
    pass


def validate_url(url: str) -> AllowedSource:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UrlNotAllowed("only https URLs are allowed")
    if parts.username or parts.password or parts.port not in (None, 443):
        raise UrlNotAllowed("credentials and non-default ports are not allowed")
    if ".." in parts.path or "\\" in parts.path or "%" in parts.path:
        raise UrlNotAllowed("path traversal or encoded paths are not allowed")
    for src in ALLOWLIST:
        if parts.hostname == src.host and parts.path.startswith(src.path_prefix):
            return src
    raise UrlNotAllowed(f"{parts.hostname}{parts.path} is not an allowlisted documentation source")


def fetch(url: str) -> tuple[bytes, AllowedSource]:
    src = validate_url(url)
    with (
        httpx.Client(follow_redirects=False, timeout=TIMEOUT_S) as client,
        client.stream("GET", url) as r,
    ):
        if r.status_code != 200:
            raise RuntimeError(f"fetch failed with HTTP {r.status_code}")
        buf = bytearray()
        for chunk in r.iter_bytes():
            buf.extend(chunk)
            if len(buf) > MAX_BYTES:
                raise RuntimeError("response exceeds the size limit")
    return bytes(buf), src
