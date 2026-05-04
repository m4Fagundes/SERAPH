"""
Runtime hook: make OpenSlide native libraries discoverable before importing openslide.

On Windows: adds DLL directories via os.add_dll_directory and PATH.
On macOS: sets DYLD_LIBRARY_PATH so ctypes can find libopenslide.dylib inside
          the PyInstaller bundle (sys._MEIPASS).

openslide-python >=1.4 normally auto-discovers openslide-bin's dylib, but the
package layout changes inside a PyInstaller bundle — the hook must assist discovery.
"""

import os
import sys
from pathlib import Path


def _add_dll_directory(path: Path) -> None:
    """Windows: add path to DLL search directories and PATH."""
    if not path.is_dir():
        return
    try:
        os.add_dll_directory(str(path))
    except (AttributeError, OSError):
        pass
    current_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{path}{os.pathsep}{current_path}" if current_path else str(path)


def _add_dylib_directory(path: Path) -> None:
    """macOS: add path to DYLD_LIBRARY_PATH so ctypes can find dylibs."""
    if not path.is_dir():
        return
    current = os.environ.get("DYLD_LIBRARY_PATH", "")
    os.environ["DYLD_LIBRARY_PATH"] = f"{path}{os.pathsep}{current}" if current else str(path)


if getattr(sys, "frozen", False):
    base_dir = Path(sys._MEIPASS)

    if sys.platform == "win32":
        # Windows: discover bundled OpenSlide DLLs and add their directories.
        for dll_path in base_dir.rglob("libopenslide-*.dll"):
            _add_dll_directory(dll_path.parent)

        for candidate in (
            base_dir / "openslide_bin",
            base_dir / "openslide_bin" / "bin",
            base_dir / "openslide_bin" / ".libs",
        ):
            _add_dll_directory(candidate)

    elif sys.platform == "darwin":
        # macOS: discover bundled OpenSlide dylibs and set DYLD_LIBRARY_PATH.
        # openslide-bin bundles the dylib; PyInstaller copies it into _MEIPASS.
        for dylib_path in base_dir.rglob("libopenslide*.dylib"):
            _add_dylib_directory(dylib_path.parent)

        # Candidate directories where openslide-bin may place the dylib.
        for candidate in (
            base_dir / "openslide_bin",
            base_dir / "openslide_bin" / "lib",
            base_dir / "openslide_bin" / ".dylibs",
            base_dir,  # fallback: dylib copied directly into _MEIPASS root
        ):
            _add_dylib_directory(candidate)
