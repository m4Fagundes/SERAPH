# Requirements: Grid Image Analyzer — macOS Port

**Defined:** 2026-05-04
**Core Value:** Researchers on Apple Silicon Macs can download a `.dmg`, open the app, load whole-slide images, and run nucleus segmentation with MPS acceleration — without any Python setup.

## v1 Requirements

### Dependencies

- [ ] **DEP-01**: `pip install -r requirements.txt` succeeds on macOS ARM64 without errors
- [ ] **DEP-02**: Platform-specific PyTorch installed: macOS uses CPU/MPS wheels, Windows keeps CUDA `+cu124`
- [ ] **DEP-03**: Missing runtime deps (`opencv-python`, `psutil`, `scipy`) added to `requirements.txt`
- [ ] **DEP-04**: Duplicate `* 2.py` files removed from codebase

### Runtime

- [ ] **RUN-01**: `python main.py` launches the app on macOS 15.5 without crash
- [ ] **RUN-02**: App opens and displays main window on Apple Silicon
- [ ] **RUN-03**: Standard images (TIFF, PNG, JPEG) load via pyvips on macOS
- [ ] **RUN-04**: Whole-slide images (NDPI, SVS, MRXS) load via OpenSlide on macOS
- [ ] **RUN-05**: Cellpose segmentation runs and returns results using MPS or CPU
- [ ] **RUN-06**: NuClick click-based segmentation runs and returns results using MPS or CPU

### Distribution

- [ ] **DIST-01**: PyInstaller produces a valid `.app` bundle for ARM64
- [ ] **DIST-02**: `.app` opens on macOS 15.5 without any Python installation
- [ ] **DIST-03**: `.dmg` disk image created from `.app` and downloadable
- [ ] **DIST-04**: Segmentation works inside the `.app` bundle (libvips, openslide dylibs bundled)
- [ ] **DIST-05**: Colleague can open `.dmg`, drag to Applications, and use app after running `xattr -d com.apple.quarantine`

### CI/CD

- [ ] **CI-01**: GitHub Actions `build-macos.yml` runs successfully on `macos-14` (ARM64) runner
- [ ] **CI-02**: CI installs Homebrew dependencies (`libvips`, `openslide`) before building
- [ ] **CI-03**: CI produces `.app` and `.dmg` artifacts available for download
- [ ] **CI-04**: CI correctly references `docs/build/main_release.spec`

## v2 Requirements

### Extended Platform Support

- **V2-01**: Universal binary (fat binary) for Intel + Apple Silicon
- **V2-02**: macOS code signing and notarization (Apple Developer account required)
- **V2-03**: macOS 26 (Tahoe) runner in CI when GitHub Actions supports it

## Out of Scope

| Feature | Reason |
|---------|--------|
| Intel Mac (x86_64) | Focus on Apple Silicon; Intel Macs rare in current research labs |
| Code signing / notarization | No Apple Developer account; colleagues use quarantine workaround |
| Windows build changes | Existing Windows CI stays untouched |
| Performance tuning beyond MPS | MPS baseline is sufficient for v1 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEP-01 | Phase 1 | Pending |
| DEP-02 | Phase 1 | Pending |
| DEP-03 | Phase 1 | Pending |
| DEP-04 | Phase 1 | Pending |
| RUN-01 | Phase 1 | Pending |
| RUN-02 | Phase 1 | Pending |
| RUN-03 | Phase 1 | Pending |
| RUN-04 | Phase 1 | Pending |
| RUN-05 | Phase 1 | Pending |
| RUN-06 | Phase 1 | Pending |
| DIST-01 | Phase 2 | Pending |
| DIST-02 | Phase 2 | Pending |
| DIST-03 | Phase 2 | Pending |
| DIST-04 | Phase 2 | Pending |
| DIST-05 | Phase 2 | Pending |
| CI-01 | Phase 3 | Pending |
| CI-02 | Phase 3 | Pending |
| CI-03 | Phase 3 | Pending |
| CI-04 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-04*
*Last updated: 2026-05-04 after initial definition*
