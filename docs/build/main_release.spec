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
# Usage (from repo root):
#   pyinstaller --clean --noconfirm docs/build/main_release.spec
#
# Output:
#   macOS: dist/GridAnalyzer.app (unsigned, ~800MB)
#   Windows: dist/GridAnalyzer/ folder → packaged by installer.iss
#
import pathlib
import platform
from PyInstaller.utils.hooks import collect_all, collect_data_files

# SPECPATH is set by PyInstaller to the directory of this spec file.
# This spec lives in docs/build/, so we go up two levels to reach repo root.
REPO_ROOT = str(pathlib.Path(SPECPATH).parent.parent)
HOOKS_DIR = str(pathlib.Path(SPECPATH).parent.parent / 'hooks')

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
    'numpy',      # bundles npdi and all C-extensions — prevents DLL-not-found on Windows
    'scipy',      # bundles C-extensions used by skimage and cellpose
    'cv2',        # bundles opencv binary extensions
    'h5py',       # bundles HDF5 DLLs
]

# Platform-specific native library packages
if IS_WINDOWS:
    packages_to_collect.append('openslide_bin')

if IS_MAC:
    # openslide-bin universal2 wheel bundles the OpenSlide dylib for macOS.
    # Must be collected so PyInstaller copies the dylib into _MEIPASS.
    packages_to_collect.append('openslide_bin')
    # pyvips-binary bundles libvips.dylib for macOS ARM64.
    # pyvips uses ctypes to load libvips — we must bundle it explicitly.
    packages_to_collect.append('pyvips')
    packages_to_collect.append('pyvips_binary')

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
    # NumPy C-extension internals (prevents "npdi DLL not found" on Windows)
    'numpy',
    'numpy.core',
    'numpy.core._methods',
    'numpy.core._multiarray_umath',
    'numpy._core',
    'numpy._core._multiarray_umath',
    'numpy._core._methods',
    # Scientific stack
    'scipy',
    'scipy.ndimage',
    'scipy.ndimage._filters',
    'scipy.ndimage._interpolation',
    # OpenCV
    'cv2',
    # HDF5
    'h5py',
    'h5py._hl',
    'h5py._hl.files',
    'h5py._hl.group',
    'h5py._hl.dataset',
    # Imaging
    'PIL',
    'PIL.Image',
    'PIL.ImageOps',
    # pyvips — ctypes-based binding; PyInstaller misses the cffi internals
    'pyvips',
    # NuClick submodules — lazy-imported inside methods, not caught by static analysis
    'app.infrastructure.ml_models.nuclick_torch.architecture',
    'app.infrastructure.ml_models.nuclick_torch.layers',
    'app.infrastructure.ml_models.nuclick_torch.guiding_signals',
    'app.infrastructure.ml_models.nuclick_torch.process',
    # Config modules used lazily by adapters
    'app.infrastructure.config.gpu_selector',
    'app.infrastructure.config.performance_config',
    # macOS-specific (if on macOS)
    'objc' if IS_MAC else None,
]

# Remove None values
hiddenimports = [h for h in hiddenimports if h is not None]
hiddenimports = list(set(hiddenimports))  # Remove duplicates

# ---------------------------------------------------------------------------
# 4. Analysis
# ---------------------------------------------------------------------------
# Build excludes list before Analysis — PyInstaller cannot receive None entries.
_excludes = [
    'PyQt5', 'wx', 'PySide2', 'PySide6',
    'torchaudio',       # not used by this app
    # Exclude heavy NVIDIA packages NOT needed for inference (saves ~750 MB).
    # We KEEP: cuda_runtime, cublas, cudnn, curand, nvjitlink, nvtx
    'nvidia.nccl',      # multi-GPU communication — single-GPU inference only
    'nvidia.cufft',     # FFT — not used by Cellpose/NuClick forward pass
    'nvidia.cusolver',  # dense linear algebra solver — not needed for inference
    'nvidia.cusparse',  # sparse matrix ops — not used
    'objc' if not IS_MAC else None,   # objc only on macOS
    'win32' if not IS_WINDOWS else None,  # win32 only excluded on non-Windows
]
_excludes = [e for e in _excludes if e is not None]

a = Analysis(
    [str(pathlib.Path(REPO_ROOT) / 'main.py')],
    pathex=[REPO_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(pathlib.Path(HOOKS_DIR) / 'rthook_cellpose.py'),
        str(pathlib.Path(HOOKS_DIR) / 'rthook_openslide.py'),
        str(pathlib.Path(HOOKS_DIR) / 'rthook_pyvips.py'),
        str(pathlib.Path(HOOKS_DIR) / 'rthook_portable.py'),
    ],
    excludes=_excludes,
    noarchive=False,
    optimize=0,
)

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
        name='GridAnalyzer',
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
            'CFBundleShortVersionString': '1.2.2',
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
