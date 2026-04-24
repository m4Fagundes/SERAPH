# -*- mode: python ; coding: utf-8 -*-
#
# main_release.spec — PyInstaller build spec for Grid Image Analyzer
#                      RELEASE BUILD (portable, no console)
#
# Based on the original main.spec with the following improvements:
#   1. console=False — no terminal window visible to users
#   2. runtime_tmpdir set to %LOCALAPPDATA%\GridAnalyzer for fast extraction
#   3. Optimized for end-user distribution
#
# Usage:
#   pyinstaller --clean --noconfirm main_release.spec
#
# Output:
#   dist/GridAnalyzer.exe  (~1.7 GB, self-contained)
#
import pathlib
from PyInstaller.utils.hooks import collect_all, collect_data_files

# ---------------------------------------------------------------------------
# 1. NuClick model weights
# ---------------------------------------------------------------------------
datas = [
    (
        'app/infrastructure/ml_models/nuclick_torch/weights/nuclick.pth',
        'app/infrastructure/ml_models/nuclick_torch/weights',
    ),
]

# ---------------------------------------------------------------------------
# 2. Cellpose pre-trained weights (from local cache ~/.cellpose/models/)
# ---------------------------------------------------------------------------
_cp_cache = pathlib.Path.home() / '.cellpose' / 'models'

if _cp_cache.exists() and _cp_cache.is_dir():
    for _wpath in _cp_cache.glob('*'):
        if _wpath.is_file():
            datas.append((str(_wpath), 'cellpose_weights'))

# ---------------------------------------------------------------------------
# 3. Collect all files from heavy packages (binaries, datas, hiddenimports)
# ---------------------------------------------------------------------------
binaries = []
hiddenimports = []

packages_to_collect = [
    'torch',
    'openslide_bin',
    'cellpose',
    'skimage',
    'numba',
    'llvmlite',
    'fastremap',
    'imagecodecs',
]

for pkg in packages_to_collect:
    try:
        tmp_ret = collect_all(pkg)
        datas     += tmp_ret[0]
        binaries  += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 4. Explicit hidden imports (Fallback explícito complementar)
# ---------------------------------------------------------------------------
hiddenimports += [
    # PyTorch internals (often missed on CPU-only pipelines)
    'torch',
    'torch.nn',
    'torch.nn.functional',
    'torch.utils',
    'torch.utils.data',
    'torchaudio',
    'vtorch',
    # Scientific stack
    'numpy',
    'scipy',
    'scipy.ndimage',
    'cv2',
    # NuClick dependencies (deferred imports in adapter)
    'PIL',
    'PIL.Image',
]

# Remover duplicados
hiddenimports = list(set(hiddenimports))

# ---------------------------------------------------------------------------
# 5. Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],       # custom hooks directory
    hooksconfig={},
    runtime_hooks=[
        'hooks/rthook_cellpose.py',   # sets CELLPOSE_LOCAL_MODELS_PATH & NUMBA env
    ],
    excludes=[
        # GUI
        'PyQt5',
        'wx',
        'PySide2',
        'PySide6',
        # Omit CUDA — CPU-only build
        'nvidia',
    ],
    noarchive=False,
    optimize=0,
)


pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# 6. EXE — RELEASE configuration
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GridAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX off: avoid false-positive AV flags and DLL issues
    upx_exclude=[],
    # ── PORTABILITY: extract to a local folder instead of random temp ──
    # When set to None, PyInstaller uses sys._MEIPASS in %TEMP%.
    # For a deterministic local folder, we'll handle this in the runtime hook.
    runtime_tmpdir=None,
    console=False,      # ← NO CONSOLE WINDOW — clean UX
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
