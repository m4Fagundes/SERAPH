"""Small GPU memory helpers for model adapters."""

from __future__ import annotations

import gc
import logging

logger = logging.getLogger(__name__)


def cuda_memory_snapshot(device_id: int | None = None) -> dict | None:
    """Return current free/total CUDA memory for a device, or None on CPU."""
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        device = torch.cuda.current_device() if device_id is None else int(device_id)
        free, total = torch.cuda.mem_get_info(device)
        return {
            "device_id": device,
            "device_name": torch.cuda.get_device_name(device),
            "free_gb": free / 1e9,
            "total_gb": total / 1e9,
            "allocated_gb": torch.cuda.memory_allocated(device) / 1e9,
            "reserved_gb": torch.cuda.memory_reserved(device) / 1e9,
        }
    except Exception as exc:
        logger.debug("CUDA memory snapshot skipped: %s", exc)
        return None


def cuda_memory_summary(label: str, *, log_level: int = logging.INFO) -> None:
    """Log PyTorch CUDA memory usage if CUDA is available."""
    try:
        import torch

        if not torch.cuda.is_available():
            return
        device = torch.cuda.current_device()
        snapshot = cuda_memory_snapshot(device)
        if snapshot is None:
            return
        logger.log(
            log_level,
            "CUDA memory %s: free=%.2fGB total=%.2fGB allocated=%.2fGB reserved=%.2fGB",
            label,
            snapshot["free_gb"],
            snapshot["total_gb"],
            snapshot["allocated_gb"],
            snapshot["reserved_gb"],
        )
    except Exception as exc:
        logger.debug("CUDA memory summary skipped: %s", exc)


def cleanup_cuda_memory(label: str = "cleanup") -> None:
    """Run Python GC and release PyTorch's unused CUDA cache."""
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception as exc:
        logger.debug("CUDA cleanup skipped: %s", exc)
    cuda_memory_summary(label)
