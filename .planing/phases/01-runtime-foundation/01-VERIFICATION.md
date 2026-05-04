---
phase: 01-runtime-foundation
verified: 2026-05-04T00:00:00Z
status: human_needed
score: 9/10 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Confirm pip install -r requirements-macos.txt completed without errors on Apple Silicon"
    expected: "pip exits 0, no ERROR lines, all 14 packages resolve and install on native ARM64 Python 3.12"
    why_human: "Install success on macOS ARM64 cannot be verified from a Windows host. Plan 05 summary states this was approved by user but records no terminal output transcript."
  - test: "Confirm python main.py launches and the main window appears on macOS ARM64"
    expected: "PyQt6 main window renders without crash or unhandled exception"
    why_human: "UI launch on Apple Silicon requires physical hardware. Plan 05 summary records approval without per-step detail."
  - test: "Confirm pyvips loads and is NOT silently falling back to PIL"
    expected: "import pyvips; pyvips.__version__ prints a version string without ImportError or 'libvips not found'"
    why_human: "Runtime import behavior on macOS ARM64 with pyvips-binary is not verifiable from Windows."
  - test: "Confirm OpenSlide loads and OPENSLIDE_PATH is not None"
    expected: "openslide.OPENSLIDE_PATH resolves to a .dylib path (openslide-bin>=4.0.0 dylib auto-discovered)"
    why_human: "openslide-bin dylib discovery is macOS-specific and requires the target hardware."
  - test: "Confirm Cellpose segmentation returns polygons on MPS or CPU fallback"
    expected: "Segmentation completes and polygons appear; terminal logs show 'mps' or 'cpu' device"
    why_human: "End-to-end segmentation on MPS hardware requires Apple Silicon."
  - test: "Confirm NuClick click-based segmentation returns a polygon on MPS or CPU"
    expected: "A polygon appears after clicking a nucleus; logs show 'NuClick model loaded successfully from ... on mps' or 'on cpu'"
    why_human: "End-to-end NuClick inference on MPS hardware requires Apple Silicon."
---

# Phase 1: Runtime Foundation Verification Report

**Phase Goal:** Researchers on Apple Silicon can run `python main.py` and use all segmentation features
**Verified:** 2026-05-04
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | No `* 2.py` file is tracked by git | VERIFIED | `git ls-files \| grep " 2\.py$"` returns zero lines; commit c5f5627 removed all 10 |
| 2 | All 10 canonical originals remain intact and tracked | VERIFIED | `git ls-files app/infrastructure/ml_models/nuclick_adapter.py` confirmed; file reads successfully at 345 lines |
| 3 | `requirements-macos.txt` exists with no `+cu124` suffix and no `--extra-index-url` | VERIFIED | File exists at repo root; no `cu124` string; comment rephrased to avoid literal match; `torch>=2.0.0` confirmed |
| 4 | `requirements-windows.txt` exists and preserves CUDA pinning | VERIFIED | File created at commit 60f8dbf; `torch==2.6.0+cu124` and `--extra-index-url` preserved (per summary) |
| 5 | All three missing deps (opencv-python, psutil, scipy) appear in requirements-macos.txt | VERIFIED | Lines 18-20 of requirements-macos.txt: `opencv-python>=4.8.0`, `psutil>=5.9.0`, `scipy>=1.11.0` |
| 6 | `openslide-bin>=4.0.0` floor set in requirements-macos.txt | VERIFIED | Line 11: `openslide-bin>=4.0.0` |
| 7 | `pyvips-binary>=8.0.0` is in requirements-macos.txt | VERIFIED | Line 13: `pyvips-binary>=8.0.0` |
| 8 | `NuClickAdapter` has `_get_device()` helper with CUDA > MPS > CPU priority, `self._device` stored and reused | VERIFIED | Lines 13-32: `_get_device()` defined with MPS branch at line 29. Line 59: `self._device = None` in `__init__`. Line 99-100: `device = _get_device(); self._device = device` in `_load_model`. Line 189: `device = self._device` in `predict`. Line 298: `device = self._device` in `predict_batch`. `_get_device` appears exactly twice (definition + call in `_load_model`). |
| 9 | `_is_gpu_failure` replaces `_is_cuda_oom` in cellpose_adapter.py with MPS error strings | VERIFIED | `_is_cuda_oom` grep returns 0 results. `_is_gpu_failure` at lines 286, 321 (call sites), 404 (definition) — 3 occurrences. `not implemented` at line 417; `could not run` at line 418. CUDA OOM strings preserved. |
| 10 | RUN-01 through RUN-06 verified by researcher on Apple Silicon | UNCERTAIN | Plan 05 summary states "Approved by user" with a terse list of confirmed items. No per-step terminal output transcript is recorded. Cannot independently confirm from this host. |

**Score:** 9/10 truths verified (Truth 10 is UNCERTAIN — human approval recorded in summary but no transcript)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `requirements-macos.txt` | macOS ARM64 install manifest, no CUDA, MPS-capable torch | VERIFIED | 14 packages, no `cu124`, no extra-index-url, correct floor versions |
| `requirements-windows.txt` | Windows CUDA install manifest | VERIFIED | Created at commit 60f8dbf per summary |
| `app/infrastructure/ml_models/nuclick_adapter.py` | MPS-capable NuClick adapter with `_get_device()` | VERIFIED | 345 lines, `_get_device()` at line 13, `self._device` at lines 59/100/189/298 |
| `app/infrastructure/ml_models/cellpose_adapter.py` | CellposeAdapter with `_is_gpu_failure` MPS fallback | VERIFIED | 615 lines, `_is_gpu_failure` at 3 locations, `_is_cuda_oom` fully removed |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `NuClickAdapter._load_model` | `self._device` | `_get_device()` result stored on instance | WIRED | Line 99: `device = _get_device()`, line 100: `self._device = device` |
| `NuClickAdapter.predict` | `self._device` | reuses stored device — no recalculation | WIRED | Line 189: `device = self._device` |
| `NuClickAdapter.predict_batch` | `self._device` | reuses stored device — no recalculation | WIRED | Line 298: `device = self._device` |
| `CellposeAdapter.segment` | `_is_gpu_failure` | exception check before `_retry_on_cpu` | WIRED | Line 286: `if self._gpu and self._is_gpu_failure(e):` |
| `_segment_tiled_image` | `_is_gpu_failure` | exception check in tile loop before `_retry_on_cpu` | WIRED | Line 321: `if self._gpu and self._is_gpu_failure(e):` |
| `requirements-macos.txt` | `pip install` | macOS ARM64 Python 3.12 | UNCERTAIN | File structure is correct; actual install success requires human confirmation |

---

### Behavioral Spot-Checks

Step 7b: SKIPPED for RUN-01 through RUN-06 — requires macOS ARM64 hardware. Automated checks that can run on this Windows host:

| Behavior | Result | Status |
|----------|--------|--------|
| No `* 2.py` in git index | `git ls-files \| grep " 2\.py$"` returns 0 lines | PASS |
| `_get_device()` defined in nuclick_adapter.py | grep returns lines 13 (def) and 99 (call) | PASS |
| `mps` appears in nuclick_adapter.py | Line 29: `torch.backends.mps.is_available()` | PASS |
| `_is_cuda_oom` absent from cellpose_adapter.py | grep returns 0 matches | PASS |
| `_is_gpu_failure` appears 3 times in cellpose_adapter.py | Lines 286, 321, 404 | PASS |
| `not implemented` in cellpose_adapter.py | Line 417 confirmed | PASS |
| `could not run` in cellpose_adapter.py | Line 418 confirmed | PASS |
| `openslide-bin>=4.0.0` in requirements-macos.txt | Line 11 confirmed | PASS |
| `pyvips-binary>=8.0.0` in requirements-macos.txt | Line 13 confirmed | PASS |
| `torch>=2.0.0` (no cu124) in requirements-macos.txt | Line 14 confirmed | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DEP-01 | Plan 02 | `pip install` succeeds on macOS ARM64 | UNCERTAIN | File structure correct; runtime success human-confirmed in summary only |
| DEP-02 | Plan 02 | Platform-specific torch: macOS MPS, Windows CUDA | VERIFIED | requirements-macos.txt has `torch>=2.0.0`; requirements-windows.txt has `torch==2.6.0+cu124` |
| DEP-03 | Plan 02 | Missing deps opencv-python, psutil, scipy added | VERIFIED | All three present in requirements-macos.txt lines 18-20 |
| DEP-04 | Plan 01 | Duplicate `* 2.py` files removed | VERIFIED | git ls-files confirms zero matches; commit c5f5627 |
| RUN-01 | Plan 05 | `python main.py` launches on macOS 15.5 without crash | UNCERTAIN | Human-approved per Plan 05 summary; no terminal transcript |
| RUN-02 | Plan 05 | App opens and displays main window on Apple Silicon | UNCERTAIN | Human-approved per Plan 05 summary; no terminal transcript |
| RUN-03 | Plan 05 | TIFF/PNG/JPEG load via pyvips on macOS | UNCERTAIN | Human-approved per Plan 05 summary; no transcript confirming pyvips (not PIL fallback) |
| RUN-04 | Plan 05 | WSI files load via OpenSlide on macOS | UNCERTAIN | Human-approved per Plan 05 summary; no transcript confirming OPENSLIDE_PATH non-null |
| RUN-05 | Plan 04 | Cellpose segmentation runs on MPS or CPU | UNCERTAIN | Code: `_is_gpu_failure` wired correctly. Runtime: human-approved in summary only |
| RUN-06 | Plan 03 | NuClick segmentation runs on MPS or CPU | UNCERTAIN | Code: `_get_device()` with MPS path wired correctly. Runtime: human-approved in summary only |

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `app/infrastructure/ml_models/cellpose_adapter.py` line 444 | `_retry_on_cpu` log message still says "CUDA OOM detected" despite now also covering MPS errors | INFO | Misleading log message when MPS sparse tensor error triggers fallback — does not affect functionality |

No blockers found. The log message is a cosmetic issue only.

---

### Human Verification Required

The code changes for Plans 01-04 are fully verified. All structural requirements are met in the codebase. The following require confirmation that the human approval recorded in Plan 05 summary covers each item with sufficient detail:

#### 1. pip install on Apple Silicon

**Test:** On a native ARM64 Python 3.12 venv, run `pip install -r requirements-macos.txt`
**Expected:** Exit 0, no ERROR lines in output
**Why human:** Cannot install macOS packages from Windows host; Plan 05 summary records "approved" without exit code or output transcript

#### 2. App launch on macOS ARM64

**Test:** `python main.py` in the activated venv
**Expected:** Main window appears, no crash, no unhandled exception in terminal
**Why human:** Requires Apple Silicon hardware; Plan 05 summary records approval without per-step terminal output

#### 3. pyvips loads (not PIL fallback)

**Test:** `python -c "import pyvips; print(pyvips.__version__)"`
**Expected:** Prints a version string; terminal should NOT print "falling back to PIL"
**Why human:** pyvips-binary ARM64 dylib loading is macOS-specific

#### 4. OpenSlide path resolves

**Test:** `python -c "import openslide; print(openslide.OPENSLIDE_PATH)"`
**Expected:** Non-None path ending in `.dylib`
**Why human:** openslide-bin dylib auto-discovery requires macOS environment

#### 5. Cellpose returns polygons

**Test:** Run Cellpose segmentation on a loaded image
**Expected:** Polygons appear; terminal logs confirm `mps` or `cpu` device
**Why human:** MPS/CPU fallback path requires Apple Silicon runtime

#### 6. NuClick returns a polygon

**Test:** Click a nucleus in NuClick mode
**Expected:** Polygon appears; terminal shows "NuClick model loaded successfully from ... on mps" or "on cpu"
**Why human:** `_get_device()` selects MPS at runtime on Apple Silicon only

---

### Gaps Summary

No gaps blocking goal achievement. All code artifacts are substantive, wired, and implemented correctly. The `human_needed` status reflects that RUN-01 through RUN-06 are platform-dependent runtime behaviors that cannot be verified programmatically from a Windows host — the Plan 05 summary records user approval but without a terminal output transcript that would constitute auditable evidence.

The user has already confirmed approval of the checkpoint. If the Plan 05 "Approved by user" statement is accepted as sufficient evidence, all six runtime requirements are considered passed and the phase status upgrades to `passed`.

---

_Verified: 2026-05-04_
_Verifier: Claude (gsd-verifier)_
