import os
import sys
import logging
import warnings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# A frozen windowed build has no console, so stderr goes nowhere. Without a log
# file on disk, a failure inside segmentation is invisible to the user.
try:
    from app.infrastructure.logging_setup import configure_logging, unhandled_exception_hook

    configure_logging()
    unhandled_exception_hook()
except Exception as e:  # never block startup on logging
    logging.warning("File logging unavailable: %s", e)

# On Apple Silicon, several operators used by Cellpose/SAM/CellViT have no Metal
# kernel. This must be set before torch is imported or they raise instead of
# falling back to the CPU. (The frozen build also sets it in hooks/rthook_torch_env.py.)
if sys.platform == "darwin":
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

# Initialize GPU selector first to isolate compatible GPUs BEFORE importing torch.
# No-op on macOS and in frozen builds — see gpu_selector.initialize_gpu_visibility.
try:
    from app.infrastructure.config.gpu_selector import initialize_gpu_visibility
    initialize_gpu_visibility()
except Exception as e:
    logging.warning("Failed to initialize GPU visibility: %s", e)

# ── WINDOWS WORKAROUND (WinError 1114) ──
# PyTorch must be imported BEFORE PyQt6. Both load C++ and OpenMP DLLs
# that conflict. If PyQt6 loads first, torch fails to initialize c10.dll.
try:
    import torch
except Exception as e:
    logging.warning("Failed to pre-load torch: %s", e)

from PIL import Image

Image.MAX_IMAGE_PIXELS = None 

try:
    import pyvips

    pyvips.cache_set_max_mem(256 * 1024 * 1024)
    pyvips.cache_set_max(200)
    _PYVIPS_AVAILABLE = True
except Exception:
    pyvips = None
    _PYVIPS_AVAILABLE = False

from app.interface.gui.main_window import SlicerLabApp


def selftest() -> int:
    """
    Import every native dependency and report the selected compute device.

    Runs with SERAPH_SELFTEST=1 and exits without opening a window. The release
    workflow runs this against the packaged app on each target macOS version, so
    a missing dylib or hidden import fails the build instead of the user's launch.
    """
    failures: list[str] = []
    lines: list[str] = []

    # A windowed build (console=False) has no usable stdout on Windows, so the
    # CI reads the report from SERAPH_SELFTEST_LOG instead.
    log_path = os.environ.get("SERAPH_SELFTEST_LOG")

    def emit(line: str) -> None:
        lines.append(line)
        try:
            print(line, flush=True)
        except Exception:
            pass

    def check(label: str, fn, *, optional: bool = False) -> None:
        try:
            detail = fn()
            emit(f"  OK    {label}{f' — {detail}' if detail else ''}")
        except Exception as exc:
            if optional:
                emit(f"  WARN  {label} (optional) — {type(exc).__name__}: {exc}")
                return
            failures.append(label)
            emit(f"  FAIL  {label} — {type(exc).__name__}: {exc}")

    emit(f"SERAPH selftest — python={sys.version.split()[0]} platform={sys.platform} "
         f"frozen={getattr(sys, 'frozen', False)}")

    def _torch() -> str:
        import torch
        from app.infrastructure.config.device import describe_device, select_device

        device = select_device()
        # Prove the backend actually executes, not just that it reports available.
        result = (torch.ones(8, 8, device=device) @ torch.ones(8, 8, device=device)).sum().item()
        assert result == 512.0, f"unexpected matmul result: {result}"
        return f"torch {torch.__version__} on {describe_device(device)}"

    def _openslide() -> str:
        import openslide

        return f"openslide {openslide.__library_version__}"

    def _pyvips() -> str:
        import pyvips

        return f"libvips {pyvips.version(0)}.{pyvips.version(1)}"

    check("torch + device", _torch)
    check("cellpose", lambda: __import__("cellpose").version)
    check("openslide", _openslide)
    # pyvips is optional: the app falls back to PIL when libvips is absent
    # (it is not shipped on Windows). It IS bundled on macOS via pyvips-binary.
    check("pyvips", _pyvips, optional=sys.platform != "darwin")
    check("opencv", lambda: __import__("cv2").__version__)
    check("scikit-image", lambda: __import__("skimage").__version__)
    check("h5py", lambda: __import__("h5py").__version__)
    check("PyQt6", lambda: __import__("PyQt6.QtWidgets", fromlist=["QApplication"]) and "QtWidgets")
    check("cellpose adapter", lambda: type(
        __import__("app.infrastructure.ml_models.cellpose_adapter",
                   fromlist=["CellposeAdapter"]).CellposeAdapter(model_type="cpsam", gpu=False)
    ).__name__)
    check("main window import", lambda: __import__(
        "app.interface.gui.main_window", fromlist=["SlicerLabApp"]).SlicerLabApp.__name__)

    if failures:
        emit(f"SELFTEST FAILED — {len(failures)} check(s): {', '.join(failures)}")
    else:
        emit("SELFTEST PASSED")

    if log_path:
        try:
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        except Exception as exc:  # pragma: no cover
            logging.warning("Could not write selftest log to %s: %s", log_path, exc)

    return 1 if failures else 0


def main() -> None:
    if os.environ.get("SERAPH_SELFTEST") == "1":
        sys.exit(selftest())

    if not _PYVIPS_AVAILABLE:
        warnings.warn(
            "pyvips not installed or missing libvips — falling back to PIL. "
            "Large images may consume more memory.",
            stacklevel=1,
        )
    from PyQt6.QtWidgets import QApplication
    from app.interface.gui.splash_screen import SeraphSplashScreen

    app = QApplication(sys.argv)
    # QSettings keys the persisted theme off these — set before any settings read.
    app.setOrganizationName("SERAPH")
    app.setApplicationName("SERAPH")

    from PyQt6.QtGui import QIcon
    from app.interface.gui.theme import create_seraph_icon
    from app.interface.gui.theme_manager import apply_theme, saved_theme

    app.setWindowIcon(QIcon(create_seraph_icon(256)))
    # Applies the palette and the global stylesheet in one shot.
    apply_theme(saved_theme(), persist=False)

    splash = SeraphSplashScreen()
    splash.show()
    app.processEvents()

    splash.set_status("Loading models and services…")
    window = SlicerLabApp()

    splash.finish(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()