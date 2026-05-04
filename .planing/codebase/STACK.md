# Technology Stack

**Analysis Date:** 2026-05-04

## Languages

**Primary:**
- Python 3.11 (CI: 3.11 for Windows, 3.12 for macOS) — all application code

**Secondary:**
- XML (stdlib `xml.etree.ElementTree`) — tile descriptor format (`app/infrastructure/tile_xml.py`)
- GeoJSON (stdlib `json`) — annotation import from QuPath/ASAP/SlideRunner (`app/infrastructure/tile_geojson.py`)
- JSON — project save/load format, configuration files (`app/infrastructure/io.py`, `config_template.json`)

## Runtime

**Environment:**
- CPython 3.11 (minimum 3.10 per `pyproject.toml`)
- Virtual environment: `.venv/` (present in repo)

**Package Manager:**
- pip (inferred from CI workflow and `requirements.txt`)
- No lockfile committed (only `requirements.txt` with loose version pins)

## Frameworks

**Core:**
- PyQt6 6.11.0 — Desktop GUI framework; all windows, dialogs, toolbars, canvas (`app/interface/gui/`)

**ML Inference:**
- PyTorch 2.6.0+cu124 (CUDA 12.4 build; CPU-only used in CI) — tensor ops, model device management, GPU/MPS detection (`app/infrastructure/ml_models/`)
- torchvision 0.21.0+cu124 — bundled with PyTorch; not used directly by app code but required by cellpose
- Cellpose 4.1.1 — automated batch nucleus/cell segmentation (`app/infrastructure/ml_models/cellpose_adapter.py`)

**Testing:**
- pytest 8.x — test runner; config in `pyproject.toml` `[tool.pytest.ini_options]`
- pytest-cov 5.x — coverage reporting

**Build/Packaging:**
- PyInstaller — produces standalone `.exe` (Windows) and `.app` (macOS) bundles; spec at `docs/build/main_release.spec`
- Inno Setup 6 — Windows installer packaging; script at `docs/build/installer.iss`
- Hatchling — Python package build backend (`pyproject.toml`)
- create-dmg (Homebrew) — macOS DMG disk image creation

**Linting/Formatting:**
- ruff 0.4.x — linter + formatter (replaces flake8, isort, pyupgrade, black); config in `pyproject.toml`

**Type Checking:**
- mypy — non-strict, progressive; config in `pyproject.toml`

## Key Dependencies

**Critical (always required):**
- `Pillow` 12.2.0 — PIL Image I/O, drawing, mask operations; used everywhere in `app/`
- `PyQt6` 6.11.0 — entire UI layer (`app/interface/gui/`)
- `openslide-python` 1.4.3 — reads whole-slide image formats (.ndpi, .svs, .mrxs, etc.); used in `app/domain/pyramid.py`
- `openslide-bin` 1.4.3 — native OpenSlide DLLs for Windows
- `openpyxl` 3.1.5 — Excel export capability; used by export services

**ML / Segmentation:**
- `cellpose` 4.1.1 (>=4.0,<5.0) — automated nucleus segmentation; `app/infrastructure/ml_models/cellpose_adapter.py`
- `torch` 2.6.0+cu124 — PyTorch; used by both Cellpose and NuClick adapters
- `scikit-image` 0.26.0 — image processing utilities; used by cellpose and analysis code
- `opencv-python` 4.13.0.92 (cv2) — contour detection for mask→polygon conversion; `app/infrastructure/ml_models/cellpose_adapter.py`, `nuclick_adapter.py`
- `scipy` 1.17.1 — `scipy.ndimage.find_objects` for efficient mask label extraction; `app/infrastructure/ml_models/cellpose_adapter.py`
- `numpy` 2.4.4 — all numerical/array operations in ML adapters

**Optional / Performance:**
- `pyvips` — libvips binding for fast lazy image tiling; optional, falls back to PIL if missing (`app/domain/pyramid.py`, `main.py`)
- `psutil` 7.2.2 — memory usage monitoring during segmentation (`app/infrastructure/ml_models/cellpose_adapter.py`)
- `numba` / `llvmlite` — JIT compilation used internally by Cellpose; bundled in PyInstaller output

**File Format Support:**
- `tifffile` 2026.4.11 — TIFF support (used by cellpose/scikit-image chain)
- `roifile` 2026.2.10 — ROI file format reading (used by cellpose)

## Configuration

**Environment:**
- No `.env` files used; all runtime config lives in `~/.grid-analyzer/config.json`
- Template at `config_template.json` (committed); users copy to `~/.grid-analyzer/config.json`
- Config manager: `app/infrastructure/config/performance_config.py` (singleton `ConfigManager`)
- Hardware auto-detection: `app/infrastructure/config/hardware_detector.py` selects "low/medium/high" performance profile
- GPU auto-selection: `app/infrastructure/config/gpu_selector.py` picks best compatible CUDA device

**Build:**
- PyInstaller spec: `docs/build/main_release.spec`
- Inno Setup installer: `docs/build/installer.iss`
- Runtime hooks: `hooks/rthook_cellpose.py`, `hooks/rthook_openslide.py`, `hooks/rthook_portable.py`
- Portable build variant: `portable/build_portable.spec`, `portable/launcher.spec`

## Platform Requirements

**Development:**
- Python >= 3.10 (tested with 3.11 on Windows, 3.12 on macOS)
- CUDA 12.4 compatible NVIDIA GPU recommended (RTX 2060+ tested); CPU fallback supported
- libvips (optional): install via `pip install pyvips` + system libvips for large-image performance
- OpenSlide native libraries: provided via `openslide-bin` on Windows; system package on macOS/Linux

**Production (distributed builds):**
- Windows: self-contained `.exe` installer via Inno Setup; bundles Python, all DLLs, Cellpose weights
- macOS: `.app` bundle (unsigned unless Apple Developer account configured); targets macOS 12+ (Monterey special-cased for CPU-only mode)
- macOS Monterey 12.x: automatic CPU-only mode (`force_cpu_only=True`) due to MPS instability

---

*Stack analysis: 2026-05-04*
