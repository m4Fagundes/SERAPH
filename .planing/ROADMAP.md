# Roadmap: Grid Image Analyzer — macOS Port

## Overview

Three phases deliver the macOS port from zero to automated CI artifact. Phase 1 gets the app running locally on Apple Silicon. Phase 2 packages it into a distributable `.dmg`. Phase 3 automates the build in GitHub Actions so future releases happen without manual effort.

## Phases

- [ ] **Phase 1: Runtime Foundation** - Fix dependencies and get `python main.py` running on macOS ARM64
- [ ] **Phase 2: Distribution** - Produce a `.app` bundle and `.dmg` that colleagues can use without Python
- [ ] **Phase 3: CI/CD** - GitHub Actions builds `.dmg` automatically on every push

## Phase Details

### Phase 1: Runtime Foundation
**Goal**: Researchers on Apple Silicon can run `python main.py` and use all segmentation features
**Depends on**: Nothing (first phase)
**Requirements**: DEP-01, DEP-02, DEP-03, DEP-04, RUN-01, RUN-02, RUN-03, RUN-04, RUN-05, RUN-06
**Success Criteria** (what must be TRUE):
  1. `pip install -r requirements-macos.txt` completes without errors on macOS ARM64
  2. `python main.py` launches and displays the main window on Apple Silicon
  3. TIFF, PNG, JPEG, and whole-slide images (NDPI, SVS, MRXS) load and render correctly
  4. Cellpose batch segmentation runs and returns results (MPS or CPU fallback)
  5. NuClick click-based segmentation runs and returns results (MPS or CPU fallback)
**Plans**: 5 plans

Plans:
- [ ] 01-PLAN-01.md — Remove 10 duplicate `* 2.py` files via git rm (DEP-04)
- [ ] 01-PLAN-02.md — Create requirements-macos.txt and requirements-windows.txt (DEP-01, DEP-02, DEP-03)
- [ ] 01-PLAN-03.md — Patch NuClickAdapter with _get_device() MPS helper (RUN-06)
- [ ] 01-PLAN-04.md — Extend CellposeAdapter GPU fallback to catch MPS errors (RUN-05)
- [ ] 01-PLAN-05.md — Runtime verification checkpoint on Apple Silicon (RUN-01–06)

### Phase 2: Distribution
**Goal**: A colleague can download a `.dmg`, drag the app to Applications, and use it without installing Python
**Depends on**: Phase 1
**Requirements**: DIST-01, DIST-02, DIST-03, DIST-04, DIST-05
**Success Criteria** (what must be TRUE):
  1. PyInstaller produces a valid `.app` bundle that opens on macOS 15.5 without any Python installation
  2. Image loading and segmentation work inside the `.app` bundle (libvips and openslide dylibs bundled)
  3. `.dmg` disk image is created, mounts cleanly, and the app runs after `xattr -d com.apple.quarantine`
**Plans**: TBD

### Phase 3: CI/CD
**Goal**: GitHub Actions builds and publishes a `.dmg` artifact automatically without manual intervention
**Depends on**: Phase 2
**Requirements**: CI-01, CI-02, CI-03, CI-04
**Success Criteria** (what must be TRUE):
  1. `build-macos.yml` workflow runs to completion on a `macos-14` (ARM64) runner
  2. CI installs Homebrew deps (`libvips`, `openslide`) and correctly references `docs/build/main_release.spec`
  3. `.app` and `.dmg` artifacts are available for download from the workflow run
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Runtime Foundation | 0/5 | Planned | - |
| 2. Distribution | 0/? | Not started | - |
| 3. CI/CD | 0/? | Not started | - |
