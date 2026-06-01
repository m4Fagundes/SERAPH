"""Helpers for locating local third-party source checkouts."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_ROOT = PROJECT_ROOT / "external"


def repo_path(name: str, *parts: str) -> Path:
    """Return a local external repo path, preferring external/<name>.

    The fallback to the project root keeps older worktrees usable while local
    checkouts are being migrated.
    """
    external_path = EXTERNAL_ROOT / name
    base = external_path if external_path.exists() else PROJECT_ROOT / name
    return base.joinpath(*parts)


def add_repo_to_path(name: str, *parts: str) -> Path:
    """Add an external repo, or subdirectory of it, to sys.path."""
    path = repo_path(name, *parts)
    path_str = str(path)
    if path.exists() and path_str not in sys.path:
        sys.path.insert(0, path_str)
    return path
