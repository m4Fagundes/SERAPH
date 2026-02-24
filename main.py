import tkinter as tk

# Must be set before any PIL/pyvips usage
from PIL import Image
Image.MAX_IMAGE_PIXELS = None  # Allow ultra-large images (200k×200k+)

try:
    import pyvips
    # Limit pyvips memory usage — process in smaller chunks
    pyvips.cache_set_max_mem(256 * 1024 * 1024)  # 256 MB cache limit
    pyvips.cache_set_max(200)  # max 200 cached operations
except Exception:
    pyvips = None
    print("Warning: pyvips not installed or missing libvips, falling back to PIL. Large images may consume more memory.")

from app.interface.gui.main_window import SlicerLabApp

if __name__ == "__main__":
    root = tk.Tk()
    app = SlicerLabApp(root)
    root.mainloop()