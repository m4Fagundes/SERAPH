import tkinter as tk
import warnings

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
    root = tk.Tk()
    SlicerLabApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()