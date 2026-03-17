import sys
import logging
import warnings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# ── WORKAROUND PARA WINDOWS (WinError 1114) ──
# O PyTorch deve ser importado ANTES do PyQt6. Ambos carregam DLLs de
# C++ e OpenMP que entram em conflito. Se o PyQt6 carregar primeiro,
# o torch falha ao inicializar a c10.dll.
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


def main() -> None:
    if not _PYVIPS_AVAILABLE:
        warnings.warn(
            "pyvips not installed or missing libvips — falling back to PIL. "
            "Large images may consume more memory.",
            stacklevel=1,
        )
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = SlicerLabApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()