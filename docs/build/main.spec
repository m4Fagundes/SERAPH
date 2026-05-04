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
#   3. Heavy packages binaries (DLLs): collected via collect_all.
#   4. PyTorch & Numba: require specific handling to avoid DLL/JIT misses.
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

# Em vez de hardcodar os pesos, copiamos de forma inteligente todos os modelos
# cacheados na máquina que realiza o build, prevenindo crash em runtime no cliente
if _cp_cache.exists() and _cp_cache.is_dir():
    for _wpath in _cp_cache.glob('*'):
        if _wpath.is_file():
            datas.append((str(_wpath), 'cellpose_weights'))

# ---------------------------------------------------------------------------
# 3. Collect all files from heavy packages (binaries, datas, hiddenimports)
# ---------------------------------------------------------------------------
binaries = []
hiddenimports = []

# Numba, llvmlite e skimage costumam perder DLLs sem o collect_all.
# PyTorch falha facilmente ao encontrar a libiomp5md.dll.
# Cellpose é coletado integralmente aqui.
packages_to_collect = [
    'torch', 
    'openslide_bin', 
    'cellpose', 
    'skimage', 
    'numba', 
    'llvmlite',
    'fastremap'
]

for pkg in packages_to_collect:
    tmp_ret = collect_all(pkg)
    datas     += tmp_ret[0]
    binaries  += tmp_ret[1]
    hiddenimports += tmp_ret[2]

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
    'vtorch', # in case torchvision fails occasionally
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
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
