# -*- mode: python ; coding: utf-8 -*-
#
# main_release.spec — PyInstaller build spec for Grid Image Analyzer
#                      RELEASE BUILD (portable, no console, macOS compatible)
#
# Features:
#   1. console=False — no terminal window visible to users
#   2. NuClick model downloaded on-demand (not embedded) → smaller download
#   3. Cellpose weights cached from ~/.cellpose/models/
#   4. macOS-friendly paths and code signing support
#   5. Platform-aware configuration
#
# Usage (macOS):
#   pyinstaller --clean --noconfirm main_release.spec
#
# Usage (Windows):
#   pyinstaller --clean --noconfirm main_release.spec
#
# Output:
#   macOS: dist/GridAnalyzer.app (unsigned, ~800MB)
#   Windows: dist/GridAnalyzer.exe (~1.7GB, includes runtime)
#
import pathlib
import platform
from PyInstaller.utils.hooks import collect_all, collect_data_files

# Detect platform
IS_MAC = platform.system() == 'Darwin'
IS_WINDOWS = platform.system() == 'Windows'

# ---------------------------------------------------------------------------
# 1. Data files (excluding NuClick model — now downloaded on-demand)
# ---------------------------------------------------------------------------
datas = []

# Note: NuClick model is NO LONGER embedded!
# It's downloaded on-demand from HuggingFace to ~/.grid-analyzer/models/
# This keeps the executable ~500MB smaller and faster to download.

# Cellpose pre-trained weights (from local cache ~/.cellpose/models/)
_cp_cache = pathlib.Path.home() / '.cellpose' / 'models'

if _cp_cache.exists() and _cp_cache.is_dir():
    for _wpath in _cp_cache.glob('*'):
        if _wpath.is_file():
            datas.append((str(_wpath), 'cellpose_weights'))

# ---------------------------------------------------------------------------
# 2. Collect all files from heavy packages (binaries, datas, hiddenimports)
# ---------------------------------------------------------------------------
binaries = []
hiddenimports = []

packages_to_collect = [
    'torch',
    'cellpose',
    'skimage',
    'numba',
    'llvmlite',
    'fastremap',
]

# openslide_bin is Windows-only
if IS_WINDOWS:
    packages_to_collect.append('openslide_bin')

for pkg in packages_to_collect:
    try:
        tmp_ret = collect_all(pkg)
        datas     += tmp_ret[0]
        binaries  += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 3. Explicit hidden imports
# ---------------------------------------------------------------------------
hiddenimports += [
    # PyTorch internals
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
    'cv2',
    # Imaging
    'PIL',
    'PIL.Image',
    'PIL.ImageOps',
    # macOS-specific (if on macOS)
    'objc' if IS_MAC else None,
]

# Remove None values
hiddenimports = [h for h in hiddenimports if h is not None]
hiddenimports = list(set(hiddenimports))  # Remove duplicates

# ---------------------------------------------------------------------------
# 4. Analysis
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
        # GUI frameworks we don't use
        'PyQt5',
        'wx',
        'PySide2',
        'PySide6',
        # CUDA (CPU-only build)
        'nvidia',
        # Windows-specific
        'win32' if not IS_WINDOWS else None,
    ],
    noarchive=False,
    optimize=0,
)

# Remove None values from excludes
if a.excludes:
    a.excludes = [e for e in a.excludes if e is not None]

pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# 5. Building
# ---------------------------------------------------------------------------
if IS_MAC:
    # macOS app bundle
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='GridAnalyzer',
        debug=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,  # Signing requires Apple Developer account
        entitlements_file=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='GridAnalyzer.app',
    )
    
    # macOS app
    app = BUNDLE(
        coll,
        name='GridAnalyzer.app',
        icon=None,  # Set to 'path/to/icon.icns' if you have one
        bundle_identifier='com.matheus1.gridanalyzer',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'NSRequiresIPhoneOS': False,
            'CFBundleShortVersionString': '1.0.0',
        },
    )

else:
    # Windows EXE
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='GridAnalyzer',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='GridAnalyzer',
    )
