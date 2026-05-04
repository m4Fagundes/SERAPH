---
phase: 1
plan: 4
subsystem: ml_models
tags: [cellpose, mps, gpu-fallback, apple-silicon]
dependency_graph:
  requires: [01-02]
  provides: [RUN-05]
  affects: [cellpose_adapter]
tech_stack:
  added: []
  patterns: [gpu-to-cpu-fallback, mps-error-detection]
key_files:
  modified:
    - app/infrastructure/ml_models/cellpose_adapter.py
decisions:
  - "_is_cuda_oom renamed to _is_gpu_failure to cover both CUDA OOM and MPS unsupported-op errors without touching _retry_on_cpu or _clear_cuda_cache"
metrics:
  duration: "~5 minutes"
  completed: "2026-05-04"
  tasks_completed: 1
  tasks_total: 1
---

# Phase 1 Plan 4: Patch CellposeAdapter MPS Fallback Summary

Extended `CellposeAdapter._is_cuda_oom` into `_is_gpu_failure` — adding MPS `NotImplementedError` and `Could not run` sparse-backend checks so CPU fallback triggers on Apple Silicon as well as CUDA OOM.

## What Was Built

`_is_gpu_failure` replaces `_is_cuda_oom` in `cellpose_adapter.py`. The method now covers four GPU failure patterns:

| String checked | Error covered |
|---|---|
| `cuda out of memory` | CUDA OOM (existing) |
| `cudnn error` | cuDNN errors (existing) |
| `not implemented` | MPS `NotImplementedError` for sparse tensor ops |
| `could not run` | MPS `SparseMPS` backend errors |

Both call sites (`segment()` line 286 and `_segment_tiled_image()` line 321) were updated. The `_retry_on_cpu` and `_clear_cuda_cache` methods were not renamed — their names remain accurate.

## GitNexus Impact Analysis — _is_cuda_oom

```
risk: LOW
direct callers (d=1): segment(), _segment_tiled_image()  — both in cellpose_adapter.py
indirect (d=2): test_adapter_with_sample_image, segment_with_cellpose
modules affected: Ml_models (direct), Scripts (indirect)
```

No HIGH or CRITICAL risk. All direct callers are within the same file and were updated as part of this patch.

## gitnexus_rename Dry-Run

`gitnexus rename` is not available in the CLI (MCP-only tool). Impact analysis confirmed the only callers are `segment()` and `_segment_tiled_image()` inside `cellpose_adapter.py`. The rename was performed with targeted Edit calls on the definition and both call sites — equivalent to a safe graph-aware rename given the symbol has no external callers.

## Verification Results

```
grep -c "_is_cuda_oom" cellpose_adapter.py  → 0  (PASS: old name removed)
grep -n "_is_gpu_failure" cellpose_adapter.py:
  line 286: call site 1 — segment()
  line 321: call site 2 — _segment_tiled_image()
  line 404: definition

grep -n "not implemented" → line 417  (PASS)
grep -n "could not run"   → line 418  (PASS)
Python syntax check       → syntax OK
```

## Updated Call Sites

**Call site 1 — `segment()`, line 286:**
```python
if self._gpu and self._is_gpu_failure(e):
    return self._retry_on_cpu(
        image, diameter, _flow, _cellprob, original_error=e,
    )
```

**Call site 2 — `_segment_tiled_image()`, line 321:**
```python
if self._gpu and self._is_gpu_failure(e):
    tile_polygons = self._retry_on_cpu(
        tile, diameter, flow_threshold, cellprob_threshold,
        original_error=e,
    )
```

## Backward Compatibility

CUDA OOM behavior is fully preserved. The original `"cuda out of memory"` and `"cudnn error"` string checks remain in the method body. Windows/CUDA paths are unaffected.

## Deviations from Plan

**[Rule 3 - Blocking] gitnexus_rename CLI unavailable**
- Found during: T1 pre-edit
- Issue: `npx gitnexus rename` exits with "unknown command" — the rename subcommand is MCP-only (not in CLI v1.6.1)
- Fix: Performed the rename via three targeted Edit calls (definition + 2 call sites). Impact analysis confirmed no external callers exist, making the manual rename fully safe
- Files modified: cellpose_adapter.py only
- Commit: bc96641

None in logic or scope.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced.

## Self-Check: PASSED

- `app/infrastructure/ml_models/cellpose_adapter.py` modified and committed
- Commit `bc96641` exists: `feat(01-04): extend GPU fallback to catch MPS sparse tensor errors in CellposeAdapter (RUN-05)`
- `_is_cuda_oom`: 0 occurrences remaining
- `_is_gpu_failure`: 3 occurrences (1 definition + 2 call sites)
- MPS error strings `not implemented` and `could not run` present at lines 417-418
