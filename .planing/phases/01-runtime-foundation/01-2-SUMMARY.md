---
phase: 1
plan: 2
title: "Split requirements by platform — create requirements-macos.txt"
subsystem: dependencies
tags: [requirements, macos, windows, torch, cuda, mps, platform-split]
requirements: [DEP-01, DEP-02, DEP-03]
key-decisions:
  - "Split requirements by platform — macOS uses CPU/MPS wheels, Windows keeps +cu124 pinning"
  - "Rephrase comment in requirements-macos.txt to avoid literal extra-index-url string (acceptance criterion)"
metrics:
  duration: "~5 minutes"
  completed: "2026-05-04"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
key-files:
  created:
    - requirements-macos.txt
    - requirements-windows.txt
  modified: []
---

# Phase 1 Plan 2: Split Requirements by Platform Summary

**One-liner:** Platform-split pip requirements — macOS ARM64 with MPS-capable torch and bundled native libs, Windows with pinned CUDA 12.4 torch wheels and three missing runtime deps added to both files.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| T1 | Create requirements-macos.txt | 9dea00f | requirements-macos.txt |
| T2 | Create requirements-windows.txt, commit both | 9dea00f | requirements-windows.txt |

## Packages Added / Changed per File

### requirements-macos.txt (new file)

| Package | Value | Note |
|---------|-------|------|
| torch | `>=2.0.0` | No CUDA suffix — MPS bundled in standard wheel |
| torchvision | `>=0.15.0` | No CUDA suffix |
| openslide-python | `>=1.4.0` | Auto-discovers openslide-bin |
| openslide-bin | `>=4.0.0` | macOS dylib support (was 1.4.3 on Windows) |
| pyvips | `>=2.2.0` | pyvips Python bindings |
| pyvips-binary | `>=8.0.0` | Bundles libvips ARM64 (new — not in requirements.txt) |
| opencv-python | `>=4.8.0` | DEP-03 — was missing |
| psutil | `>=5.9.0` | DEP-03 — was missing |
| scipy | `>=1.11.0` | DEP-03 — was missing |
| No `--extra-index-url` | — | Avoids pip bug #13637 with platform markers |

### requirements-windows.txt (new file)

| Package | Value | Note |
|---------|-------|------|
| torch | `==2.6.0+cu124` | Preserved from requirements.txt |
| torchvision | `==0.21.0+cu124` | Preserved from requirements.txt |
| openslide-python | `>=1.3.1` | Preserved from requirements.txt |
| openslide-bin | `>=1.4.3` | Preserved from requirements.txt |
| opencv-python | `>=4.8.0` | DEP-03 — was missing from requirements.txt |
| psutil | `>=5.9.0` | DEP-03 — was missing from requirements.txt |
| scipy | `>=1.11.0` | DEP-03 — was missing from requirements.txt |
| `--extra-index-url` | pytorch CUDA 12.4 index | Preserved from requirements.txt |

### requirements.txt

Not modified. Content identical to original.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Comment in requirements-macos.txt contained literal "extra-index-url" string**
- **Found during:** T1 acceptance verification
- **Issue:** The comment `# Do NOT add --extra-index-url here` caused `grep "extra-index-url" requirements-macos.txt` to return a match, failing the acceptance criterion
- **Fix:** Rephrased comment to `# Do NOT add a PyTorch custom index here` — functionally equivalent, no grep match
- **Files modified:** requirements-macos.txt
- **Commit:** 9dea00f (included in same commit)

## Confirmation: requirements.txt Unchanged

Original content (11 lines):
- `# Runtime dependencies`
- `--extra-index-url https://download.pytorch.org/whl/cu124`
- `Pillow>=10.4.0`, `openpyxl>=3.1.0`, `PyQt6>=6.0.0`
- `openslide-python>=1.3.1`, `openslide-bin>=1.4.3`
- `torch==2.6.0+cu124`, `torchvision==0.21.0+cu124`
- `cellpose>=4.0,<5.0`, `scikit-image>=0.21.0`

No modifications were made to this file.

## Self-Check
