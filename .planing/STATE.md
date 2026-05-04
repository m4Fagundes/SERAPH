# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-04)

**Core value:** Researchers on Apple Silicon Macs can download a `.dmg`, open the app, load whole-slide images, and run nucleus segmentation with MPS acceleration — without any Python setup.
**Current focus:** Phase 1 — Runtime Foundation

## Current Position

Phase: 1 of 3 (Runtime Foundation)
Plan: 0 of 5 in current phase
Status: Ready to execute
Last activity: 2026-05-04 — Phase 1 planned (5 plans, 3 waves)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: none yet
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Split requirements.txt by platform: macOS uses CPU/MPS wheels, Windows keeps `+cu124`
- Skip code signing for now: no Apple Developer account; colleagues use `xattr -d com.apple.quarantine`
- ARM64-only (no universal binary): simpler build; Intel Macs are rare in research labs

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

Last session: 2026-05-04
Stopped at: Phase 1 planned — ready to execute (5 plans in 3 waves)
Resume file: None
