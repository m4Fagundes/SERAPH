# macOS Build & Distribution Guide

How GridAnalyzer is packaged for macOS, what the CI guarantees, and what you
need to configure to make the app open with a double-click.

## Target platform

**Apple Silicon (arm64), macOS 13 or later.** Verified on **macOS 15** and **macOS 26**
on every release — the build runs on macOS 15 and the resulting bundle is then
launched on both versions before anything is published.

**Intel Macs are not supported.** PyTorch has published no macOS `x86_64` wheels
since version 2.3, and Cellpose-SAM (`cpsam`) needs a modern torch. Supporting
Intel would mean pinning the whole stack back to torch 2.2, which the models no
longer work with. There is no `universal2` build for the same reason.

## Compute backend

The app has no CUDA on macOS. It runs on **MPS (Metal)** when available and falls
back to the CPU otherwise. All of that is decided in one place —
`app/infrastructure/config/device.py`:

| Function | Purpose |
|---|---|
| `select_device(use_gpu, device_id)` | The CUDA > MPS > CPU ladder. Every adapter calls this. |
| `empty_cache()` | Frees CUDA **and** Metal memory. |
| `is_gpu_failure(exc)` | Matches OOM/unsupported-op errors on both backends, which drives the CPU retry. |
| `supports_autocast(device)` | Mixed precision on CUDA only; MPS stays fp32. |

Two things to know about Metal:

* `PYTORCH_ENABLE_MPS_FALLBACK=1` is set before torch is imported (in `main.py`
  and in `hooks/rthook_torch_env.py` for the frozen build). Several operators
  used by Cellpose/SAM/CellViT have no Metal kernel; without this they raise
  instead of running on the CPU.
* Batch sizes and tile sizes are lower on MPS than on a discrete GPU
  (`performance_config.py`). Apple Silicon shares one memory pool with the OS,
  so the CUDA-tuned numbers would push the machine into swap.

**Forcing a backend:** set `SERAPH_DEVICE=cpu` (or `mps`, `cuda`) to override
auto-detection — useful when debugging a Metal-specific problem.

## The self-test

`SERAPH_SELFTEST=1` makes the app import every native dependency, run a real
matmul on the selected device, print a report, and exit — without opening a window.

```bash
SERAPH_SELFTEST=1 /Applications/GridAnalyzer.app/Contents/MacOS/GridAnalyzer
```

CI runs this against the packaged `.app` on both macOS 15 and macOS 26. That is
what turns "a dylib is missing" into a failed build instead of a crash on your Mac.

## What the build guarantees

The `Verify bundle is self-contained` step fails the build if any bundled `.dylib`
or `.so` links against `/opt/homebrew` or `/usr/local`. This matters: Homebrew is
**not** used to build the app. `libvips` and `libopenslide` come from the
`pyvips-binary` and `openslide-bin` wheels and are copied into the bundle. If we
let Homebrew provide them, PyInstaller would link to paths that exist on the CI
runner and on no user's machine.

The `.app` is uploaded with `ditto`, not a plain zip, so symlinks, permissions and
the code signature survive the round-trip.

## Signing and notarization

Without an Apple Developer account the DMG still builds, but macOS quarantines
anything downloaded from the internet, so the first launch is blocked. Users have
to run this once:

```bash
xattr -dr com.apple.quarantine /Applications/GridAnalyzer.app
```

To remove that step, add these repository secrets (Settings → Secrets and
variables → Actions). The workflow detects them and switches to Developer ID
signing + notarization automatically; no workflow edit is needed.

| Secret | What it is |
|---|---|
| `MACOS_CERTIFICATE` | Your "Developer ID Application" certificate exported as `.p12`, then base64-encoded: `base64 -i cert.p12 \| pbcopy` |
| `MACOS_CERTIFICATE_PWD` | The password you set when exporting the `.p12` |
| `MACOS_SIGNING_IDENTITY` | The identity string, e.g. `Developer ID Application: Your Name (TEAM123456)` |
| `MACOS_NOTARY_APPLE_ID` | The Apple ID email of the developer account |
| `MACOS_NOTARY_TEAM_ID` | Your 10-character Team ID |
| `MACOS_NOTARY_PASSWORD` | An **app-specific password** (appleid.apple.com → Sign-In and Security → App-Specific Passwords) — not your Apple ID password |

An Apple Developer membership costs ~$99/year. With all six set, the release DMG
is signed, notarized by Apple, and stapled, so it opens with a double-click and
the release notes say so.

## Releasing

The build is driven by git tags:

```bash
git tag v1.4.0
git push origin v1.4.0
```

That triggers both platform workflows. Each one:

1. Clones the pinned upstream repos (CellViT, patho-sam, micro-sam, torch-em, elf)
   at fixed commits, so a release is reproducible.
2. Builds with PyInstaller, stamping the tag into the bundle version.
3. Runs the self-test against the packaged app.
4. Publishes the DMG / installer to the GitHub Release for that tag.

Pushing to `main` builds and verifies the macOS app too, but publishes nothing.

## Building locally

```bash
pip install -r requirements-macos.txt
pip install 'pyinstaller>=6.10'
python -c "from cellpose import models; models.CellposeModel(model_type='cpsam', gpu=False)"

SERAPH_VERSION=1.4.0 pyinstaller --clean --noconfirm docs/build/main_release.spec
SERAPH_SELFTEST=1 ./dist/GridAnalyzer.app/Contents/MacOS/GridAnalyzer
```

## Troubleshooting

**"GridAnalyzer is damaged and can't be opened"** — the quarantine flag on an
unsigned build. Run the `xattr -dr` command above. It is not actually damaged.

**The app opens on the CPU when you expect the GPU** — run the self-test; it
prints the device it selected. Check that `torch.backends.mps.is_available()` is
true and that no `SERAPH_DEVICE` override is set.

**A model crashes with "not implemented for MPS"** — confirm
`PYTORCH_ENABLE_MPS_FALLBACK=1` is in the environment. The adapters also catch
these and retry on the CPU (`device.is_gpu_failure`), so it should degrade rather
than crash; if it crashes, that path has a gap worth reporting.

**The build fails on "links against a Homebrew/local path"** — a dependency
started pulling a native library from Homebrew instead of a wheel. Do not add
`brew install` to make it pass; find the wheel that ships the library, or the
bundle will break on machines without Homebrew.
