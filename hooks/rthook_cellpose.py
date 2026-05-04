"""
Runtime hook: set CELLPOSE_LOCAL_MODELS_PATH before cellpose is imported.

When running as a PyInstaller bundle, sys._MEIPASS points to the temporary
directory where bundled data files are extracted. This hook ensures that
Cellpose finds its pre-trained weights there instead of trying to download
them from the internet at runtime.

Architecture note: this file must be referenced in main.spec under
`runtime_hooks` to be executed at application startup, before any
user code (including deferred imports) runs.
"""
import os
import sys
import tempfile

if getattr(sys, 'frozen', False):
    # Running as PyInstaller single-file or one-dir bundle.
    # sys._MEIPASS is the extraction directory for bundled data.
    _base = sys._MEIPASS
    _models_dir = os.path.join(_base, 'cellpose_weights')
    # setdefault: do not override if the user explicitly set the var
    os.environ.setdefault('CELLPOSE_LOCAL_MODELS_PATH', _models_dir)
    
    # Numba caching best practices for PyInstaller:
    # Numba attempts to cache JIT compilations. If it runs inside a PyInstaller
    # frozen bundle, it might attempt to write to _MEIPASS, which causes crashes.
    # We enforce Numba to use a safe temporary directory in AppData/Temp.
    try:
        numba_cache = os.path.join(tempfile.gettempdir(), 'numba_cache_grid_analyzer')
        os.makedirs(numba_cache, exist_ok=True)
        os.environ.setdefault('NUMBA_CACHE_DIR', numba_cache)
    except Exception:
        pass

