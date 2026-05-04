# Grid Image Analyzer — macOS Port

## What This Is

Desktop scientific image analysis tool (PyQt6 + Python) that allows researchers to annotate microscopy images using grid tiles and run AI-powered nucleus segmentation (Cellpose, NuClick). Currently works on Windows with CUDA GPU. This milestone ports the app to **Apple Silicon Macs** (macOS 15.5 Sequoia and macOS 26 Tahoe), producing a distributable `.dmg` for researcher colleagues.

## Core Value

Researchers on Apple Silicon Macs can download a `.dmg`, open the app, load whole-slide images, and run nucleus segmentation with MPS acceleration — without any Python setup.

## Requirements

### Validated

- ✓ PyQt6 GUI with macro/micro dual-view — existing
- ✓ Grid tile annotation — existing
- ✓ Cellpose 4.x batch segmentation (Windows/CUDA) — existing
- ✓ NuClick click-based segmentation (Windows) — existing
- ✓ TIFF/PNG/JPEG via pyvips — existing
- ✓ NDPI/SVS/MRXS via OpenSlide — existing
- ✓ Project save/load (.lab JSON format) — existing
- ✓ Export (GeoJSON, XML, JSON) — existing
- ✓ Model auto-download infrastructure — existing

### Active

- [ ] `pip install` succeeds on macOS ARM64 (fix CUDA-only torch deps)
- [ ] `python main.py` runs without crash on macOS 15.5+
- [ ] Cellpose segmentation runs via MPS on Apple Silicon
- [ ] NuClick segmentation runs via MPS on Apple Silicon
- [ ] pyvips works on macOS (libvips via Homebrew or bundled)
- [ ] OpenSlide works on macOS (openslide dylibs bundled)
- [ ] PyInstaller produces valid `.app` bundle on ARM64
- [ ] `.dmg` distributable created and openable by colleagues
- [ ] GitHub Actions CI builds `.dmg` for Apple Silicon automatically
- [ ] Duplicate `* 2.py` files removed

### Out of Scope

- Intel Mac (x86_64) support — focus is Apple Silicon only
- macOS code signing / notarization — colleagues can use `xattr -d com.apple.quarantine`
- Windows build changes — not affected by this milestone
- GPU performance optimization beyond MPS enablement

## Context

- **Codebase:** Python 3.12, PyQt6, Cellpose 4.x, PyTorch, pyvips, OpenSlide
- **Existing macOS structure:** `build-macos.yml`, `docs/build/main_release.spec`, `docs/macos/SETUP_MACOS.md`, `model_downloader.py`
- **CellposeAdapter already has MPS detection** (`torch.backends.mps.is_available()`) — just needs the right PyTorch build
- **CI workflow exists but is broken** — wrong torch build, missing Homebrew deps, wrong spec path

## Constraints

- **Platform:** Apple Silicon ARM64 only (macOS 15.5+, macOS 26+)
- **Distribution:** `.dmg` that opens with double-click; colleagues do `xattr -d` if Gatekeeper blocks
- **PyTorch:** Must use macOS ARM64 wheels (no `+cu124`) — separate from Windows CUDA requirements
- **NuClick weights:** Auto-downloaded on first use via `model_downloader.py`

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Split requirements by platform | macOS needs `torch` without CUDA index; Windows needs `+cu124` | — Pending |
| Skip code signing for now | No Apple Developer account; colleagues use quarantine workaround | — Pending |
| ARM64-only (no universal binary) | Simpler build; Intel Macs are rare in research labs now | — Pending |

---
*Last updated: 2026-05-04 after initialization*

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state
