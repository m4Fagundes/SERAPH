# -*- mode: python ; coding: utf-8 -*-
#
# main.spec — PyInstaller build spec for Grid Image Analyzer
#
# Key packaging decisions:
#
#   1. NuClick weights: bundled explicitly from app/infrastructure/...
#   2. Cellpose weights: bundled from ~/.cellpose/models/ into cellpose_weights/
#      and located at runtime via hooks/rthook_cellpose.py (sets
#      CELLPOSE_LOCAL_MODELS_PATH = sys._MEIPASS/cellpose_weights).
#   3. OpenSlide DLLs: collected via collect_all('openslide_bin').
#   4. PyTorch (CPU-only): collected via collect_all('torch').
#   5. console=True during testing so exceptions are visible in terminal.
#      Switch to console=False for final distribution.
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
#    Bundled into cellpose_weights/ inside the exe.
#    The runtime hook hooks/rthook_cellpose.py sets CELLPOSE_LOCAL_MODELS_PATH
#    so Cellpose finds them without downloading.
# ---------------------------------------------------------------------------
_cp_cache = pathlib.Path.home() / '.cellpose' / 'models'
_cp_weights = [
    'nucleitorch_0',       # nuclei model — used by CellposeModel(model_type='nuclei')
    'cytotorch_0',         # cyto model   — bundled for completeness (~26 MB)
    'size_cytotorch_0.npy' # size estimator needed by cellpose internals
]
for _w in _cp_weights:
    _wpath = _cp_cache / _w
    if _wpath.exists():
        datas.append((str(_wpath), 'cellpose_weights'))

# ---------------------------------------------------------------------------
# 3. Collect all files from heavy packages (binaries, datas, hiddenimports)
# ---------------------------------------------------------------------------
binaries = []
hiddenimports = []

for pkg in ['torch', 'openslide_bin']:
    tmp_ret = collect_all(pkg)
    datas     += tmp_ret[0]
    binaries  += tmp_ret[1]
    hiddenimports += tmp_ret[2]

# collect cellpose data files (key/, logo/, gui HTML) without triggering
# collect_all which sometimes pulls in GUI dependencies we don't need
datas += collect_data_files('cellpose')

# ---------------------------------------------------------------------------
# 4. Explicit hidden imports
#    PyInstaller static analysis misses these because they are imported
#    lazily (deferred imports inside methods) or via string-based lookups.
# ---------------------------------------------------------------------------
hiddenimports += [
    # Cellpose and its runtime deps
    'cellpose',
    'cellpose.models',
    'cellpose.core',
    'cellpose.dynamics',
    'cellpose.transforms',
    'cellpose.utils',
    'cellpose.io',
    'cellpose.resnet_torch',
    'cellpose.version',
    # PyTorch internals often missed on CPU-only builds
    'torch',
    'torch.nn',
    'torch.nn.functional',
    'torch.utils',
    'torch.utils.data',
    'torchaudio',
    # Scientific stack
    'numpy',
    'scipy',
    'scipy.ndimage',
    'scipy.ndimage._ni_label',
    'scipy.ndimage._ni_label._ni_label',
    'cv2',
    'skimage',
    'skimage.morphology',
    'skimage.measure',
    'fastremap',
    # NuClick dependencies (deferred imports in adapter)
    'PIL',
    'PIL.Image',
]

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
        'hooks/rthook_cellpose.py',   # sets CELLPOSE_LOCAL_MODELS_PATH
    ],
    excludes=[
        # Cellpose GUI (PyQt5-based) — we use PyQt6, no need to bundle PyQt5
        'PyQt5',
        'wx',
        # Omit CUDA — CPU-only torch build
        'nvidia',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# 6. EXE
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
    runtime_tmpdir=None,
    console=True,       # keep True for debugging; set False for final release
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
