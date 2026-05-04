"""
Runtime hook: help pyvips find libvips.dylib inside the PyInstaller bundle.

pyvips uses ctypes.util.find_library('vips') at import time.  Inside a
PyInstaller bundle, the standard library search path does not include
sys._MEIPASS, so ctypes cannot find libvips.dylib unless we add it to
DYLD_LIBRARY_PATH before pyvips is imported.

pyvips-binary embeds libvips as a platform wheel.  PyInstaller copies
pyvips_binary package contents (including libvips.dylib) into sys._MEIPASS.
This hook ensures those directories are on the dynamic loader search path.
"""

import os
import sys
from pathlib import Path


def _add_dylib_directory(path: Path) -> None:
    """Add path to DYLD_LIBRARY_PATH (macOS) or PATH (Windows fallback)."""
    if not path.is_dir():
        return
    if sys.platform == "darwin":
        current = os.environ.get("DYLD_LIBRARY_PATH", "")
        os.environ["DYLD_LIBRARY_PATH"] = (
            f"{path}{os.pathsep}{current}" if current else str(path)
        )
    else:
        current = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{path}{os.pathsep}{current}" if current else str(path)


if getattr(sys, "frozen", False) and sys.platform == "darwin":
    base_dir = Path(sys._MEIPASS)

    # Search for libvips dylib in likely pyvips_binary bundle locations.
    for dylib_path in base_dir.rglob("libvips*.dylib"):
        _add_dylib_directory(dylib_path.parent)

    # Candidate directories pyvips_binary may use.
    for candidate in (
        base_dir / "pyvips_binary",
        base_dir / "pyvips_binary" / "lib",
        base_dir / "pyvips_binary" / ".dylibs",
        base_dir / ".dylibs",
        base_dir,  # fallback: dylib flattened into _MEIPASS root
    ):
        _add_dylib_directory(candidate)
