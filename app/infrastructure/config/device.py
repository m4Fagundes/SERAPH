"""
device — single source of truth for the PyTorch backend used by every adapter.

Before this module each ML adapter re-implemented its own CUDA > MPS > CPU
ladder. The copies drifted: InstanSeg never reached MPS, the MPS branches
ignored an explicit ``use_gpu=False``, OOM detection only matched CUDA error
strings, and no caller ever freed Metal memory.

Backends, in order of preference:
    CUDA (Windows/Linux, NVIDIA)  >  MPS (Apple Silicon)  >  CPU

Apple Silicon notes
-------------------
* Several operators used by Cellpose/SAM/CellViT have no Metal kernel. The app
  relies on ``PYTORCH_ENABLE_MPS_FALLBACK=1`` (set in ``hooks/rthook_torch_env.py``
  for frozen builds, and defensively here for development runs) so those fall
  back to the CPU instead of raising NotImplementedError.
* MPS uses unified memory, so VRAM-keyed batch heuristics do not apply; callers
  should treat it as a mid-range device rather than a discrete GPU.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Must be set before torch is first imported. Harmless if torch is already in.
if sys.platform == "darwin":
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

# Env escape hatch: SERAPH_DEVICE=cpu|mps|cuda|cuda:1 forces a backend.
DEVICE_OVERRIDE_ENV = "SERAPH_DEVICE"


def _torch() -> Optional[Any]:
    try:
        import torch

        return torch
    except Exception as exc:  # pragma: no cover - torch is a hard dependency
        logger.warning("PyTorch unavailable: %s", exc)
        return None


def cuda_available() -> bool:
    torch = _torch()
    if torch is None:
        return False
    try:
        return bool(torch.cuda.is_available()) and torch.cuda.device_count() > 0
    except Exception:
        return False


def mps_available() -> bool:
    """True when this is an Apple Silicon Mac with a working Metal backend."""
    torch = _torch()
    if torch is None:
        return False
    try:
        backends = getattr(torch.backends, "mps", None)
        if backends is None:
            return False
        return bool(backends.is_available() and backends.is_built())
    except Exception:
        return False


def gpu_available() -> bool:
    """True when any GPU backend (CUDA or MPS) can be used."""
    return cuda_available() or mps_available()


def select_device(use_gpu: Optional[bool] = None, device_id: Optional[int] = None) -> Any:
    """
    Resolve the torch.device this app should run on.

    Args:
        use_gpu: True forces a GPU backend when one exists, False pins the CPU,
                 None (default) means "use a GPU if one is available".
        device_id: CUDA index to prefer. Ignored on MPS/CPU.

    Returns:
        torch.device — always a valid device; falls back to CPU rather than raising.
    """
    torch = _torch()
    if torch is None:
        raise RuntimeError("PyTorch is required but could not be imported")

    override = os.environ.get(DEVICE_OVERRIDE_ENV, "").strip()
    if override:
        try:
            logger.info("Device override via %s=%s", DEVICE_OVERRIDE_ENV, override)
            return torch.device(override)
        except Exception as exc:
            logger.warning("Invalid %s=%r (%s); falling back to auto-detection.",
                           DEVICE_OVERRIDE_ENV, override, exc)

    # An explicit "no GPU" must be honoured on every backend — including MPS,
    # which the old per-adapter ladders returned unconditionally.
    if use_gpu is False:
        return torch.device("cpu")

    if cuda_available():
        index = device_id
        if index is None:
            try:
                from .gpu_selector import get_best_cuda_device

                index = get_best_cuda_device()
            except Exception as exc:
                logger.debug("CUDA device selection failed: %s", exc)
        if index is not None:
            return torch.device(f"cuda:{index}")
        return torch.device("cuda:0")

    if mps_available():
        return torch.device("mps")

    return torch.device("cpu")


def select_device_str(use_gpu: Optional[bool] = None, device_id: Optional[int] = None) -> str:
    """select_device() for the libraries that want a string ("cuda:0"/"mps"/"cpu")."""
    return str(select_device(use_gpu=use_gpu, device_id=device_id))


def describe_device(device: Any) -> str:
    """Human-readable device label for logs and the UI."""
    torch = _torch()
    if torch is None:
        return "unknown"
    try:
        device = torch.device(device)
        if device.type == "cuda":
            index = device.index if device.index is not None else torch.cuda.current_device()
            return f"CUDA · {torch.cuda.get_device_name(index)}"
        if device.type == "mps":
            return "MPS · Apple Silicon GPU"
        return "CPU"
    except Exception:
        return str(device)


def supports_autocast(device: Any) -> bool:
    """
    Whether mixed precision should be used on this device.

    CUDA: yes. CPU: no (fp32 is faster than emulated fp16).
    MPS: no — autocast on Metal is still unreliable for the ViT backbones used
    here (silent NaNs in SAM/CellViT attention), so we keep fp32.
    """
    torch = _torch()
    if torch is None:
        return False
    try:
        return torch.device(device).type == "cuda"
    except Exception:
        return False


def empty_cache(device: Any = None) -> None:
    """
    Release cached GPU memory on whichever backend is active.

    Handles MPS, which every previous cache-clearing call site ignored.
    """
    torch = _torch()
    if torch is None:
        return

    device_type = None
    if device is not None:
        try:
            device_type = torch.device(device).type
        except Exception:
            device_type = None

    try:
        if device_type in (None, "cuda") and cuda_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception as exc:
        logger.debug("CUDA cache cleanup failed: %s", exc)

    try:
        if device_type in (None, "mps") and mps_available():
            mps_module = getattr(torch, "mps", None)
            if mps_module is not None and hasattr(mps_module, "empty_cache"):
                mps_module.empty_cache()
    except Exception as exc:
        logger.debug("MPS cache cleanup failed: %s", exc)


def is_oom_error(exc: BaseException) -> bool:
    """
    True for an out-of-memory failure on any backend.

    CUDA raises "CUDA out of memory"; MPS raises "MPS backend out of memory".
    Matching only the CUDA wording meant Apple Silicon never hit the CPU-retry path.
    """
    message = str(exc).lower()
    return (
        "out of memory" in message
        or "outofmemoryerror" in message
        or "mps backend out of memory" in message
    )


def is_gpu_failure(exc: BaseException) -> bool:
    """
    True for any GPU failure that a CPU retry could plausibly recover from.

    Covers OOM plus the missing-kernel errors MPS raises for operators that
    Metal does not implement (Cellpose 4.x sparse ops on Apple Silicon).
    """
    message = str(exc).lower()
    return (
        is_oom_error(exc)
        or "cudnn error" in message
        or "cuda error" in message
        or "not implemented" in message
        or "could not run" in message
        or "mps" in message and "error" in message
    )
