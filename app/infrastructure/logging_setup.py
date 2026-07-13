"""
logging_setup — send logs to a file the user can actually find.

A frozen windowed build (console=False) has no console attached, so anything
written to stderr is discarded. That is how a failed model load on macOS turned
into "I click Segment and nothing happens": the adapter logged the error and
returned an empty list, and the error went nowhere.

Log locations:
    macOS    ~/Library/Logs/GridAnalyzer/gridanalyzer.log
    Windows  %LOCALAPPDATA%\\GridAnalyzer\\Logs\\gridanalyzer.log
    other    ~/.grid-analyzer/logs/gridanalyzer.log
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
from pathlib import Path

_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


def log_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "GridAnalyzer"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "GridAnalyzer" / "Logs"
    return Path.home() / ".grid-analyzer" / "logs"


def log_file() -> Path:
    return log_directory() / "gridanalyzer.log"


def configure_logging(level: int = logging.INFO) -> Path | None:
    """
    Attach a rotating file handler to the root logger.

    Returns the log path, or None if the file could not be opened (in which case
    console logging still applies and the app continues).
    """
    root = logging.getLogger()
    root.setLevel(level)

    try:
        directory = log_directory()
        directory.mkdir(parents=True, exist_ok=True)
        path = log_file()

        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        handler.setLevel(level)
        root.addHandler(handler)
    except Exception as exc:  # pragma: no cover - never block startup on logging
        logging.warning("Could not open log file: %s", exc)
        return None

    # Header: the first thing to check when a user reports a problem.
    logging.info("─" * 60)
    logging.info(
        "GridAnalyzer starting — %s %s (%s), python %s, frozen=%s",
        platform.system(),
        platform.mac_ver()[0] or platform.release(),
        platform.machine(),
        sys.version.split()[0],
        getattr(sys, "frozen", False),
    )

    try:
        from app.infrastructure.config.device import describe_device, select_device

        logging.info("Compute device: %s", describe_device(select_device()))
    except Exception as exc:
        logging.warning("Device detection failed at startup: %s", exc)

    logging.info("Log file: %s", log_file())
    return log_file()


def unhandled_exception_hook() -> None:
    """Route uncaught exceptions to the log instead of a discarded stderr."""

    def handle(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = handle
