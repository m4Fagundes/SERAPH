# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-04)

**Core value:** Researchers on Apple Silicon Macs can download a `.dmg`, open the app, load whole-slide images, and run nucleus segmentation with MPS acceleration — without any Python setup.
**Current focus:** Phase 2 — Distribution

## Current Position

Phase: 2 of 3 (Distribution)
Plan: 1 of 3 in current phase
Status: Phase 2 Plan 1 complete — 2 plans remaining in Phase 2
Last activity: 2026-05-04 — Phase 2 Plan 1 executed (spec + runtime hooks fixed for macOS dylib discovery)

Progress: [██░░░░░░░░] 33%

## Performance Metrics

**Velocity:**
- Total plans completed: 1
- Average duration: 2 min
- Total execution time: 0.03 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 02-distribution | 1 | 2 min | 2 min |

**Recent Trend:**
- Last 5 plans: 02-01 (2 min)
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Split requirements.txt by platform: macOS uses CPU/MPS wheels, Windows keeps `+cu124`
- Skip code signing for now: no Apple Developer account; colleagues use `xattr -d com.apple.quarantine`
- ARM64-only (no universal binary): simpler build; Intel Macs are rare in research labs
- COLLECT name changed from 'GridAnalyzer.app' to 'GridAnalyzer' to avoid name clash with BUNDLE step (02-01)
- DYLD_LIBRARY_PATH chosen over VIPS_LIBDIR because pyvips does not read VIPS_LIBDIR directly (02-01)
- rthook_portable.py registered in runtime_hooks preemptively — CI plan (Phase 3) will create the file (02-01)

### Pending Todos

None yet.

### Blockers/Concerns

- All Phase 1 blockers addressed in plans:
  - DEP-04 duplicate files → Plan 01 (git rm)
  - openslide-bin macOS support → openslide-bin>=4.0.0 in requirements-macos.txt (Plan 02)
  - build-macos.yml broken → addressed in Phase 3 (CI/CD)

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | Universal binary (Intel + Apple Silicon) | Deferred | Init |
| v2 | Code signing / notarization | Deferred | Init |
| v2 | macOS 26 (Tahoe) CI runner | Deferred | Init |

## Session Continuity

Last session: 2026-05-04T20:04:46Z
Stopped at: Completed 02-01-PLAN.md — PyInstaller spec + runtime hooks for macOS dylib discovery
Resume file: None
