"""Path guard: local ingestion may only read inside INGESTION_ROOT (no traversal, no symlink escape)."""

from __future__ import annotations

from pathlib import Path


class ForbiddenPathError(PermissionError):
    pass


def resolve_within_root(requested: str | Path, root: Path) -> Path:
    root = root.resolve()
    candidate = (
        (root / Path(requested)).resolve()
        if not Path(requested).is_absolute()
        else Path(requested).resolve()
    )
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ForbiddenPathError(f"Path {requested!r} is outside the ingestion root") from exc
    if not candidate.exists():
        raise FileNotFoundError(str(candidate))
    return candidate
