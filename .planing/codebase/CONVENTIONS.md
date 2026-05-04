# Coding Conventions

**Analysis Date:** 2026-05-04

## Naming Patterns

**Files:**
- `snake_case` for all Python modules: `batch_segmentation_service.py`, `tile_analysis.py`, `hardware_detector.py`
- Interface/port files prefixed with nothing, but class names carry the `I` prefix: `segmentation_model.py` → `ISegmentationModel`
- Test files follow `test_<subject>.py` pattern: `test_cellpose4_migration.py`, `test_tile_analysis_script.py`
- Duplicate files exist with ` 2` suffix (e.g., `interactive_segmentation_service 2.py`), indicating stale copies — these are not canonical

**Classes:**
- `PascalCase` universally: `BatchSegmentationService`, `ImagePyramid`, `UndoManager`
- Domain Port (interface) classes use `I` prefix: `IBatchSegmentationModel`, `ISegmentationModel`
- Abstract base analyzers use suffix `Analyzer`: `TileAnalyzer`, `BasicStatsAnalyzer`
- Adapters use `Adapter` suffix: `CellposeAdapter`, `NuClickAdapter`
- Services use `Service` suffix: `ExportService`, `ProjectService`, `InteractiveSegmentationService`
- Config dataclasses use `Config` suffix: `CellposeConfig`, `PerformanceConfig`, `ThreadingConfig`
- GUI components do not follow a strict suffix pattern

**Functions:**
- `snake_case` for all method names: `register_model`, `get_available_models`, `segment_tile`
- Private methods use single underscore prefix: `_create_stroke_mask`, `_ensure_model_loaded`, `_masks_to_polygons`
- Static helpers use `@staticmethod` + underscore prefix: `_is_cuda_oom`, `_clear_cuda_cache`, `_format_image_size`
- Verb-noun pattern for actions: `load_project`, `save_project`, `export_metadata`, `apply_fine_tune`
- `get_*` prefix for accessors returning computed values: `get_available_models`, `get_analyzer`, `get_thumbnail`
- `is_*` / `can_*` for boolean predicates: `is_batch_model`, `can_undo`, `can_redo`

**Variables:**
- `snake_case` for locals and instance attributes
- Private instance attributes prefixed with `_`: `self._models`, `self._model`, `self._gpu`, `self._undo_stack`
- Module-level constants in `UPPER_SNAKE_CASE`: `MAX_HISTORY`, `LAYER_COLORS`, `TILE_COLORS`, `OPENSLIDE_EXTENSIONS`
- Class-level defaults in `UPPER_SNAKE_CASE`: `DEFAULT_FLOW_THRESHOLD`, `PATCH_SIZE`, `PAD`
- Loop variables and temporaries use short names consistent with domain: `bx1`, `by1`, `bx2`, `by2` for bounding box coords

**Type Annotations:**
- All public method signatures are fully typed on newer infrastructure code (e.g., `app/infrastructure/ml_models/cellpose_adapter.py`)
- Older application layer services (e.g., `app/application/export_service.py`, `app/application/project_service.py`) have partial or missing annotations on some methods
- Return types always annotated on service methods: `-> List[str]`, `-> None`, `-> List[List[Tuple[int, int]]]`
- Union syntax uses Python 3.10+ `X | Y` form where present: `float | None`, `Optional[bool]`
- `from __future__ import annotations` is NOT used; `Optional` and `Union` from `typing` used in older files

## Code Style

**Formatter/Linter:**
- `ruff` is the configured tool (replaces flake8 + isort + black). Config in `pyproject.toml`
- Line length: 100 characters (not 88)
- Quote style: double quotes
- Indent: 4 spaces

**Ruff lint rules active:**
- `E` — pycodestyle errors
- `F` — pyflakes
- `I` — isort (import sorting)
- `UP` — pyupgrade (modern Python syntax)
- `B` — flake8-bugbear
- `W` — pycodestyle warnings
- `E501` (line-too-long) is ignored — formatter handles it
- `B008` (function-call defaults) is ignored

**Type checking:**
- `mypy` configured non-strictly (`strict = false`): `warn_return_any = false`, `ignore_missing_imports = true`
- Progressive typing — not all code is annotated

## Import Organization

**Order (enforced by ruff/isort):**
1. Standard library: `import os`, `import logging`, `import json`, `import copy`
2. Third-party: `from PIL import Image`, `from PyQt6.QtWidgets import ...`
3. First-party app: `from app.domain.xxx import ...`, `from app.application.xxx import ...`

**Example from `app/infrastructure/ml_models/cellpose_adapter.py`:**
```python
import logging
import time
from typing import List, Tuple, Optional

from PIL.Image import Image

from app.domain.interfaces.batch_segmentation_model import IBatchSegmentationModel
from app.infrastructure.config.performance_config import get_performance_config
```

**Path aliases:**
- `known-first-party = ["app"]` configured in ruff isort — no `@/` path alias; only package-relative imports

**Lazy imports:**
- Heavy ML dependencies (`torch`, `numpy`, `cv2`, `cellpose`) are imported inside methods on first use to avoid Windows DLL conflicts with PyQt6. Pattern documented in both `CellposeAdapter` and `NuClickAdapter`.

**Relative imports:**
- Used only within GUI component layer: `from .components import (CanvasRenderer, ...)`

## Error Handling

**Application Service Pattern:**
- Services catch `Exception as e`, log with `logger.exception(...)`, and return empty/safe defaults
- Services do NOT re-raise to callers; the GUI layer receives safe empty results
- Pattern from `app/application/batch_segmentation_service.py`:
```python
try:
    polygons = model.segment(image, ...)
    return polygons
except Exception as e:
    logger.exception("Error running batch segmentation for %s: %s", model_name, e)
    return []
```

**Infrastructure/IO Layer Pattern:**
- The infrastructure layer DOES re-raise as domain exceptions using `raise ... from exc`
- Custom exception `ProjectIOError(IOError)` defined in `app/infrastructure/exceptions.py`
- Pattern from `app/infrastructure/io.py`:
```python
except (OSError, json.JSONDecodeError) as exc:
    logger.error("Failed to load project '%s': %s", path, exc)
    raise ProjectIOError(f"Cannot read project file '{path}': {exc}") from exc
```

**Domain Layer:**
- Domain functions (e.g., `app/domain/geometry.py`) use early returns for invalid input, no exceptions
- Pattern: validate inputs (`if not polygon or len(polygon) < 3: return False`)

**Infrastructure Adapters:**
- Use graduated fallback: GPU → CPU retry on `CUDA OOM`
- Pattern in `CellposeAdapter._retry_on_cpu()` — reload model then re-run
- `ImportError` caught separately for optional dependencies (psutil, torch)

**GUI Layer:**
- Errors shown via Qt dialogs, not re-raised

## Logging

**Framework:** Python standard `logging` module. No third-party logging library.

**Setup:**
- Module-level logger: `logger = logging.getLogger(__name__)` — present in every application, infrastructure, and domain module that logs
- Root logger configured in `main.py`: `logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")`
- Diagnostic tool (`app/tools/diagnose_hardware.py`) uses: `format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'`

**Patterns:**
- `%s` format string (not f-string) for deferred formatting: `logger.info("Model loaded: %s", name)`
- `logger.info()` for successful operations and state changes
- `logger.debug()` for verbose/trace details
- `logger.warning()` for soft failures or missing resources that don't block execution
- `logger.error()` for failures in I/O, model loading, or configuration
- `logger.exception()` in `except` blocks in Application Services — includes full traceback automatically
- Some legacy code uses `print(...)` with `flush=True` for debug output (e.g., `SegmentationWorker.run()` in `canvas_renderer.py`) — not the preferred pattern

## Docstrings

**Style:** Google-style docstrings with `Args:` and `Returns:` sections.

**Module-level docstrings:**
- Present on infrastructure adapters and complex modules
- Include architecture notes referencing skills/patterns (e.g., `Architecture (architecture-patterns):`)
- Example from `app/application/batch_segmentation_service.py`:
```python
"""
BatchSegmentationService — Application Service for batch segmentation models.

Architecture (architecture-patterns):
    Mediates between the domain Port (IBatchSegmentationModel) and the
    presentation layer. ...

Design Decision (python-patterns §8 — Error Handling):
    ...
"""
```

**Class docstrings:** Present on all public classes — describe responsibility and Clean Architecture layer.

**Method docstrings:**
- Present on all public methods of services and adapters
- Include `Args:` and `Returns:` sections
- Sparse or missing on GUI component methods
- Some shorter methods have single-line docstrings: `"""Returns the names of all available models."""`

**When to comment inline:**
- Complex algorithm steps (e.g., mask-to-polygon conversion in `CellposeAdapter._masks_to_polygons()`)
- Non-obvious architectural decisions (e.g., DLL load-order workaround for Windows)
- Legacy schema migration logic

## Function Design

**Size:** Most functions are focused and single-purpose; long functions (50+ lines) appear in `ExportService.save_selected_cells()` and `ProjectService.load_project()` for inherently complex pipelines.

**Parameters:**
- Services accept keyword arguments with defaults for optional overrides: `diameter: float | None = None`
- Progress callbacks passed as optional callables: `progress_callback=None`
- `**kwargs` used in analyzer `analyze()` method for extensibility

**Return Values:**
- Services return empty list `[]` for failed operations, never `None` for collection returns
- Booleans returned by predicate helpers: `is_batch_model`, `can_undo`
- Count integers returned by export operations: `save_selected_cells`, `export_nuclei_from_slice`

## Module Design

**Exports:**
- No `__all__` declarations in most modules; public API is implicit
- `app/interface/gui/components/__init__.py` uses explicit named imports for GUI components

**Barrel Files:**
- `app/interface/gui/components/__init__.py` re-exports all component classes
- Other `__init__.py` files are mostly empty

**Dataclasses:**
- Frozen dataclasses used for config objects: `@dataclass(frozen=True)` on `CellposeConfig`, `ThreadingConfig`, `PerformanceConfig`
- Prevents mutation after construction to avoid race conditions

## Patterns

**Dependency Injection:**
- Services never instantiate infrastructure objects themselves
- Adapters injected at Composition Root (`app/interface/gui/main_window.py` `__init__`)

**Lazy Loading:**
- Heavy ML imports deferred to first-use `_ensure_model_loaded()` method
- Applied consistently in `CellposeAdapter` and `NuClickAdapter`

**Port/Adapter (Hexagonal):**
- Domain Ports: `ISegmentationModel`, `IBatchSegmentationModel` in `app/domain/interfaces/`
- Adapters: `CellposeAdapter`, `NuClickAdapter` in `app/infrastructure/ml_models/`

**Snapshot-based Undo:**
- `UndoManager` in `app/domain/history.py` captures tile state via `tile.serialize()` before each mutation

---

*Convention analysis: 2026-05-04*
