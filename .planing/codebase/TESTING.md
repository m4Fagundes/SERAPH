# Testing Patterns

**Analysis Date:** 2026-05-04

## Test Framework

**Runner:**
- `pytest` >= 8.0
- Config: `pyproject.toml` under `[tool.pytest.ini_options]`

**Assertion Library:**
- Built-in `assert` statements (pytest-style, no `unittest.TestCase`)

**Run Commands:**
```bash
pytest                          # Run all tests (from project root)
pytest -v                       # Verbose output (default via addopts)
pytest --tb=short               # Short traceback (default via addopts)
pytest --cov=app                # Coverage (requires pytest-cov)
pytest tests/                   # Run only formal test suite
python test_cellpose4_migration.py  # Run migration validation script directly
```

**pytest config in `pyproject.toml`:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
```

## Test File Organization

**Formal test directory:**
- `tests/` at project root — only one file currently present: `tests/test_tile_analysis_script.py`
- Subdirectories exist but are empty: `tests/application/`, `tests/domain/`, `tests/infrastructure/`

**Ad-hoc validation scripts (not collected by pytest):**
- `test_cellpose4_migration.py` — root-level script, standalone, runs with `python test_cellpose4_migration.py`
- `app/tools/diagnose_hardware.py` — diagnostic tool with `test_*` functions but runs as `python -m app.tools.diagnose_hardware`, not as pytest tests

**Naming:**
- Pytest test files: `test_<subject>.py`
- Pytest test functions: `def test_<what_is_tested>():`
- Migration/diagnostic scripts: same `test_*` function naming but self-contained with a `main()` runner

## Test Structure

**Formal pytest tests (`tests/test_tile_analysis_script.py`):**
```python
# No pytest fixtures or assertions — this is a smoke test via direct execution
def main() -> None:
    service = TileAnalysisService()
    dummy_analyzer = BasicStatsAnalyzer()
    service.register_analyzer(dummy_analyzer)
    print(f"Available analyzers: {service.get_available_analyzers()}")
    print("Module Architecture is properly wired.")

if __name__ == "__main__":
    main()
```

Note: `tests/test_tile_analysis_script.py` does not contain any `def test_*` functions and has no pytest assertions — it is a script masquerading as a test file. Pytest collects it but finds no test items.

**Migration validation scripts (`test_cellpose4_migration.py`):**
```python
def test_cellpose_version():
    """Verify Cellpose version is 4.0+"""
    try:
        import cellpose
        version = cellpose.__version__
        major_version = int(version.split('.')[0])
        logger.info(f"✓ Cellpose version: {version}")
        assert major_version >= 4, f"Expected Cellpose 4.0+, got {version}"
        return True
    except Exception as e:
        logger.error(f"✗ Failed to verify Cellpose version: {e}")
        return False
```

**Patterns observed:**
- Return-value pattern: test functions return `True`/`False` (not pytest pass/fail)
- No `setUp`/`tearDown` or pytest fixtures
- No test classes — all top-level functions
- `assert` used only inside migration scripts (not formal pytest tests)
- Logging used for test result output: `logger.info("✓ ...")`, `logger.error("✗ ...")`

## Mocking

**Framework:** No mocking framework is used in current tests. `unittest.mock` is not imported in any test file.

**No mock usage detected.** Existing tests rely on real instantiation of services and adapters.

**What SHOULD be mocked (gaps):**
- `ImagePyramid` — requires a real image file path; tests that use `ImageSession` would fail without a real file
- `CellposeAdapter._model` — loading the ML model requires cellpose + torch installed
- File I/O in `ProjectService` — `load_project_file` / `save_project_file` hit disk

## Fixtures and Factories

**No pytest fixtures exist** (`conftest.py` is absent from `tests/`).

**Test data:**
- Migration script creates synthetic image data inline:
```python
test_image_array = np.zeros((100, 100), dtype=np.uint8)
test_image_array[40:60, 40:60] = 200  # Add a bright nucleus-like region
test_image = Image.fromarray(test_image_array, mode='L')
```
- No shared fixture files, no factory helpers, no `factories/` or `fixtures/` directories

## Coverage

**Requirements:** No enforced coverage threshold defined in `pyproject.toml`.

**View Coverage:**
```bash
pytest --cov=app --cov-report=html    # HTML coverage report in htmlcov/
pytest --cov=app --cov-report=term    # Terminal summary
```

`pytest-cov >= 5.0` is listed as a dev dependency in `pyproject.toml`, but no coverage config exists.

## Test Types

**Unit Tests:**
- Effectively absent. `tests/test_tile_analysis_script.py` performs architecture wiring smoke-check only.
- No tests for domain logic (`geometry.py`, `history.py`, `tile.py`)
- No tests for service layer methods

**Integration Tests:**
- `test_cellpose4_migration.py` functions as an integration test: instantiates `CellposeAdapter`, calls `segment()` on synthetic images, verifies real Cellpose 4.x API compatibility
- `app/tools/diagnose_hardware.py` functions as an environment integration test

**E2E Tests:**
- Not present. No GUI automation or end-to-end test framework configured.

## CI Test Configuration

**No automated test step in CI pipelines.** Both workflows (`build-windows.yml`, `build-macos.yml`) install dependencies and build the PyInstaller release but do NOT run `pytest`.

- `build-windows.yml`: installs with `pip install -e .[dev,cellpose,vips]` (which installs pytest) but has no `pytest` step
- `build-macos.yml`: installs from `requirements.txt` and runs PyInstaller — no test step

## Common Patterns

**Architecture smoke-test pattern:**
```python
def main() -> None:
    service = TileAnalysisService()
    analyzer = BasicStatsAnalyzer()
    service.register_analyzer(analyzer)
    print(f"Available analyzers: {service.get_available_analyzers()}")
    print("Module Architecture is properly wired.")
```

**Migration validation pattern:**
```python
def test_adapter_with_sample_image():
    """Test CellposeAdapter.segment() with a sample image"""
    try:
        adapter = CellposeAdapter(model_type='nuclei', gpu=False)
        polygons = adapter.segment(test_image, diameter=30.0)
        logger.info(f"✓ Segmentation completed, detected: {len(polygons)}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed segmentation test: {e}")
        import traceback
        traceback.print_exc()
        return False
```

## Test Coverage Gaps

**Critical untested areas:**

- `app/domain/geometry.py` — `is_point_in_polygon`, `get_polygon_bounding_box`, `is_rect_overlapping`, `get_polygon_centroid` are pure functions with no side effects; ideal for unit tests
- `app/domain/history.py` — `UndoManager.push()`, `undo()`, `redo()` logic is untested
- `app/domain/tile.py` — `Tile.bounding_box`, `Tile.serialize()`, `Tile.deserialize()` are untested
- `app/application/export_service.py` — image compositing, mask application, metadata export all untested
- `app/application/project_service.py` — JSON load/save round-trip, legacy schema migration untested
- `app/application/manual_adjustment_service.py` — polygon merge/erase logic untested
- `app/infrastructure/io.py` — `load_project_file` / `save_project_file` error paths untested
- `app/infrastructure/ml_models/cellpose_adapter.py` — `_masks_to_polygons` is a pure static method amenable to unit testing without real ML model

---

*Testing analysis: 2026-05-04*
