# SERAPH — Segmentation Engine for Research in Anatomical Pathology and Histology

**Image and Multimedia Data Science Laboratory (IMSCIENCE)**

A desktop application for segmenting and annotating cell nuclei in ultra-large microscopy images (WSI — Whole Slide Images). Built to handle images ranging from hundreds of megabytes to multiple gigabytes without loading them fully into RAM.

---

## About

Developed by **Matheus Fagundes** under the Scientific Initiation Program at IMSCIENCE.

The tool bridges interactive annotation workflows with deep-learning segmentation models (Cellpose and NuClick), letting pathologists and researchers isolate regions of interest, run AI-driven nucleus segmentation, manually correct results, and export ML-ready datasets — all from a single dark-themed PyQt6 desktop interface.

---

## What You Can Do

- **Open giant images instantly** — formats supported: `.ndpi`, `.svs`, `.mrxs`, `.tiff`, `.png`, `.jpeg`, `.webp`, `.bmp` and other WSI formats, with no upfront parsing delay
- **Navigate large images fluidly** — multiscale rendering engine reads only the pixels needed for the current viewport
- **Isolate regions of interest** — Grid Tool or freehand Brush Tool to carve out tiles from biological tissue sections
- **Segment nuclei with AI** — click-based NuClick segmentation or whole-tile Cellpose batch segmentation (GPU auto-detected)
- **Run automated pipelines** — Macro Pipeline runs Cellpose → NuClick in sequence across all slices with pause/resume/cancel
- **Manually correct AI errors** — Eraser Brush, Selection Brush, and pixel-level editor to refine any polygon
- **Organize segmentations into layers** — multiple named segmentation layers per tile, toggleable visibility, custom colors per layer
- **Export results in multiple formats** — individual slice images, per-nucleus crops, full HDF5 ML datasets, CSV/JSON metadata, companion XML descriptors
- **Import tile descriptors and GeoJSON** — restore previously exported tile layouts into new sessions
- **Undo/Redo** — deep-copy snapshot stack, up to 50 steps

---

## Architecture

The codebase follows **Clean / Hexagonal Architecture** with four strict layers:

```
app/
├── domain/           # Pure Python business logic (no UI, no I/O)
│   ├── tile.py       # Tile entity — rects, polygon, exclusions, segmentation layers
│   ├── session.py    # ImageSession — active workspace state
│   ├── pyramid.py    # ImagePyramid — on-demand multiscale reader
│   ├── history.py    # UndoManager — snapshot-based undo/redo
│   ├── geometry.py   # Geometric operations
│   └── selection.py  # BFS flood-fill for grid disconnection detection
│
├── application/      # Use-case services (orchestrate domain entities)
│   ├── export_service.py               # All export flows
│   ├── import_service.py               # XML / GeoJSON import
│   ├── project_service.py              # .lab project load/save
│   ├── interactive_segmentation_service.py  # NuClick click-based flow
│   ├── batch_segmentation_service.py   # Cellpose whole-tile flow
│   ├── manual_adjustment_service.py    # Brush/eraser fine-tuning
│   └── nuclei_extraction_service.py    # Nucleus crop extraction
│
├── infrastructure/   # External libraries and I/O adapters
│   ├── ml_models/
│   │   ├── cellpose_adapter.py   # IBatchSegmentationModel → Cellpose
│   │   ├── nuclick_adapter.py    # IInteractiveSegmentationModel → NuClick
│   │   └── nuclick_torch/        # NuClick architecture (PyTorch)
│   ├── config/
│   │   ├── hardware_detector.py  # GPU/CPU auto-detection
│   │   └── performance_config.py # Per-machine performance profiles
│   ├── io.py           # pyvips / Pillow image save
│   ├── tile_xml.py     # Tile descriptor XML read/write
│   └── tile_geojson.py # GeoJSON read
│
└── interface/
    └── gui/
        ├── main_window.py        # SlicerLabApp (QMainWindow)
        └── components/           # Mixin-based UI components
            ├── canvas_renderer.py      # Macro view (full image pan/zoom)
            ├── tile_renderer.py        # Micro view (isolated tile)
            ├── slice_inspector.py      # Tile detail inspector
            ├── slice_export.py         # Export dialog/handler
            ├── macro_pipeline_panel.py # Automated pipeline panel
            ├── project_manager.py      # Open/save project toolbar
            ├── properties_panel.py     # Right-side properties sidebar
            └── selection_tools.py      # Grid/Brush/Segment tool activation
```

---

## Core Features in Depth

### Multiscale Rendering Engine

Uses a **3-tier quality strategy** to minimize RAM and maximize rendering speed:

| Zoom level | Strategy | Backend |
|---|---|---|
| < 50% | Lossy — reads a lower-resolution pyramid level | OpenSlide built-in level / pyvips shrink |
| 50 – 94% | Lossless — crops from full-res, resizes via Lanczos | pyvips / Pillow |
| ≥ 94% | Pixel-perfect — original data, no resampling | pyvips / Pillow |

Two backends are supported transparently:

- **pyvips** — for standard formats (TIFF, PNG, JPEG, WebP, BMP). Lazy random-access — only requested pixels are decoded.
- **OpenSlide** — for WSI formats (`.ndpi`, `.svs`, `.mrxs`, `.scn`, `.bif`, etc.). Uses the multi-resolution pyramid embedded in the file.

Images open instantly regardless of file size.

### Grid Tool and BFS Disconnection

Rubber-band selection marks rectangular grid cells as one tile. When the user removes a middle cell from a large selection, the domain layer runs a **BFS flood-fill** over the 4-connected spatial neighborhood to detect whether the remaining cells form a single contiguous region or multiple disconnected islands. Disconnected groups are automatically split into separate tiles, each assigned a unique color.

### AI Segmentation Models

**Interactive (click-based) — NuClick**

- User clicks on the nucleus of interest inside an isolated tile
- Screen coordinate is mapped to the absolute image pixel space (factoring zoom, camera offset, DPI)
- NuClick model returns a binary mask → converted to a vector polygon via contour detection
- Model weights downloaded on first use from HuggingFace (~100 MB)

**Batch (whole-tile) — Cellpose**

- Segments all nuclei in the entire tile in a single inference pass
- Model: `cpsam` by default (supports `nuclei`, `cyto`, `cyto2`, and any Cellpose model type)
- GPU auto-detected at startup (CUDA on Windows, MPS on Apple Silicon)
- Parameters tunable from the toolbar: `diameter`, `flow_threshold`, `cellprob_threshold`
- Results written to a named segmentation layer — original image is never modified

**Automated Macro Pipeline**

- Runs Cellpose → NuClick in sequence across every tile in the session
- Pause / Resume / Cancel controls
- Progress bar with per-phase timing

### Segmentation Layers

Every inference run creates an independent **named layer** on the tile:

- Multiple layers per tile (e.g., "Cellpose (cpsam)", "NuClick", "Manual")
- Individual visibility toggle per layer
- Per-layer color coding
- Layer selector in the toolbar filters export/extraction scope

### Export System

| Export type | Output |
|---|---|
| Save selected slices | One image per tile, polygon mask applied, tight crop |
| Slice all (grid) | Full image split into grid tiles, no RAM peak |
| Export nuclei (images) | One image per segmented nucleus, organized by slice folder |
| Export nuclei to HDF5 | ML-ready `.h5` file: `images`, `masks`, `patient_ids`, `patient_labels`, `slide_ids`, `roi_ids`, `roi_dimension`, `pixel_size_um` |
| Export metadata | `_metadata.csv` + `_metadata.json` with physical dimensions in µm |
| XML tile descriptor | Companion `_tile.xml` written alongside each exported tile |

Supported output formats: `.png`, `.jpg`, `.tiff`, `.webp`, `.bmp`

Non-transparent formats (JPEG, BMP) automatically composite the polygon mask onto a white background.

---

## Installation

### Requirements

- Python **3.11** (Windows) or **3.12** (macOS)
- GPU optional — CUDA 12.4 on Windows, MPS auto-detected on Apple Silicon

### Windows (CUDA)

```powershell
git clone https://github.com/m4Fagundes/grid-image-analyzer.git
cd grid-image-analyzer

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements-windows.txt

python main.py
```

### macOS (Apple Silicon / Intel)

```bash
git clone https://github.com/m4Fagundes/grid-image-analyzer.git
cd grid-image-analyzer

# Install native C libraries (required for pyvips and OpenSlide)
brew install libvips openslide

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements-macos.txt

python main.py
```

### GPU (Windows CUDA) vs CPU

`requirements-windows.txt` installs PyTorch with CUDA 12.4 by default. To run CPU-only:

```powershell
pip install torch==2.6.0+cpu torchvision==0.21.0+cpu --index-url https://download.pytorch.org/whl/cpu --force-reinstall
```

---

## Building Distributable Installers

CI pipelines run automatically on tag pushes (`v*`). To build locally:

### Windows — Inno Setup installer

```powershell
# Install build deps (CPU torch for smaller artifact)
pip install Pillow openpyxl PyQt6 "openslide-python>=1.4.0" "openslide-bin>=4.0.0" "cellpose>=4.0,<5.0" scikit-image opencv-python psutil scipy numpy h5py
pip install torch==2.6.0+cpu torchvision==0.21.0+cpu --index-url https://download.pytorch.org/whl/cpu
pip install pyinstaller

# Cache Cellpose model weights (bundled into the installer)
python -c "from cellpose import models; models.CellposeModel(model_type='nuclei', gpu=False); models.CellposeModel(model_type='cyto2', gpu=False)"

# Build
python -m PyInstaller docs/build/main_release.spec --clean --noconfirm

# Package with Inno Setup
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" docs\build\installer.iss
# Output: build_installer/GridAnalyzer_Setup.exe
```

### macOS — .app bundle and .dmg

```bash
brew install libvips openslide create-dmg
pip install -r requirements-macos.txt pyinstaller

# Cache Cellpose model weights
python -c "from cellpose import models; models.CellposeModel(model_type='nuclei', gpu=False); models.CellposeModel(model_type='cyto2', gpu=False)"

pyinstaller --clean --noconfirm docs/build/main_release.spec

create-dmg --volname "GridAnalyzer" "dist/GridAnalyzer.dmg" "dist/GridAnalyzer.app"
# Output: dist/GridAnalyzer.app and dist/GridAnalyzer.dmg
```

---

## Keyboard Shortcuts

| Action | Windows / Linux | macOS |
|---|---|---|
| Pan (click + drag) | Left-click drag | Left-click drag |
| Scroll vertically | Mouse Wheel | Mouse Wheel |
| Scroll horizontally | Shift + Mouse Wheel | Shift + Mouse Wheel |
| Zoom (cursor-centered) | Ctrl + Scroll | Cmd / Option + Scroll |
| Undo | Ctrl+Z | Cmd+Z |
| Redo | Ctrl+Y | Cmd+Y |
| Clear all polygons | C | C |
| Segment nucleus (NuClick) | Right-click | Ctrl+Click / Button-2 |

---

## Project File Format (`.lab`)

Sessions are persisted as JSON with relative paths, making projects portable across machines. Share a folder containing both the `.lab` file and the source image file, and the application will resolve all paths correctly regardless of the absolute mount point.

---

## Dependencies

| Package | Purpose |
|---|---|
| PyQt6 | Desktop GUI framework |
| Pillow | Fallback image I/O and polygon masking |
| pyvips / pyvips-binary | High-performance lazy image decoding (standard formats) |
| openslide-python / openslide-bin | WSI format decoding (.ndpi, .svs, .mrxs, …) |
| torch / torchvision | Deep learning backend for Cellpose and NuClick |
| cellpose | Nucleus/cell instance segmentation |
| scikit-image | Contour detection (mask → polygon) |
| opencv-python | Image processing utilities |
| numpy | Array operations |
| scipy | Scientific computing (used by segmentation stack) |
| h5py | HDF5 export for ML datasets |
| psutil | Hardware memory detection |
| openpyxl | Spreadsheet export |

---

<p align="center">
  <b>IMSCIENCE — Merging raw Data Science with complex Cell Microscopy.</b>
</p>
