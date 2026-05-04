---
phase: 3
plan: 1
subsystem: ci-cd
tags: [github-actions, macos, arm64, pyinstaller, homebrew]
dependency_graph:
  requires: []
  provides: [working-macos-ci-workflow]
  affects: [.github/workflows/build-macos.yml]
tech_stack:
  added: []
  patterns: [github-actions-single-runner, platform-split-requirements]
key_files:
  created: []
  modified:
    - .github/workflows/build-macos.yml
decisions:
  - ARM64-only CI (macos-14); no Intel matrix to keep build simple
  - brew install libvips openslide before pip so dylibs are available at bundle time
  - requirements-macos.txt used exclusively (no CUDA wheels on CI)
  - Code signing deferred to v2 (no Apple Developer account)
metrics:
  duration: "5 minutes"
  completed: "2026-05-04"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 1
---

# Phase 3 Plan 1: Rewrite build-macos.yml — ARM64-only, fix spec path, add Homebrew deps

ARM64-only GitHub Actions workflow replacing a broken Intel+ARM64 matrix; installs libvips/openslide via Homebrew, uses requirements-macos.txt, and runs PyInstaller with the correct spec path at docs/build/main_release.spec.

## What Was Done

Rewrote `.github/workflows/build-macos.yml` in full to fix all four fatal breakage points that prevented macOS CI from succeeding.

## Changes Made to build-macos.yml (Before → After)

| Area | Before | After |
|------|--------|-------|
| Runner strategy | Matrix with macos-13 (Intel) + macos-14 (ARM64) | Single `runs-on: macos-14` (ARM64 only) |
| Python setup action | `actions/setup-python@v4` | `actions/setup-python@v5` |
| Pip cache action | `actions/cache@v3` | `actions/cache@v4` |
| Pip cache key | `hashFiles('**/requirements.txt')` | `hashFiles('requirements-macos.txt')` |
| Homebrew deps | None — libvips/openslide not installed | `brew install libvips openslide` step added before pip |
| Requirements file | `pip install -r requirements.txt` (CUDA wheels — fails on macOS) | `pip install -r requirements-macos.txt` |
| PyInstaller command | `pyinstaller --clean --noconfirm main_release.spec` (file not at root) | `pyinstaller --clean --noconfirm docs/build/main_release.spec` |
| Code signing | Step present (APPLE_ID, codesign, notarize) | Removed entirely (deferred to v2) |
| create-dmg flags | `--volicon "app.icns"` (file does not exist) + `--window-size 800 400` | Removed `--volicon`, `--window-size 600 400`, `--app-drop-link 400 190` |
| Artifact names | `GridAnalyzer-${{ matrix.arch }}.app/dmg` | Static `GridAnalyzer-arm64.app/dmg` |
| Path triggers | `requirements.txt`, `main_release.spec` | `requirements-macos.txt`, `docs/build/main_release.spec`, hook files added |
| Release condition | `startsWith(github.ref, 'refs/tags/') && matrix.arch == 'arm64'` | `startsWith(github.ref, 'refs/tags/')` (no matrix) |

## Prerequisite Files Confirmed

- `docs/build/main_release.spec` — confirmed at correct path; SPECPATH resolves to `docs/build/`, REPO_ROOT goes up two levels
- `requirements-macos.txt` — confirmed at repo root (created Phase 1, Plan 02)
- `hooks/rthook_cellpose.py` — confirmed exists
- `hooks/rthook_openslide.py` — confirmed exists

## Acceptance Criteria Results

All checks passed:
- `grep "macos-13"` → empty (PASS)
- `grep "runs-on"` → `runs-on: macos-14` (PASS)
- `grep "brew install libvips openslide"` → 1 line (PASS)
- `grep "requirements-macos.txt"` → 3 lines (path trigger + pip install + cache key) (PASS)
- `grep "requirements.txt"` excluding `-macos` → empty (PASS)
- `grep "docs/build/main_release.spec"` → 2 lines (path trigger + pyinstaller) (PASS)
- `grep "main_release.spec" | grep -v "docs/build"` → empty (PASS)
- `grep "APPLE_ID\|codesign\|notariz"` → empty (PASS)
- `grep "volicon"` → empty (PASS)
- `grep "setup-python@v5"` → 1 line (PASS)
- `grep "cache@v4"` → 1 line (PASS)

## Commit

`cf78caa` — `fix(ci): rewrite build-macos.yml — ARM64-only, fix spec path, add Homebrew deps (CI-01, CI-02, CI-04)`

## Deviations from Plan

None — plan executed exactly as written.

`npx gitnexus detect-changes --scope staged` is not a valid CLI subcommand in the installed version (the CLAUDE.md tool reference is for the MCP server tool `gitnexus_detect_changes`). The staged file is a YAML workflow with no Python symbols, so no symbol blast radius is relevant. This is consistent with the plan's own note: "build-macos.yml has no Python symbols so this is a formality."

## Known Stubs

None — the workflow file is complete and functional as written.

## Threat Flags

None — the workflow file introduces no new network endpoints, auth paths, or trust-boundary schema changes. It uses only existing `secrets.GITHUB_TOKEN` (already present in prior version).

## Self-Check: PASSED

- `.github/workflows/build-macos.yml` exists and contains correct content
- Commit `cf78caa` exists in git log
- No unexpected file deletions in commit
