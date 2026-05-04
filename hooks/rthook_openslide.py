"""
Runtime hook: make OpenSlide DLLs discoverable before importing openslide.

PyInstaller freezes Python packages, but native DLL discovery on Windows still
depends on the DLL search path. This hook adds any bundled OpenSlide DLL
directories to the process search path early in startup.
"""

import os
import sys
from pathlib import Path


def _add_dll_directory(path: Path) -> None:
    if not path.is_dir():
        return

    try:
        os.add_dll_directory(str(path))
    except Exception:
        pass

    current_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{path}{os.pathsep}{current_path}" if current_path else str(path)


if getattr(sys, "frozen", False):
    base_dir = Path(sys._MEIPASS)

    # Prefer any bundled directory that actually contains OpenSlide DLLs.
    for dll_path in base_dir.rglob("libopenslide-*.dll"):
        _add_dll_directory(dll_path.parent)

    # Also handle the package directory if openslide-bin is bundled as a folder.
    for candidate in (
        base_dir / "openslide_bin",
        base_dir / "openslide_bin" / "bin",
        base_dir / "openslide_bin" / ".libs",
    ):
        _add_dll_directory(candidate)