---
phase: 02-distribution
plan: 01
subsystem: infra
tags: [pyinstaller, openslide, pyvips, dylib, macos, runtime-hooks]

# Dependency graph
requires:
  - phase: 01-runtime-foundation
    provides: requirements-macos.txt with openslide-bin>=4.0.0 and pyvips-binary pinned
provides:
  - PyInstaller spec that bundles openslide dylibs and libvips on macOS ARM64
  - rthook_openslide.py with macOS DYLD_LIBRARY_PATH branch
  - rthook_pyvips.py setting libvips search path inside sys._MEIPASS at bundle startup
affects: [03-cicd, pyinstaller-build, macos-bundle]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Runtime hook dual-platform pattern: separate win32/darwin branches in frozen guard"
    - "DYLD_LIBRARY_PATH prepend pattern for ctypes dylib discovery inside _MEIPASS"
    - "rglob + candidate-dir fallback pattern for dylib location under changing PyInstaller layouts"

key-files:
  created:
    - hooks/rthook_pyvips.py
  modified:
    - docs/build/main_release.spec
    - hooks/rthook_openslide.py

key-decisions:
  - "COLLECT name changed from 'GridAnalyzer.app' to 'GridAnalyzer' to avoid name clash with BUNDLE step on macOS"
  - "pyvips and pyvips_binary added to IS_MAC collect branch — ctypes-based binding not auto-discovered by PyInstaller"
  - "DYLD_LIBRARY_PATH chosen over VIPS_LIBDIR because pyvips does not read VIPS_LIBDIR directly"
  - "rthook_portable.py added to runtime_hooks for future portable-mode support (stub file expected in CI plan)"

patterns-established:
  - "Platform branching in runtime hooks: if sys.platform == 'win32' / elif sys.platform == 'darwin'"
  - "rglob search + explicit candidate dirs ensures dylib found regardless of pyvips_binary internal layout changes"

requirements-completed: [DIST-01, DIST-04]

# Metrics
duration: 2min
completed: 2026-05-04
---

# Phase 2 Plan 1: Fix PyInstaller Spec and Runtime Hooks for macOS dylib Discovery Summary

**PyInstaller spec updated to bundle openslide dylibs and libvips on macOS ARM64 via IS_MAC collection branch, corrected COLLECT name, and two new runtime hooks that set DYLD_LIBRARY_PATH before ctypes-based bindings import.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-05-04T20:02:33Z
- **Completed:** 2026-05-04T20:04:46Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added IS_MAC branch to `packages_to_collect` — PyInstaller now copies `openslide_bin`, `pyvips`, and `pyvips_binary` into `_MEIPASS` on macOS
- Fixed COLLECT `name='GridAnalyzer.app'` → `name='GridAnalyzer'` to avoid the name clash where COLLECT and BUNDLE both produced `GridAnalyzer.app` (BUNDLE kept its name unchanged)
- Extended `rthook_openslide.py` with a `darwin` branch using `DYLD_LIBRARY_PATH` so the ctypes loader finds `libopenslide.dylib` inside the bundle
- Created `rthook_pyvips.py` — new frozen-guard hook that prepends pyvips_binary candidate dirs to `DYLD_LIBRARY_PATH`, enabling `ctypes.util.find_library('vips')` to succeed at bundle startup

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix main_release.spec — macOS library collection and COLLECT name** - `1a24cb5` (feat)
2. **Task 2: Fix rthook_openslide.py for macOS dylib discovery + create rthook_pyvips.py** - `44b73e8` (feat)

**Plan metadata:** _(docs commit below)_

## Files Created/Modified

- `docs/build/main_release.spec` - Added IS_MAC collection branch, rthook_pyvips + rthook_portable in runtime_hooks, COLLECT name fix, pyvips hiddenimport
- `hooks/rthook_openslide.py` - Refactored into _add_dll_directory/_add_dylib_directory helpers; added darwin branch with DYLD_LIBRARY_PATH
- `hooks/rthook_pyvips.py` - New file; sets DYLD_LIBRARY_PATH for libvips inside sys._MEIPASS; rglob + candidate-dir search

## Decisions Made

- COLLECT name was `'GridAnalyzer.app'` causing a name collision with BUNDLE on macOS — changed to `'GridAnalyzer'` so COLLECT produces the staging directory and BUNDLE wraps it as the `.app`
- `pyvips` added to `hiddenimports` (in addition to `collect_all`) because PyInstaller misses cffi internals via static analysis alone
- `rthook_portable.py` added to `runtime_hooks` list preemptively — CI/CD plan (Phase 3) will create the actual file; registering it now avoids a second spec edit

## Deviations from Plan

None — plan executed exactly as written. All 13 automated verification checks passed on first run.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Spec and runtime hooks are ready for a `pyinstaller --clean --noconfirm docs/build/main_release.spec` run on macOS ARM64
- Phase 3 (CI/CD) must create `hooks/rthook_portable.py` (already registered in `runtime_hooks`) and wire up the GitHub Actions build workflow
- No blockers for Phase 3 execution

## Self-Check: PASSED

- docs/build/main_release.spec: FOUND
- hooks/rthook_openslide.py: FOUND
- hooks/rthook_pyvips.py: FOUND
- .planing/phases/02-distribution/02-1-SUMMARY.md: FOUND
- Commit 1a24cb5: FOUND
- Commit 44b73e8: FOUND
- All 13 plan verification checks: PASSED

---
*Phase: 02-distribution*
*Completed: 2026-05-04*
