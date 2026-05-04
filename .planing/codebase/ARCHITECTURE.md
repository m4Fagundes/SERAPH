---
last_mapped: 2026-05-04
---

# Architecture — Grid Image Analyzer

## Pattern

**Clean Architecture / Domain-Driven Design (layered)**

The codebase follows a strict 4-layer clean architecture:
```
Interface (GUI) → Application (Services) → Domain (Entities) → Infrastructure (I/O, ML)
```

Dependency rule is respected: outer layers depend on inner layers; the domain layer has no outward dependencies.

## Layers

### 1. Domain (`app/domain/`)

Pure Python business logic with no framework dependencies.

| File | Role |
|------|------|
| `app/domain/session.py` | `ImageSession` — root aggregate; owns image pyramid, tiles, camera state |
| `app/domain/tile.py` | `Tile` — entity for an isolated image region; holds rects, polygons, segmentation layers, pixel masks |
| `app/domain/pyramid.py` | `ImagePyramid` — on-demand image reader abstraction (wraps pyvips/PIL) |
| `app/domain/geometry.py` | Geometry utilities (polygon operations) |
| `app/domain/history.py` | `UndoManager` — command history for reversible operations |
| `app/domain/selection.py` | Selection state helpers |
| `app/domain/tile_analysis.py` | Tile analysis value objects |
| `app/domain/interfaces/` | Abstract interfaces for ML adapters (`BatchSegmentationModel`, `SegmentationModel`) |

### 2. Application (`app/application/`)

Use-case orchestration services. Depends only on domain entities and infrastructure interfaces.

| Service | Responsibility |
|---------|----------------|
| `project_service.py` | Load/save `.lab` project files; schema migration (legacy → current) |
| `export_service.py` | Export tiles/segmentations to disk (PNG, GeoJSON, XML, JSON) |
| `import_service.py` | Import tile descriptors from XML/GeoJSON |
| `interactive_segmentation_service.py` | Click-based nucleus segmentation (NuClick) |
| `batch_segmentation_service.py` | Whole-tile segmentation (Cellpose); model routing |
| `manual_adjustment_service.py` | Brush/eraser manual mask operations |
| `nuclei_extraction_service.py` | Post-processing: extract nuclei from segmentation results |
| `pixel_mask_service.py` | Pixel-level mask operations |
| `tile_analysis_service.py` | Statistical tile analysis |

### 3. Infrastructure (`app/infrastructure/`)

External adapters. Implements domain interfaces; swappable without touching domain/application layers.

| Module | Responsibility |
|--------|----------------|
| `ml_models/cellpose_adapter.py` | Cellpose 4.x adapter — wraps `cellpose.models.CellposeModel` |
| `ml_models/nuclick_adapter.py` | NuClick adapter — wraps PyTorch model for click-guided segmentation |
| `ml_models/nuclick_torch/` | NuClick neural network (U-Net variant): architecture, layers, guiding signals |
| `ml_models/model_downloader.py` | Auto-download ML model weights |
| `config/hardware_detector.py` | GPU/CPU/memory detection for auto-configuration |
| `config/gpu_selector.py` | GPU device selection logic |
| `config/performance_config.py` | Performance profile derivation |
| `io.py` | Project file I/O (JSON `.lab` format) |
| `exceptions.py` | Domain exceptions (`ProjectIOError`) |
| `tile_geojson.py` / `tile_json.py` / `tile_xml.py` | Tile descriptor parsers/serializers |
| `analyzers/` | Pluggable analyzers (dummy_analyzer for testing) |

### 4. Interface (`app/interface/gui/`)

PyQt6 GUI. Depends on application services; never touches infrastructure directly.

| Component | Role |
|-----------|------|
| `main_window.py` | `SlicerLabApp(QMainWindow)` — composition root; wires all services and components |
| `components/canvas_renderer.py` | Macro view — full image with grid overlay; handles zoom/pan |
| `components/` (tile_renderer) | Micro view — isolated tile editing with segmentation overlay |
| `components/project_manager.py` | File open/save dialogs; session switching |
| `components/export_handler.py` | Export dialog and execution |
| `components/slice_previews.py` | Thumbnail sidebar for tiles |
| `components/properties_panel.py` | Right-side tile metadata/properties dock |
| `components/layer_dropdown.py` | Layer visibility toggle control |
| `components/macro_pipeline_panel.py` | Macro pipeline (batch operations) dock panel |
| `components/input_adapter.py` | Mouse/keyboard event normalization |

## Entry Points

- **`main.py`** — application entry point; pre-loads PyTorch before PyQt6 (Windows DLL workaround), initializes `SlicerLabApp`
- **`portable/launcher.py`** — alternative launcher for portable/PyInstaller builds

## Data Flow

### Loading an image
```
main.py → SlicerLabApp.__init__
  → ProjectManager.add_image() [GUI]
  → ImageSession(path) [Domain]
    → ImagePyramid(path) [Domain — wraps pyvips/PIL]
```

### Grid selection (Macro view)
```
CanvasRenderer [mouse click/drag] → ImageSession.tiles.append(Tile)
  → CanvasRenderer.redraw() [renders grid overlay]
```

### Entering tile isolation (Micro view)
```
SlicerLabApp.switch_to_tile(idx)
  → TileRenderer.load_tile(session, idx)
    → Tile.load_pixels(pyramid) [extracts full-res crop into memory]
  → SlicerLabApp._central_stack.setCurrentIndex(1) [swap view]
  → PropertiesPanel.load_tile(tile) [populate right dock]
```

### Click-based segmentation (NuClick)
```
TileRenderer [mouse click] → InteractiveSegmentationService.run(click, tile)
  → NuClickAdapter.segment(image, click_point)
    → NuClickTorch model inference
  → Tile.add_layer(name, model, polygons)
  → TileRenderer redraw [overlay new polygons]
```

### Batch segmentation (Cellpose)
```
SlicerLabApp._run_batch_segmentation()
  → BatchSegmentationService.run(model_name, tile, params)
    → CellposeAdapter.segment(image, diameter, flow_threshold, cellprob_threshold)
      → cellpose.models.CellposeModel.eval()
  → Tile.add_layer(name, model, polygons)
  → TileRenderer redraw
```

### Saving project
```
ProjectManager.save_project()
  → ProjectService.save_project(path, sessions)
    → [session.serialize() for each ImageSession]
      → [tile.serialize() for each Tile]
    → infrastructure/io.save_project_file(path, data) [JSON .lab file]
```

## Key Abstractions

- **`ImageSession`** — root aggregate; one per open image; owns pyramid + tiles
- **`Tile`** — isolated region entity; owns pixel cache, segmentation layers, polygon masks
- **`ImagePyramid`** — lazy image reader; never loads full image into memory
- **`SegmentationModel` / `BatchSegmentationModel`** — interfaces that decouple ML adapters from services
- **Composition Root** — `SlicerLabApp.__init__` wires all concrete adapters; no service locator

## Dual-View Context System

The application has two distinct rendering contexts that swap via `QStackedWidget`:
- **Macro (index 0)** — `CanvasRenderer` — full image with grid overlay; pan/zoom on pyramid tiles
- **Micro (index 1)** — `TileRenderer` — isolated tile; full-res crop in RAM; ML segmentation tools active

`SlicerLabApp.switch_to_tile()` / `switch_to_canvas()` handle context transitions including memory management (evicting tile pixel caches on return to canvas).
