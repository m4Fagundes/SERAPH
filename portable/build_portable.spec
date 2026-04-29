# -*- mode: python ; coding: utf-8 -*-
#
# build_portable.spec — PyInstaller build spec for Grid Image Analyzer
#                        (--onedir mode for fast extraction)
#
# This builds the PAYLOAD that the launcher will extract and run.
# Key differences from the original main.spec:
#   1. Uses COLLECT (--onedir) instead of --onefile for instant startup
#   2. console=False — no terminal window
#   3. Output goes to dist/GridAnalyzer_payload/
#
import os
import pathlib
from PyInstaller.utils.hooks import collect_all, collect_data_files

# Get the root directory of the project (parent of 'portable/')
ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

# ---------------------------------------------------------------------------
# 1. NuClick model weights
# ---------------------------------------------------------------------------
datas = [
    (
        os.path.join(ROOT, 'app/infrastructure/ml_models/nuclick_torch/weights/nuclick.pth'),
        'app/infrastructure/ml_models/nuclick_torch/weights',
    ),
]

# ---------------------------------------------------------------------------
# 2. Cellpose pre-trained weights
# ---------------------------------------------------------------------------
_cp_cache = pathlib.Path.home() / '.cellpose' / 'models'

if _cp_cache.exists() and _cp_cache.is_dir():
    for _wpath in _cp_cache.glob('*'):
        if _wpath.is_file():
            datas.append((str(_wpath), 'cellpose_weights'))

# ---------------------------------------------------------------------------
# 3. Collect all files from heavy packages
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
]

for pkg in packages_to_collect:
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 4. Explicit hidden imports
# ---------------------------------------------------------------------------
hiddenimports += [
    'torch',
    'torch.nn',
    'torch.nn.functional',
    'torch.utils',
    'torch.utils.data',
    'torchaudio',
    'numpy',
    'scipy',
    'scipy.ndimage',
    'cv2',
    'PIL',
    'PIL.Image',
]
hiddenimports = list(set(hiddenimports))

# ---------------------------------------------------------------------------
# 5. Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[os.path.join(ROOT, 'hooks')],
    hooksconfig={},
    runtime_hooks=[
        os.path.join(ROOT, 'hooks/rthook_cellpose.py'),
        os.path.join(ROOT, 'hooks/rthook_openslide.py'),
    ],
    excludes=[
        'PyQt5',
        'wx',
        'PySide2',
        'PySide6',
        'nvidia',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# 6. EXE (--onedir mode — the .exe is a thin bootstrapper)
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],                     # binaries NOT embedded in exe (--onedir)
    exclude_binaries=True,  # binaries go to COLLECT folder
    name='GridAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # ← NO CONSOLE WINDOW
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ---------------------------------------------------------------------------
# 7. COLLECT — gather all files into dist/GridAnalyzer_payload/
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='GridAnalyzer_payload',
)
