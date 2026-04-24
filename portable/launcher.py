"""
GridAnalyzer Portable Launcher
===============================

This launcher is the user-facing executable. It:

1. Extracts the bundled application payload from its embedded resources
   into a deterministic folder under %LOCALAPPDATA%\\GridAnalyzer.
2. Launches the real application (GridAnalyzer.exe) from that folder —
   completely windowless (no console flash).
3. Waits for the application process to finish.
4. Cleans up the extracted folder, leaving no traces on disk.

Architecture:
  launcher.exe  (tiny, ~5 MB)
    └── extracts → %LOCALAPPDATA%\\GridAnalyzer\\<version_hash>\\
        ├── GridAnalyzer.exe   (real PyInstaller --onedir output)
        ├── *.dll / *.pyd
        └── ... bundled data ...

The launcher itself is built with PyInstaller --onefile --windowed --noconsole
so the user sees zero terminal windows.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import time
import atexit
import ctypes
from pathlib import Path


# ─── Configuration ──────────────────────────────────────────────────────────
APP_NAME = "GridAnalyzer"
APP_EXE_NAME = "GridAnalyzer.exe"
# Version hash derived from this launcher's own path (changes when payload changes)
_LAUNCHER_PATH = Path(sys.executable if getattr(sys, "frozen", False) else __file__)


def _compute_payload_hash() -> str:
    """Compute a short hash to version the extracted payload folder."""
    h = hashlib.md5()
    h.update(str(_LAUNCHER_PATH.stat().st_size).encode())
    h.update(str(_LAUNCHER_PATH.stat().st_mtime_ns).encode())
    return h.hexdigest()[:12]


def _get_install_dir() -> Path:
    """Return the deterministic local install directory."""
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        local_appdata = str(Path.home() / "AppData" / "Local")
    return Path(local_appdata) / APP_NAME / _compute_payload_hash()


def _get_payload_source() -> Path:
    """Return the path to the bundled payload inside the frozen exe."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "payload"
    else:
        # Dev mode: assume payload is next to this script
        return Path(__file__).parent / "payload"


def _hide_console():
    """Ensure no console window is visible (defense-in-depth)."""
    try:
        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def _extract_payload(source: Path, dest: Path) -> None:
    """
    Copy the payload from the frozen bundle to the install directory.
    Uses shutil.copytree for atomic-ish extraction.
    Skips extraction if the destination already exists and looks complete.
    """
    marker = dest / ".extracted_ok"
    if marker.exists():
        return  # Already extracted — skip for instant startup

    # Clean partial extractions
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(source), str(dest))

    # Write marker
    marker.write_text("ok", encoding="utf-8")


def _cleanup(install_dir: Path) -> None:
    """
    Remove the extracted payload folder.
    Called on exit — best-effort; retries a few times for locked files.
    """
    if not install_dir.exists():
        return

    for attempt in range(5):
        try:
            shutil.rmtree(str(install_dir))
            return
        except Exception:
            time.sleep(0.5 * (attempt + 1))

    # Last resort: schedule deletion on next reboot (Windows)
    try:
        _schedule_delete_on_reboot(install_dir)
    except Exception:
        pass


def _schedule_delete_on_reboot(path: Path) -> None:
    """Use MoveFileEx to delete a folder on next reboot."""
    MOVEFILE_DELAY_UNTIL_REBOOT = 0x00000004
    ctypes.windll.kernel32.MoveFileExW(str(path), None, MOVEFILE_DELAY_UNTIL_REBOOT)


def _cleanup_old_versions(base_dir: Path, current_hash: str) -> None:
    """Remove old extracted versions, keeping only the current one."""
    if not base_dir.exists():
        return
    for child in base_dir.iterdir():
        if child.is_dir() and child.name != current_hash:
            try:
                shutil.rmtree(str(child))
            except Exception:
                pass


def main():
    _hide_console()

    payload_source = _get_payload_source()
    install_dir = _get_install_dir()
    version_hash = _compute_payload_hash()
    base_dir = install_dir.parent

    # Clean old versions first
    _cleanup_old_versions(base_dir, version_hash)

    # Extract
    _extract_payload(payload_source, install_dir)

    # Register cleanup on exit
    atexit.register(_cleanup, install_dir)

    # Launch the real application
    app_exe = install_dir / APP_EXE_NAME
    if not app_exe.exists():
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Erro: Executável da aplicação não encontrado em:\n{app_exe}",
            "GridAnalyzer — Erro",
            0x10,  # MB_ICONERROR
        )
        return 1

    try:
        # Launch without console — CREATE_NO_WINDOW flag
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            [str(app_exe)],
            cwd=str(install_dir),
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
        )
        proc.wait()
        return proc.returncode
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Erro ao iniciar a aplicação:\n{e}",
            "GridAnalyzer — Erro",
            0x10,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
