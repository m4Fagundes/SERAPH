"""
GPUSelector — Automatically selects the PyTorch-compatible GPU.

Problem: RTX 5060 is not yet supported in PyTorch.
Solution: If multiple GPUs are present, use the first compatible one.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_best_cuda_device() -> Optional[int]:
    """
    Returns the index of the best CUDA device compatible with PyTorch.
    
    Rules:
    1. If CUDA is not available: returns None
    2. If there is a compatible GPU: returns its index
    3. If no GPU is compatible: returns None (will force CPU fallback)
    
    Returns:
        GPU index (0, 1, ...) or None if none compatible
    """
    try:
        import torch
    except ImportError:
        logger.warning("PyTorch not available - GPU selection disabled")
        return None
    
    if not torch.cuda.is_available():
        logger.debug("CUDA not available")
        return None
    
    # Compute capabilities supported by current PyTorch
    # sm_50 (Maxwell), sm_60 (Pascal), sm_70 (Volta), sm_75 (Turing), sm_80 (Ampere), sm_86 (Ampere), sm_90 (Hopper)
    supported_capabilities = {(5, 0), (6, 0), (6, 1), (7, 0), (7, 5), (8, 0), (8, 6), (9, 0)}
    
    num_devices = torch.cuda.device_count()
    compatible_devices = []
    
    for device_id in range(num_devices):
        try:
            device_name = torch.cuda.get_device_name(device_id)
            device_cap = torch.cuda.get_device_capability(device_id)
            
            if device_cap in supported_capabilities:
                logger.info(
                    f"✅ GPU {device_id}: {device_name} (sm_{device_cap[0]}{device_cap[1]}) - SUPPORTED"
                )
                compatible_devices.append(device_id)
            else:
                logger.warning(
                    f"❌ GPU {device_id}: {device_name} (sm_{device_cap[0]}{device_cap[1]}) - NOT SUPPORTED"
                )
        except Exception as e:
            logger.warning(f"Failed to query GPU {device_id}: {e}")
    
    if compatible_devices:
        best_device = compatible_devices[0]
        logger.info(f"Selected GPU device {best_device} for CUDA operations")
        return best_device
    else:
        logger.warning("No compatible CUDA devices found - will use CPU")
        return None


def set_cuda_device(device_id: Optional[int]) -> None:
    """
    Sets which CUDA device will be used.
    
    Args:
        device_id: Device index or None for CPU
    """
    try:
        import torch
        
        if device_id is None:
            logger.info("CUDA device set to None (will use CPU)")
            return
        
        if not torch.cuda.is_available():
            logger.warning("CUDA not available - ignoring device selection")
            return
        
        if device_id >= torch.cuda.device_count():
            logger.warning(f"Device {device_id} not available (only {torch.cuda.device_count()} devices)")
            return
        
        torch.cuda.set_device(device_id)
        device_name = torch.cuda.get_device_name(device_id)
        logger.info(f"CUDA device set to {device_id}: {device_name}")
        
    except Exception as e:
        logger.warning(f"Failed to set CUDA device: {e}")


def initialize_gpu_visibility() -> None:
    """
    Runs a lightweight subprocess to find the best compatible GPU,
    and sets CUDA_VISIBLE_DEVICES in the parent process BEFORE torch is imported.
    This prevents incompatible GPUs (like RTX 5060) from corrupting the PyTorch/cuDNN context.
    """
    # If already inside a probe or visibility is already set, do nothing
    if "SERAPH_GPU_PROBE" in os.environ or "CUDA_VISIBLE_DEVICES" in os.environ:
        return

    try:
        import subprocess
        import sys
        
        # Run a subprocess with SERAPH_GPU_PROBE set to 1 to find the best device
        env = os.environ.copy()
        env["SERAPH_GPU_PROBE"] = "1"
        
        # Run a python command to query the best device using this module
        cmd = [
            sys.executable, 
            "-c", 
            "from app.infrastructure.config.gpu_selector import get_best_cuda_device; print(get_best_cuda_device())"
        ]
        
        logger.info("Detecting best compatible GPU in background subprocess...")
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            output = result.stdout.strip()
            # Extract last line in case of PyTorch warnings
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            if lines:
                last_line = lines[-1]
                if last_line != "None":
                    best_device = int(last_line)
                    os.environ["CUDA_VISIBLE_DEVICES"] = str(best_device)
                    logger.info(f"Successfully isolated GPU {best_device} via CUDA_VISIBLE_DEVICES.")
                    return
        else:
            logger.warning(f"Subprocess GPU detection returned code {result.returncode}. Stderr: {result.stderr}")
    except Exception as e:
        logger.warning(f"Failed to run GPU subprocess detection: {e}")


# Run visibility initialization on import (this runs before any PyTorch imports can happen)
try:
    initialize_gpu_visibility()
except Exception as e:
    logger.warning(f"Failed to initialize GPU visibility on import: {e}")


# Auto-select best GPU on import
try:
    if "SERAPH_GPU_PROBE" not in os.environ:
        if "CUDA_VISIBLE_DEVICES" not in os.environ:
            best_device = get_best_cuda_device()
            if best_device is not None:
                set_cuda_device(best_device)
                os.environ["CUDA_VISIBLE_DEVICES"] = str(best_device)
        else:
            # If visibility was already isolated, we just set default device to 0 (the only visible one)
            set_cuda_device(0)
except Exception as e:
    logger.warning(f"GPU auto-selection failed: {e}")


