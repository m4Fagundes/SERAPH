# External Integrations

**Analysis Date:** 2026-05-04

## APIs & External Services

**Model Hosting (HuggingFace):**
- HuggingFace Hub — NuClick PyTorch model weights hosted at `https://huggingface.co/m4fagundes/grid-image-analyzer/resolve/main/nuclick.pth`
  - SDK/Client: stdlib `urllib.request.urlretrieve` (no `huggingface_hub` SDK)
  - Auth: none (public repo, anonymous download)
  - Implementation: `app/infrastructure/ml_models/model_downloader.py` — `ModelDownloader._download_file()`
  - Cache: `~/.grid-analyzer/models/nuclick.pth` (on first use, downloaded on-demand)
  - Fallback: bundled copy at `app/infrastructure/ml_models/nuclick_torch/weights/nuclick.pth` if download fails

**Cellpose Model Registry:**
- Cellpose pretrained model weights — downloaded on first use via the `cellpose` library's built-in download mechanism
  - SDK/Client: `cellpose.models.CellposeModel` (internally uses its own download)
  - Auth: none (public)
  - Cache: `~/.cellpose/models/` (Cellpose default; overridden in PyInstaller bundles via `CELLPOSE_LOCAL_MODELS_PATH` env var)
  - Models used: `"nuclei"`, `"cyto2"` (configurable in `CellposeAdapter.__init__`)
  - PyInstaller build pre-downloads weights: see `build-windows.yml` "Cache Cellpose Models" step

**PyTorch Package Index:**
- PyTorch CUDA wheels — fetched from `https://download.pytorch.org/whl/cu124` during installation
  - Auth: none
  - Configured in `requirements.txt` via `--extra-index-url https://download.pytorch.org/whl/cu124`

## Data Storage

**Databases:**
- None — no database used

**Project Files (local filesystem):**
- Project save/load: JSON files, arbitrary user-chosen paths
  - Read/write: `app/infrastructure/io.py` — `load_project_file()`, `save_project_file()`
  - Format: plain JSON with tile descriptors, polygon data, segmentation layers

**Configuration (local filesystem):**
- User config: `~/.grid-analyzer/config.json`
  - Manager: `app/infrastructure/config/performance_config.py` — `ConfigManager`
  - Template: `config_template.json` (committed to repo)

**Tile Descriptor Files (local filesystem):**
- XML: `*_tile.xml` files exported alongside image tiles
  - Reader/Writer: `app/infrastructure/tile_xml.py`
- GeoJSON: `.geojson` files imported from third-party tools (QuPath, ASAP, SlideRunner)
  - Reader: `app/infrastructure/tile_geojson.py`
- Tile JSON: internal JSON representation
  - Reader: `app/infrastructure/tile_json.py`

**ML Model Cache (local filesystem):**
- NuClick model: `~/.grid-analyzer/models/nuclick.pth` (~450 MB)
- Cellpose models: `~/.cellpose/models/` (nuclei, cyto2 weights)

**File Storage:**
- Local filesystem only — no cloud object storage (S3, GCS, Azure Blob, etc.)

**Caching:**
- None (no Redis, Memcached, or similar)
- In-process: Cellpose model instance cached in `CellposeAdapter._model` after first `_ensure_model_loaded()` call
- In-process: NuClick model instance cached in `NuClickAdapter._model`
- In-process: `HardwareDetector` singleton at `app/infrastructure/config/hardware_detector.py`
- In-process: `ConfigManager` singleton at `app/infrastructure/config/performance_config.py`

## Authentication & Identity

**Auth Provider:**
- None — this is a local desktop application with no user accounts, login, or authentication

## Monitoring & Observability

**Error Tracking:**
- None — no Sentry, Datadog, or similar service

**Logs:**
- Python stdlib `logging` module; configured at startup in `main.py`
- Format: `"%(levelname)s %(name)s: %(message)s"` at `INFO` level
- All major operations in ML adapters and services log at INFO/DEBUG/WARNING/ERROR
- No log aggregation or remote transport

## CI/CD & Deployment

**Hosting:**
- GitHub Releases — distributes compiled installers (`.exe` for Windows, `.app`/`.dmg` for macOS)
- Triggered by git tags matching `v*`

**CI Pipeline:**
- GitHub Actions
  - Windows build: `.github/workflows/build-windows.yml` — Python 3.11, PyInstaller, Inno Setup, releases to GitHub
  - macOS build: `.github/workflows/build-macos.yml` — Python 3.12, matrix build (x86_64 on macos-13, arm64 on macos-14), PyInstaller, create-dmg
- GitHub Actions secrets used:
  - `GITHUB_TOKEN` — for creating releases (provided automatically by GitHub)
  - `APPLE_ID`, `APPLE_ID_PASSWORD`, `TEAM_ID` — optional macOS code signing (skipped if not configured)

**Release Artifacts:**
- `build_installer/GridAnalyzer_Setup.exe` — Windows self-contained installer
- `dist/GridAnalyzer.app` — macOS app bundle
- `dist/GridAnalyzer.dmg` — macOS disk image (optional, `continue-on-error: true`)

## Webhooks & Callbacks

**Incoming:**
- None — local desktop app, no web server, no webhooks

**Outgoing:**
- None — no outgoing webhooks
- Note: The only outbound network call at runtime is the on-demand model download from HuggingFace (see above)

## Whole-Slide Image Format Support

**OpenSlide library** handles native WSI formats locally:
- `.ndpi` — Hamamatsu NDP
- `.svs` — Aperio/Leica
- `.mrxs` — 3DHISTECH MIRAX
- `.vms`, `.vmu` — Hamamatsu
- `.scn` — Leica
- `.bif` — Ventana
- Implementation: `app/domain/pyramid.py` — `ImagePyramid` class, `OPENSLIDE_EXTENSIONS` set
- Windows DLLs: provided by `openslide-bin` PyPI package; configured in `hooks/rthook_openslide.py` for bundled builds

## GPU/Hardware Acceleration

**CUDA (NVIDIA, Windows/Linux):**
- PyTorch CUDA runtime; version 12.4 (`cu124`) for release builds, CPU-only (`--index-url .../cpu`) for CI builds
- GPU auto-selection: `app/infrastructure/config/gpu_selector.py` — picks best compatible device, skips unsupported architectures (e.g. RTX 5060 not yet supported)
- Supported CUDA compute capabilities: sm_50, sm_60, sm_61, sm_70, sm_75, sm_80, sm_86, sm_90

**MPS (Apple Silicon / macOS):**
- PyTorch MPS backend used on macOS (Ventura+)
- macOS Monterey 12.x: MPS disabled automatically due to instability; CPU-only mode enforced

---

*Integration audit: 2026-05-04*
