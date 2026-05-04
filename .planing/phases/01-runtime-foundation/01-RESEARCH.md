# Phase 1: Runtime Foundation — Research

**Researched:** 2026-05-04
**Domain:** Python dependency management, macOS ARM64 platform compatibility, PyTorch MPS, pyvips, OpenSlide
**Confidence:** HIGH (dependency stack), MEDIUM (MPS inference behavior for Cellpose)

---

## Summary

Phase 1 gets `python main.py` running on macOS Apple Silicon by fixing six categories of problems:
1. The current `requirements.txt` hard-codes CUDA PyTorch wheels that fail on macOS.
2. Three runtime dependencies (`opencv-python`, `psutil`, `scipy`) are used in code but missing from requirements.
3. Ten `* 2.py` files exist alongside their originals — safe to delete, but the presence of the `nuclick_adapter 2.py` copy shows an older version of NuClick that does not support MPS, which is a signal to verify the real adapter is the one with MPS support.
4. `NuClickAdapter._load_model` (in the canonical `nuclick_adapter.py`) only checks `cuda` and falls back to `cpu`, never checking `torch.backends.mps`. MPS must be added as a fallback path.
5. `pyvips` requires a bundled libvips — the `pyvips[binary]` extra or `pyvips-binary` package handles this via a pre-built ARM64 wheel.
6. `openslide-bin` now provides a macOS universal2 wheel that bundles the OpenSlide dylib, eliminating the Homebrew dependency for local development (though Homebrew remains the CI approach).

**Primary recommendation:** Split requirements into `requirements-macos.txt` and `requirements-windows.txt` (or use environment markers), install standard PyTorch from PyPI (no CUDA index), install `pyvips[binary]`, install `openslide-bin openslide-python`, add the three missing deps, delete the `* 2.py` files, and patch `NuClickAdapter` to prefer `mps` over `cpu`.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEP-01 | `pip install -r requirements.txt` succeeds on macOS ARM64 without errors | Split requirements by platform; remove CUDA index and `+cu124` torch spec on macOS |
| DEP-02 | Platform-specific PyTorch: macOS uses CPU/MPS wheels, Windows keeps `+cu124` | macOS: `pip install torch torchvision` from default PyPI (no index URL); Windows: keep existing |
| DEP-03 | Missing runtime deps (`opencv-python`, `psutil`, `scipy`) added | All three have macOS arm64 wheels on PyPI; versions confirmed |
| DEP-04 | Duplicate `* 2.py` files removed from codebase | 10 files confirmed; originals exist for all; Python never imports them; safe `git rm` |
| RUN-01 | `python main.py` launches on macOS 15.5 without crash | PyQt6 ≥6.7 has macOS universal2 wheel; `main.py` already guards pyvips import; torch pre-load guard is safe |
| RUN-02 | App opens and displays main window on Apple Silicon | PyQt6 universal2 wheel confirmed; no ARM64-specific Qt bugs in core library |
| RUN-03 | Standard images (TIFF, PNG, JPEG) load via pyvips on macOS | `pyvips[binary]` / `pyvips-binary` package provides bundled libvips ARM64 |
| RUN-04 | Whole-slide images (NDPI, SVS, MRXS) load via OpenSlide on macOS | `openslide-bin` universal2 wheel bundles dylib; works with `openslide-python ≥1.4` |
| RUN-05 | Cellpose segmentation runs using MPS or CPU | Cellpose 4.x supports MPS inference; sparse tensor ops fail silently on MPS; adapter already has MPS detection path |
| RUN-06 | NuClick segmentation runs using MPS or CPU | Current `nuclick_adapter.py` only checks CUDA, then CPU — MPS path must be added |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PyTorch device selection (CUDA/MPS/CPU) | Infrastructure (adapter layer) | — | `CellposeAdapter` and `NuClickAdapter` own device logic; `HardwareDetector` advises |
| pyvips image loading | Domain (`ImagePyramid`) | Infrastructure (pyvips C extension) | `pyramid.py` owns the pyvips call; the C extension provides the dylib |
| OpenSlide WSI loading | Domain (`ImagePyramid`) | Infrastructure (openslide-bin dylib) | `pyramid.py` owns the openslide call; `openslide-bin` provides the shared library |
| Requirements split by platform | Build / devops | — | requirements files are not application code; this is a repo-level concern |
| Duplicate file removal | Repository hygiene | — | `git rm` — no runtime effect on Python import resolution |
| MPS fallback in NuClickAdapter | Infrastructure (adapter layer) | — | `nuclick_adapter.py:_load_model` and inline `device =` calls need patching |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `torch` | 2.7.0 (latest stable) | PyTorch with MPS support | Standard PyPI wheel includes MPS; no CUDA index needed on macOS |
| `torchvision` | 0.22.0 (matches torch 2.7.0) | Vision ops used by Cellpose | Must match torch major version |
| `cellpose` | 4.1.1 (current) | Nucleus segmentation | Already pinned `>=4.0,<5.0`; 4.1.1 on PyPI |
| `pyvips` | 3.1.1 (current) | Standard image loading (TIFF/PNG/JPEG) | Main package; requires companion binary |
| `pyvips-binary` | 8.18.0 (current) | Bundled libvips for macOS ARM64 | Provides `macosx_11_0_arm64.whl`; avoids Homebrew for local dev |
| `openslide-python` | 1.4.3 (current) | WSI loading (NDPI/SVS/MRXS) | Version ≥1.4 supports openslide-bin on macOS |
| `openslide-bin` | 4.0.0.13 (current) | Bundled OpenSlide dylib for macOS | `macosx_11_0_universal2.whl` includes ARM64 and x86_64 |
| `PyQt6` | ≥6.0.0 (keep existing constraint) | GUI framework | 6.11.0 available; universal2 wheel on PyPI; no ARM64 issues in core |
| `opencv-python` | 4.13.0.92 (current) | Contour detection in NuClick/Cellpose | macOS ARM64 wheel available; used by both adapters |
| `psutil` | 7.2.2 (current) | Memory usage monitoring in CellposeAdapter | ARM64 wheel available; already used in `_check_memory_usage` |
| `scipy` | 1.17.1 (current) | `scipy.ndimage.find_objects` in `_masks_to_polygons` | ARM64 wheel available; already imported in `cellpose_adapter.py` |
| `scikit-image` | ≥0.21.0 (keep existing) | Image processing | Already in requirements.txt |
| `Pillow` | ≥10.4.0 (keep existing) | PIL fallback image loading | Already in requirements.txt |
| `openpyxl` | ≥3.1.0 (keep existing) | Excel export | Already in requirements.txt |

**Version verification:**
- `torch 2.7.0` — confirmed via `pip index versions torch` [VERIFIED: pip registry]
- `pyvips 3.1.1` — confirmed via `pip index versions pyvips` [VERIFIED: pip registry]
- `pyvips-binary 8.18.0` — confirmed via PyPI search [CITED: pypi.org/project/pyvips-binary]
- `openslide-bin 4.0.0.13` — confirmed via `pip index versions openslide-bin` [VERIFIED: pip registry]
- `openslide-python 1.4.3` — confirmed via `pip index versions openslide-python` [VERIFIED: pip registry]
- `opencv-python 4.13.0.92` — confirmed via `pip index versions opencv-python` [VERIFIED: pip registry]
- `psutil 7.2.2` — confirmed via `pip index versions psutil` [VERIFIED: pip registry]
- `scipy 1.17.1` — confirmed via `pip index versions scipy` [VERIFIED: pip registry]
- `cellpose 4.1.1` — confirmed via `pip index versions cellpose` [VERIFIED: pip registry]

### Platform Split Approach

The canonical approach for this project: two separate requirements files.

```
requirements-macos.txt   # macOS ARM64 (this phase)
requirements-windows.txt # Windows CUDA (untouched — existing behavior)
```

`requirements-windows.txt` is effectively the current `requirements.txt` renamed. `requirements-macos.txt` replaces the CUDA torch block with plain `torch torchvision` (no `--extra-index-url`, no `+cu124` suffix) and adds `pyvips-binary`, the three missing deps, and removes `openslide-bin` from macOS-specific restrictions (it works on both now).

**Installation:**

```bash
# macOS ARM64
pip install -r requirements-macos.txt

# Windows (existing)
pip install -r requirements-windows.txt
```

---

## Architecture Patterns

### System Architecture Diagram

```
User clicks "Run Cellpose"
        |
        v
GUI Thread (PyQt6 main_window.py)
        |-- dispatches via QThreadPool -->
        v
CellposeAdapter.segment()          NuClickAdapter.predict()
        |                                  |
        v                                  v
_ensure_model_loaded()             _ensure_model_loaded()
        |                                  |
        v                                  v
HardwareDetector / config          _get_model_path() → ModelDownloader
        |                                  |
        v                                  v
CellposeModel(gpu=True/False)      NuClick_NN.load_state_dict()
    torch.device(mps|cuda|cpu)         torch.device(mps|cuda|cpu)  ← NEEDS PATCH
        |                                  |
        v                                  v
model.eval(img_np, ...)             model(input_tensor)
        |                                  |
        v                                  v
masks → _masks_to_polygons()       preds → cv2.findContours()
  (scipy.ndimage + cv2)                    |
        |                                  v
        v                           polygon coords
List[List[(x,y)]] → GUI
```

```
Image Load Request
        |
        v
ImagePyramid.__init__(path)
        |
        ├── .ndpi / .svs / .mrxs → openslide.OpenSlide(path)
        |       (dylib from openslide-bin universal2 wheel)
        |
        └── .tiff / .png / .jpeg → pyvips.Image.new_from_file(path)
                (libvips from pyvips-binary arm64 wheel)
        |
        v
viewport_for_camera() → PIL.Image region
        |
        v
QPixmap → QLabel (canvas_renderer.py)
```

### Recommended Project Structure for Requirements

```
grid-image-analyzer/
├── requirements-macos.txt      # new — macOS ARM64 deps (this phase)
├── requirements-windows.txt    # renamed from requirements.txt (unchanged content)
├── requirements.txt            # keep pointing to platform-appropriate file, OR delete
└── app/
    └── infrastructure/
        └── ml_models/
            └── nuclick_adapter.py  # patch: add MPS device path
```

### Pattern 1: Platform-Split requirements.txt

**What:** Two separate requirements files, one per platform. No environment markers (avoids the pip `--extra-index-url` + markers interaction bug where markers are ignored when combined with index URLs).
**When to use:** When platforms need fundamentally different index URLs (macOS uses PyPI default; Windows uses `download.pytorch.org/whl/cu124`).

```
# requirements-macos.txt
# macOS ARM64 — no CUDA index, MPS comes bundled in standard torch wheels
Pillow>=10.4.0
openpyxl>=3.1.0
PyQt6>=6.0.0
openslide-python>=1.4.0
openslide-bin>=4.0.0
pyvips>=2.2.0
pyvips-binary>=8.0.0
torch>=2.0.0
torchvision>=0.15.0
cellpose>=4.0,<5.0
scikit-image>=0.21.0
opencv-python>=4.8.0
psutil>=5.9.0
scipy>=1.11.0
```

```
# requirements-windows.txt
# Windows — CUDA 12.4 torch wheels
--extra-index-url https://download.pytorch.org/whl/cu124
Pillow>=10.4.0
openpyxl>=3.1.0
PyQt6>=6.0.0
openslide-python>=1.3.1
openslide-bin>=1.4.3
torch==2.6.0+cu124
torchvision==0.21.0+cu124
cellpose>=4.0,<5.0
scikit-image>=0.21.0
opencv-python>=4.8.0
psutil>=5.9.0
scipy>=1.11.0
```

**Note on environment markers alternative:** PEP 508 markers (`; sys_platform == 'darwin'`) do work in requirements.txt, but pip has a known bug (issue #13637) where `--extra-index-url` combined with markers causes the markers to be ignored. Because Windows needs `--extra-index-url` for CUDA, using a single file with markers is unreliable. Two separate files is the safe pattern. [CITED: github.com/pypa/pip/issues/13637]

### Pattern 2: MPS Device Selection in NuClickAdapter

**What:** Add `mps` as a device option between CUDA and CPU.
**When to use:** For all torch device selection code that currently only checks `cuda`.

Current broken pattern (in `nuclick_adapter.py`):
```python
# BROKEN — skips MPS entirely on macOS
best_gpu = get_best_cuda_device()
if torch.cuda.is_available() and best_gpu is not None:
    device = torch.device(f'cuda:{best_gpu}')
else:
    device = torch.device('cpu')
```

Corrected pattern:
```python
import torch

def _get_device() -> torch.device:
    """Selects the best available device: CUDA > MPS > CPU."""
    try:
        from app.infrastructure.config.gpu_selector import get_best_cuda_device
        best_gpu = get_best_cuda_device()
        if torch.cuda.is_available() and best_gpu is not None:
            return torch.device(f'cuda:{best_gpu}')
    except Exception:
        pass

    if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        return torch.device('mps')

    return torch.device('cpu')
```

This helper must replace the inline device-selection logic in `_load_model`, `predict`, and `predict_batch`. There are **three locations** in `nuclick_adapter.py` that need updating (lines ~77–81, ~170–175, ~284–289).

**Note:** `CellposeAdapter` already has MPS detection at line 89–90 via `torch.backends.mps.is_available()` — it does NOT need patching for MPS awareness. However, `_load_model` does not explicitly pass `device=torch.device('mps')` to `CellposeModel` when MPS is selected — Cellpose's own GPU detection should handle this when `gpu=True`, but it is worth verifying Cellpose picks MPS when CUDA is absent. [ASSUMED — needs runtime verification on Apple Silicon]

### Anti-Patterns to Avoid

- **Pinning torch to `==2.6.0+cu124` in macOS requirements:** The `+cu124` suffix only exists on the CUDA PyPI index. The macOS wheel from PyPI default has no suffix. Pinning the exact version with suffix breaks on macOS.
- **Using a single `requirements.txt` with `--extra-index-url` + platform markers:** pip silently ignores markers when `--extra-index-url` is present (known bug). Do not rely on this pattern.
- **`brew install openslide` for local dev:** Unnecessary — `openslide-bin` universal2 wheel bundles the dylib. Homebrew is only needed for CI/PyInstaller bundling (Phase 3).
- **Deleting `* 2.py` files with OS delete instead of `git rm`:** Must use `git rm` to remove them from git history tracking. Plain filesystem delete leaves them as untracked deletions that can reappear on checkout.
- **Importing `nuclick_adapter 2` anywhere:** These are inaccessible via Python imports (spaces in filenames are not valid module names). But PyInstaller's `collect_all` on the `app` package might try to bundle them as data files. Remove before any PyInstaller build.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| libvips dylib bundling for macOS | Custom dylib download scripts | `pyvips-binary` package | Provides tested ARM64 wheel with bundled libvips |
| OpenSlide dylib bundling for macOS | Homebrew install scripts | `openslide-bin` universal2 wheel | Already bundles dylib; openslide-python ≥1.4 knows to find it |
| MPS device detection | Custom `platform.system()` checks | `torch.backends.mps.is_available()` | Official PyTorch API; handles fallback edge cases |
| torch version for macOS | Manual wheel URL management | Plain `pip install torch torchvision` from PyPI | PyPI's macOS wheel includes MPS; no CUDA index needed |
| Duplicate file detection | Custom glob scripts | `git ls-files` + manual `git rm` | Git is the source of truth for what's tracked |

**Key insight:** The dependency ecosystem has matured enough that `pip install openslide-bin pyvips-binary` handles what previously required system library installations. Resist the urge to add Homebrew steps for Phase 1 (local runtime) — those are Phase 3 concerns (CI/PyInstaller).

---

## Runtime State Inventory

Not applicable — this is a greenfield dependency/code fix phase with no rename or migration involved. No stored data, service config, OS-registered state, secrets, or build artifacts are being renamed.

---

## Common Pitfalls

### Pitfall 1: Rosetta Python Makes MPS Invisible

**What goes wrong:** `torch.backends.mps.is_available()` returns `False` even on M1/M2/M3.
**Why it happens:** The Python binary was installed under Rosetta 2 (x86_64 emulation), not natively as ARM64. The MPS backend is only visible to native ARM64 processes.
**How to avoid:** Verify `python3 -c "import platform; print(platform.machine())"` returns `arm64`, not `x86_64`. If `x86_64`, reinstall Python using native ARM64 installer from python.org (3.12 ARM64) or `pyenv` with `arch -arm64` prefix.
**Warning signs:** `platform.machine()` returns `x86_64`; slow performance; MPS always unavailable.

### Pitfall 2: Cellpose MPS Sparse Tensor Crash

**What goes wrong:** Cellpose segmentation raises `NotImplementedError: Could not run 'aten::_sparse_coo_tensor_with_dims_and_tensors' with arguments from the 'SparseMPS' backend`.
**Why it happens:** Cellpose's mask creation code uses sparse tensor operations that MPS does not support. This is a known Cellpose 4.x limitation on Apple Silicon.
**How to avoid:** Cellpose 4.x documentation says "the new mask creation code is not yet supported by Mac" — the adapter must catch this exception and retry on CPU. The existing `_retry_on_cpu` path in `CellposeAdapter` covers CUDA OOM but not MPS failures. Add MPS failure detection alongside CUDA OOM detection.
**Warning signs:** `NotImplementedError` in cellpose logs during mask extraction; model forward pass succeeds but mask creation fails.

### Pitfall 3: openslide-bin Universal2 vs Old openslide-bin Windows-Only

**What goes wrong:** `import openslide` succeeds but `openslide.OpenSlide(path)` raises `OpenSlideError: Could not open file` or `ImportError: Couldn't locate OpenSlide dylib`.
**Why it happens:** Older `openslide-bin` versions (pre-4.0.0.2) only shipped Windows DLLs. The macOS support was added in 4.0.0.2. If a cached wheel from an old version is used, the dylib is absent.
**How to avoid:** Pin `openslide-bin>=4.0.0` in requirements. The current `requirements.txt` pins `>=1.4.3` which could resolve to an old Windows-only wheel (though on macOS pip would fail to find a compatible wheel and error out, rather than install silently).
**Warning signs:** `ImportError` or `OpenSlideError` when loading WSI files; `pip show openslide-bin` showing version < 4.0.0.

### Pitfall 4: NuClick Model Device Mismatch

**What goes wrong:** NuClick model weights load on CPU but input tensor is on MPS (or vice versa), causing `RuntimeError: Expected all tensors to be on the same device`.
**Why it happens:** `_load_model` sets one device and the inline `predict/predict_batch` methods recalculate device independently. If the recalculation produces a different result (e.g., race condition or state change), tensors land on different devices.
**How to avoid:** Extract device selection into a single `_get_device()` helper; store the selected device as `self._device` at load time; use `self._device` in `predict` and `predict_batch` instead of recalculating.
**Warning signs:** `RuntimeError: Expected all tensors to be on the same device, but found at least two devices`.

### Pitfall 5: `* 2.py` Files Picked Up by PyInstaller (Phase 2 risk, detected now)

**What goes wrong:** PyInstaller bundles `nuclick_adapter 2.py` as a data file alongside `nuclick_adapter.py`, inflating bundle size and potentially confusing dynamic import mechanisms.
**Why it happens:** PyInstaller's `collect_all('app')` includes all files in the `app` directory tree, not just importable `.py` files.
**How to avoid:** Delete all `* 2.py` files with `git rm` before running PyInstaller (Phase 2). Doing it now in Phase 1 is correct timing since it's a DEP-04 requirement.
**Warning signs:** `.app` bundle contains `nuclick_adapter 2.py` at build time.

### Pitfall 6: pyvips Falls Back to PIL Silently

**What goes wrong:** Large TIFF files cause memory pressure or slow loading even though pyvips is "installed".
**Why it happens:** `main.py` silently falls back to `pyvips = None` if pyvips import fails. This can happen if `pyvips-binary` is not installed alongside `pyvips` — the Python binding installs but finds no `libvips` shared library at import time.
**How to avoid:** Install `pyvips-binary` alongside `pyvips`. After install, verify `import pyvips; print(pyvips.__version__)` succeeds without error.
**Warning signs:** App startup logs `"pyvips not installed or missing libvips — falling back to PIL"`.

---

## Code Examples

### requirements-macos.txt (complete working file)

```
# requirements-macos.txt — macOS ARM64 / Apple Silicon
# No CUDA index — torch from PyPI default includes MPS support
Pillow>=10.4.0
openpyxl>=3.1.0
PyQt6>=6.0.0
openslide-python>=1.4.0
openslide-bin>=4.0.0
pyvips>=2.2.0
pyvips-binary>=8.0.0
torch>=2.0.0
torchvision>=0.15.0
cellpose>=4.0,<5.0
scikit-image>=0.21.0
opencv-python>=4.8.0
psutil>=5.9.0
scipy>=1.11.0
```

### NuClickAdapter MPS device helper (patch for `nuclick_adapter.py`)

```python
# Add this helper at module level or as a static method
def _get_torch_device() -> "torch.device":
    """Returns the best available device: CUDA > MPS > CPU."""
    import torch
    try:
        from app.infrastructure.config.gpu_selector import get_best_cuda_device
        best_gpu = get_best_cuda_device()
        if torch.cuda.is_available() and best_gpu is not None:
            return torch.device(f'cuda:{best_gpu}')
    except Exception:
        pass

    if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        return torch.device('mps')

    return torch.device('cpu')
```

Replace all three inline `device = ...` blocks in `nuclick_adapter.py` with a call to this helper. Also store the result on `self._device` in `_load_model` so `predict`/`predict_batch` can reuse it without recalculating.

### CellposeAdapter MPS failure detection (patch for `_is_cuda_oom`)

```python
@staticmethod
def _is_gpu_failure(exc: Exception) -> bool:
    """Returns True if exc is a GPU (CUDA OOM or MPS unsupported op) error."""
    msg = str(exc).lower()
    return (
        "cuda out of memory" in msg
        or "cudnn error" in msg
        or "not implemented for" in msg  # MPS sparse tensor errors
        or "could not run" in msg         # MPS NotImplementedError prefix
    )
```

Replace `_is_cuda_oom` with `_is_gpu_failure` and update its call sites so MPS failures also trigger CPU fallback.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `openslide-bin` Windows DLLs only | `openslide-bin` universal2 macOS wheel | v4.0.0.2 (2024) | No Homebrew needed for local dev |
| `pip install pyvips` requires system libvips | `pip install pyvips pyvips-binary` bundles libvips | `pyvips-binary 8.x` (2025) | No Homebrew needed for local dev |
| PyTorch MPS: "experimental" (PyTorch 1.12–2.0) | PyTorch MPS: stable for inference (PyTorch 2.x) | PyTorch 2.0 (2023) | Inference reliable; some training ops still missing |
| `openslide-python` required system libvips | `openslide-python ≥1.4` auto-finds `openslide-bin` dylib | v1.4.0 (2024) | Seamless pip-only install |

**Deprecated/outdated:**
- `openslide-bin>=1.4.3` constraint in current requirements.txt: this version range predates macOS support. Must be raised to `>=4.0.0`.
- `torch==2.6.0+cu124` on macOS: `+cu124` suffix wheels do not exist on default PyPI. Must be replaced with a plain version constraint.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Cellpose 4.x `gpu=True` auto-selects MPS when CUDA is absent on macOS | Architecture Patterns (Pattern 2), RUN-05 | Cellpose may stay on CPU even with MPS available, reducing performance; not a correctness failure |
| A2 | `pyvips-binary` includes the same format support (TIFF/PNG/JPEG) needed by `ImagePyramid` | Standard Stack | If bundled libvips lacks TIFF support, standard images won't load; fallback to PIL still applies |
| A3 | `openslide-python ≥1.4.3` auto-discovers the dylib bundled in `openslide-bin` without `DYLD_LIBRARY_PATH` | Standard Stack, RUN-04 | May need `DYLD_LIBRARY_PATH=/path/to/openslide-bin/lib` set explicitly; OS-level workaround available |

---

## Assumptions Requiring Runtime Validation

1. **Does Cellpose `gpu=True` auto-select MPS when CUDA is absent?**
   - What we know: `CellposeAdapter._runtime_gpu_available()` checks `torch.backends.mps.is_available()` and returns `True`. The model is instantiated with `gpu=self._gpu` — but Cellpose internally maps this to the appropriate device.
   - What's unclear: Whether Cellpose 4.x's internal device selection logic picks up MPS when `gpu=True` and CUDA is absent on macOS.
   - Approach: CellposeAdapter already has CPU fallback via `_retry_on_cpu` — Plan 05 verification will confirm behavior by logging `self._model.device` after loading. If CPU despite MPS being available, explicitly pass `device=torch.device('mps')` to `CellposeModel` as a follow-up.

2. **Does `openslide-python` find `openslide-bin`'s dylib automatically on macOS?**
   - What we know: `openslide-python ≥1.4` was specifically updated to support `openslide-bin`. The documentation says to install both and it "just works."
   - What's unclear: Whether the automatic dylib discovery works without `DYLD_LIBRARY_PATH` on macOS 15.5 specifically.
   - Approach: Plan 05 verification step 4 tests this explicitly on Apple Silicon hardware via `python -c "import openslide; print(openslide.OPENSLIDE_PATH)"` after install. If the path is absent, `DYLD_LIBRARY_PATH` workaround will be documented.

3. **Is there an existing `requirements-macos.txt` or `requirements-windows.txt` that the CI references?**
   - What we know: `build-macos.yml` references `requirements.txt` directly. `build-windows.yml` uses `pip install -e .[dev,cellpose,vips]`.
   - What's unclear: Whether renaming `requirements.txt` will break CI before Phase 3 fixes it.
   - Recommendation: Keep `requirements.txt` pointing to the Windows/CUDA variant (unchanged behavior for the existing broken CI) and introduce `requirements-macos.txt` as a new file. The researcher on macOS can explicitly `pip install -r requirements-macos.txt`.

---

## Environment Availability

This phase is a dependency fix (editing text files and Python code). No external services beyond pip are required to implement it. The target execution environment (Apple Silicon Mac) is not this machine (Windows). The following tools are needed to implement:

| Dependency | Required By | Available (dev machine) | Notes |
|------------|------------|--------------------------|-------|
| Python 3.12 (ARM64) | Target runtime | N/A (target is macOS) | Must be native ARM64 on target |
| git | `git rm` for `* 2.py` files | Yes (Windows dev machine) | `git rm` works on both platforms |
| pip | requirements install | Yes | |
| macOS 15.5 (Apple Silicon) | Testing RUN-01 through RUN-06 | No (dev machine is Windows) | Researcher colleague runs validation |

**Missing dependencies with no fallback:**
- Apple Silicon Mac for testing — implementation can be done on Windows, but validation requires macOS ARM64 hardware.

---

## Security Domain

No new authentication, session management, access control, cryptography, or network endpoints are introduced in this phase. The only security-adjacent concern is model download integrity (ModelDownloader fetches `nuclick.pth` from a configured URL) — this is pre-existing infrastructure and out of scope for this phase.

---

## Sources

### Primary (HIGH confidence)
- `pip index versions` — Verified current versions for all 9 packages [VERIFIED: pip registry]
- [openslide-bin PyPI search result] — Confirmed `macosx_11_0_universal2.whl` exists for 4.0.0.13 [CITED: pypi.org/project/openslide-bin]
- [pyvips-binary PyPI] — Confirmed `macosx_11_0_arm64.whl` exists for 8.18.0 [CITED: pypi.org/project/pyvips-binary]
- [PyTorch get-started page] — `pip3 install torch torchvision` for macOS; no CUDA index needed [CITED: pytorch.org/get-started/locally]
- [Cellpose docs] — MPS device supported for inference via `--gpu_device mps` [CITED: cellpose.readthedocs.io/en/latest/installation.html]

### Secondary (MEDIUM confidence)
- [PyPI pip issue #13637] — `--extra-index-url` + environment markers bug [CITED: github.com/pypa/pip/issues/13637]
- [Cellpose issue #1063] — MPS sparse tensor error during mask creation [CITED: github.com/MouseLand/cellpose/issues/1063]
- [openslide-bin image.sc announcement] — Confirmed macOS binaries added in 4.0.0.2 [CITED: forum.image.sc/t/openslide-binary-build-4-0-0-2-now-with-linux-and-macos-binaries]
- [pyvips README] — `pip install "pyvips[binary]"` for bundled libvips [CITED: libvips.github.io/pyvips/README.html]

### Tertiary (LOW confidence)
- Assumption A1 (Cellpose MPS auto-select) — requires runtime verification on Apple Silicon

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified via pip registry; platform wheel existence confirmed via PyPI
- Architecture: HIGH — code read directly from source; device selection gaps identified by inspection
- MPS inference reliability: MEDIUM — Cellpose docs confirm support; known sparse tensor limitation documented; NuClick standard CNN ops should work without issue
- Pitfalls: HIGH for DEP issues; MEDIUM for MPS runtime behavior (depends on Apple Silicon hardware)

**Research date:** 2026-05-04
**Valid until:** 2026-08-04 (90 days — PyTorch and Cellpose are stable; openslide-bin releases frequently but version floor `>=4.0.0` covers the macOS requirement)
