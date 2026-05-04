---
last_mapped: 2026-05-04
---

# Directory Structure — Grid Image Analyzer

## Top-Level Layout

```
grid-image-analyzer/
├── main.py                    # Application entry point
├── requirements.txt           # Python dependencies
├── pyproject.toml             # Project metadata, build config, versioning
├── config_template.json       # Runtime config template
├── README.md                  # User-facing documentation
├── CLAUDE.md / AGENTS.md      # AI assistant instructions
├── PROJECT_STRUCTURE.md       # Directory guide (Portuguese)
│
├── app/                       # All source code
├── tests/                     # Automated tests
├── docs/                      # Build specs, macOS guides, optimization docs
├── scripts/                   # Standalone utility scripts
├── hooks/                     # PyInstaller runtime hooks
├── portable/                  # Portable build launcher
├── skills/                    # Custom Claude skills
│
├── .planning/                 # GSD planning artifacts
├── .gitnexus/                 # GitNexus index
├── .claude/                   # Claude Code configuration
├── .github/                   # CI/CD workflows
│
├── build/                     # PyInstaller build output (gitignored)
├── build_installer/           # Installer build output (gitignored)
├── dist/                      # Distribution artifacts (gitignored)
└── .venv/ / venv/             # Virtual environments (gitignored)
```

## Source Code (`app/`)

```
app/
├── __init__.py
│
├── domain/                    # Business logic — no external dependencies
│   ├── session.py             # ImageSession (root aggregate)
│   ├── tile.py                # Tile (domain entity)
│   ├── pyramid.py             # ImagePyramid (lazy image reader)
│   ├── geometry.py            # Polygon/geometry utilities
│   ├── history.py             # UndoManager (command pattern)
│   ├── selection.py           # Selection state
│   ├── tile_analysis.py       # Tile analysis value objects
│   └── interfaces/
│       ├── segmentation_model.py       # Interface for click-based ML models
│       └── batch_segmentation_model.py # Interface for batch ML models
│
├── application/               # Use-case services
│   ├── project_service.py              # Load/save .lab project files
│   ├── export_service.py               # Export tiles/masks to disk
│   ├── import_service.py               # Import tile descriptors
│   ├── interactive_segmentation_service.py  # NuClick orchestration
│   ├── batch_segmentation_service.py        # Cellpose orchestration
│   ├── manual_adjustment_service.py         # Brush/eraser operations
│   ├── nuclei_extraction_service.py         # Post-processing nuclei
│   ├── pixel_mask_service.py                # Pixel mask ops
│   ├── tile_analysis_service.py             # Statistical analysis
│   └── services.py                          # Re-exports / service factory
│
├── infrastructure/            # External adapters
│   ├── io.py                  # .lab project JSON I/O
│   ├── exceptions.py          # ProjectIOError
│   ├── tile_geojson.py        # GeoJSON tile descriptor I/O
│   ├── tile_json.py           # JSON tile descriptor I/O
│   ├── tile_xml.py            # XML tile descriptor I/O
│   ├── ml_models/
│   │   ├── cellpose_adapter.py        # Cellpose 4.x wrapper
│   │   ├── nuclick_adapter.py         # NuClick PyTorch wrapper
│   │   ├── model_downloader.py        # Auto-download weights
│   │   └── nuclick_torch/             # NuClick neural net implementation
│   │       ├── architecture.py        # U-Net variant
│   │       ├── layers.py              # Custom PyTorch layers
│   │       ├── guiding_signals.py     # Click-guided signal generation
│   │       └── process.py             # Inference pipeline
│   ├── config/
│   │   ├── hardware_detector.py       # GPU/CPU/RAM detection
│   │   ├── gpu_selector.py            # GPU device selection
│   │   └── performance_config.py      # Performance profile
│   └── analyzers/
│       ├── dummy_analyzer.py          # Test/placeholder analyzer
│       └── __init__.py
│
└── interface/
    └── gui/
        ├── main_window.py             # SlicerLabApp — composition root
        └── components/
            ├── canvas_renderer.py     # Macro view (full image + grid)
            ├── tile_renderer.py       # Micro view (isolated tile editing)
            ├── project_manager.py     # File dialogs, session management
            ├── export_handler.py      # Export dialog & execution
            ├── slice_previews.py      # Tile thumbnail sidebar
            ├── properties_panel.py    # Right dock: tile metadata
            ├── layer_dropdown.py      # Layer visibility toggle
            ├── macro_pipeline_panel.py # Batch operation pipeline dock
            └── input_adapter.py       # Mouse/keyboard event handling
```

## Tests (`tests/`)

```
tests/
├── application/           # Service layer tests
├── domain/                # Domain entity tests
├── infrastructure/        # I/O and adapter tests
└── test_tile_analysis_script.py
```

Plus root-level migration test: `test_cellpose4_migration.py`

## Docs & Scripts

```
docs/
├── build/
│   ├── main.spec              # PyInstaller spec (dev build)
│   └── main_release.spec      # PyInstaller spec (release build)
├── macos/
│   ├── INSTRUCTIONS_MACOS_BUILD.py
│   └── SETUP_MACOS.md
└── optimization/
    └── GPU_OPTIMIZATION.py

scripts/
└── segment_image_cellpose.py  # Standalone CLI segmentation utility

hooks/
├── rthook_cellpose.py         # PyInstaller: cellpose runtime hook
├── rthook_openslide.py        # PyInstaller: openslide runtime hook
└── rthook_portable.py         # PyInstaller: portable mode hook
```

## Key File Locations

| Need | File |
|------|------|
| App entry point | `main.py` |
| Main window / composition root | `app/interface/gui/main_window.py` |
| Root domain aggregate | `app/domain/session.py` |
| Core domain entity | `app/domain/tile.py` |
| Project file format | `app/infrastructure/io.py` |
| Cellpose integration | `app/infrastructure/ml_models/cellpose_adapter.py` |
| NuClick integration | `app/infrastructure/ml_models/nuclick_adapter.py` |
| Hardware auto-detection | `app/infrastructure/config/hardware_detector.py` |
| Python dependencies | `requirements.txt` |
| Build config | `pyproject.toml` |
| Windows installer spec | `docs/build/main_release.spec` |

## Naming Conventions

- **Files**: `snake_case.py`
- **Classes**: `PascalCase` (e.g., `ImageSession`, `CellposeAdapter`, `SlicerLabApp`)
- **Services**: `{Noun}Service` pattern (e.g., `ProjectService`, `ExportService`)
- **Adapters**: `{ModelName}Adapter` pattern (e.g., `CellposeAdapter`, `NuClickAdapter`)
- **Tests**: mirror source structure under `tests/`
- **Duplicate files**: several `* 2.py` files exist (e.g., `nuclick_adapter 2.py`) — these are stale copies that should be deleted

## Notable Patterns

- **Duplicate source files** with ` 2` suffix in `app/infrastructure/ml_models/nuclick_torch/` and elsewhere — appear to be accidental copies, not intentional alternatives
- **Project file format**: `.lab` files are JSON arrays, one object per `ImageSession`
- **Config**: `config_template.json` at root; no runtime config file is committed (generated at first run)
