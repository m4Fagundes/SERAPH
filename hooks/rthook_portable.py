"""
Runtime hook: set up portable execution environment.

This hook runs before any user code and handles:
1. CELLPOSE_LOCAL_MODELS_PATH for bundled model weights
2. NUMBA_CACHE_DIR to prevent writes to _MEIPASS
3. Cleanup of the extraction directory on process exit (portable mode)
"""
import os
import sys
import shutil
import atexit
import tempfile

if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS
    _models_dir = os.path.join(_base, 'cellpose_weights')
    os.environ.setdefault('CELLPOSE_LOCAL_MODELS_PATH', _models_dir)

    # Numba cache in safe temp directory
    try:
        numba_cache = os.path.join(tempfile.gettempdir(), 'numba_cache_grid_analyzer')
        os.makedirs(numba_cache, exist_ok=True)
        os.environ.setdefault('NUMBA_CACHE_DIR', numba_cache)
    except Exception:
        pass


