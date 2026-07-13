"""
Runtime hook: configure the PyTorch environment before torch is imported.

Must run before the first `import torch`, because PyTorch reads these
variables once, at import time.

1. PYTORCH_ENABLE_MPS_FALLBACK — on Apple Silicon several operators used by
   Cellpose / SAM / CellViT have no Metal kernel. Without this variable torch
   raises NotImplementedError instead of running those operators on the CPU,
   which makes MPS unusable for this app.
2. CUDA_VISIBLE_DEVICES is never probed on macOS: there is no CUDA there, and
   the probe would spawn a subprocess of a frozen binary (see gpu_selector).
"""
import os
import sys

if sys.platform == "darwin":
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
