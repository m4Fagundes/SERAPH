"""
HardwareDetector — Detects hardware capabilities and compatibility.

Architecture: Clean Architecture (Infrastructure Layer)
- Detects CPU cores, memory, GPU/MPS availability
- Checks compatibility with macOS Monterey 12.7.6
- Provides recommendations for performance configuration
- Auto-selects the best GPU compatible with PyTorch

Design Decision (python-patterns §8 — Error Handling):
    All detections have safe fallbacks. If a detection fails,
    it returns appropriate conservative values for older hardware.
"""

import platform
import sys
import logging
import subprocess
import os
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Auto-select best compatible GPU on import (handles RTX 5060 not supported yet)
try:
    from .gpu_selector import get_best_cuda_device, set_cuda_device
    _best_device = get_best_cuda_device()
    if _best_device is not None:
        set_cuda_device(_best_device)
except Exception as e:
    logger.debug(f"GPU auto-selection unavailable: {e}")


class HardwareDetector:
    """
    Detects hardware capabilities and provides recommendations
    for performance configuration.

    Focused on compatibility with macOS Monterey 12.7.6 and limited hardware.
    """

    def __init__(self):
        self.system = platform.system()
        self.is_mac = self.system == "Darwin"
        self.is_mac_monterey = False
        self.mac_version = None

        if self.is_mac:
            self._detect_mac_version()

        self.cpu_cores = self._detect_cpu_cores()
        self.memory_gb = self._detect_memory()
        self.gpu_available = self._detect_gpu_availability()
        self.gpu_recommended = self._recommend_gpu_usage()

        logger.info(
            "Hardware detection: %s, %d cores, %.1f GB RAM, GPU: %s (recommended: %s)",
            self.system, self.cpu_cores, self.memory_gb,
            self.gpu_available, self.gpu_recommended
        )

    def _detect_mac_version(self) -> None:
        """Detects macOS version and if it is Monterey (12.x)."""
        try:
            mac_ver = platform.mac_ver()[0]  # e.g., "12.7.6"
            self.mac_version = mac_ver

            # Parse major version
            try:
                major_version = int(mac_ver.split('.')[0])
                # Monterey is version 12
                self.is_mac_monterey = major_version == 12
            except (ValueError, IndexError):
                self.is_mac_monterey = False

            logger.debug("macOS version detected: %s (Monterey: %s)",
                        mac_ver, self.is_mac_monterey)
        except Exception as e:
            logger.warning("Failed to detect macOS version: %s", e)
            self.is_mac_monterey = False

    def _detect_cpu_cores(self) -> int:
        """Detects the number of available CPU cores."""
        try:
            import multiprocessing
            cores = multiprocessing.cpu_count()

            # For very old hardware, limit threads
            if cores <= 2:
                logger.info("Low core count detected: %d cores", cores)
                return max(1, cores)
            elif cores <= 4:
                # Modest CPUs - use 75% of cores to avoid overloading
                return max(2, cores - 1)
            else:
                # Modern CPUs - use all cores except 2 for system
                return max(4, cores - 2)

        except Exception as e:
            logger.warning("Failed to detect CPU cores: %s. Using conservative default (2).", e)
            return 2  # Conservative default

    def _detect_memory(self) -> float:
        """Detects available RAM memory in GB."""
        try:
            if self.is_mac:
                # macOS: use sysctl
                result = subprocess.run(
                    ['sysctl', 'hw.memsize'],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode == 0:
                    # hw.memsize is in bytes
                    mem_bytes = int(result.stdout.split(':')[1].strip())
                    mem_gb = mem_bytes / (1024**3)
                    return round(mem_gb, 1)
            else:
                # Linux/Windows fallback
                import psutil
                mem_gb = psutil.virtual_memory().total / (1024**3)
                return round(mem_gb, 1)
        except Exception as e:
            logger.warning("Failed to detect memory: %s. Using conservative default (4 GB).", e)
            return 4.0  # Conservative default

    def _detect_gpu_availability(self) -> bool:
        """
        Detects if GPU/MPS/CUDA is available and functional.

        Detects:
        - macOS: MPS (Metal Performance Shaders)
        - Windows/Linux: CUDA (NVIDIA GPUs)
        """
        try:
            import torch
        except ImportError:
            logger.debug("PyTorch not installed - GPU detection unavailable")
            return False

        if self.is_mac:
            # macOS: Detect MPS
            # macOS Monterey 12.x has known issues with MPS
            if self.is_mac_monterey:
                logger.info("macOS Monterey detected - MPS may be unstable")

                # Test PyTorch MPS if available
                if hasattr(torch.backends, 'mps'):
                    mps_available = torch.backends.mps.is_available()
                    mps_built = torch.backends.mps.is_built()

                    logger.debug("PyTorch MPS: available=%s, built=%s",
                                mps_available, mps_built)

                    # On Monterey, even if available, it can be unstable
                    if mps_available and mps_built:
                        # Test simple operation to verify stability
                        try:
                            # Light MPS test
                            device = torch.device("mps")
                            test_tensor = torch.randn(2, 3, device=device)
                            _ = test_tensor * 2
                            logger.info("MPS test passed on macOS Monterey")
                            return True
                        except Exception as e:
                            logger.warning("MPS test failed on macOS Monterey: %s", e)
                            return False

                    return False
                else:
                    logger.debug("PyTorch MPS not available in this build")
                    return False
            else:
                # Newer macOS - trust PyTorch detection
                if hasattr(torch.backends, 'mps'):
                    is_available = torch.backends.mps.is_available() and torch.backends.mps.is_built()
                    if is_available:
                        logger.info("PyTorch MPS available on macOS")
                    return is_available
                return False
        else:
            # Windows/Linux: Detect CUDA
            logger.debug("Detecting CUDA availability on %s", self.system)
            
            try:
                # Check if CUDA is available in PyTorch
                cuda_available = torch.cuda.is_available()
                
                if not cuda_available:
                    logger.debug("CUDA not detected by PyTorch")
                    return False
                
                # Check number of GPUs
                num_gpus = torch.cuda.device_count()
                if num_gpus == 0:
                    logger.debug("PyTorch reports CUDA available but no GPUs found")
                    return False
                
                logger.info("CUDA available with %d GPU(s)", num_gpus)
                
                # Search for compatible GPU (even if not the first one)
                supported_capabilities = {(5, 0), (6, 0), (6, 1), (7, 0), (7, 5), (8, 0), (8, 6), (9, 0)}
                compatible_gpus = []
                
                for device_id in range(num_gpus):
                    try:
                        device_cap = torch.cuda.get_device_capability(device_id)
                        device_name = torch.cuda.get_device_name(device_id)
                        
                        if device_cap in supported_capabilities:
                            compatible_gpus.append((device_id, device_name, device_cap))
                            logger.info(f"Compatible GPU found: {device_id} - {device_name} (sm_{device_cap[0]}{device_cap[1]})")
                        else:
                            logger.warning(f"Incompatible GPU: {device_id} - {device_name} (sm_{device_cap[0]}{device_cap[1]})")
                    except Exception as e:
                        logger.debug(f"Failed to check GPU {device_id}: {e}")
                
                if compatible_gpus:
                    # There is at least one compatible GPU
                    logger.info(f"Found {len(compatible_gpus)} compatible GPU(s)")
                    # Test simple operation on compatible GPU to verify functionality
                    try:
                        device = torch.device(f"cuda:{compatible_gpus[0][0]}")
                        test_tensor = torch.randn(2, 3, device=device)
                        _ = test_tensor * 2
                        logger.info("CUDA functional test passed on compatible GPU")
                        return True
                    except Exception as e:
                        logger.warning("CUDA functional test failed: %s", e)
                        return False
                else:
                    # No compatible GPU found
                    logger.warning(f"CUDA available but no compatible GPUs found (found {num_gpus} total)")
                    return False
                    
            except Exception as e:
                logger.warning("CUDA detection error: %s", e)
                return False

    def _recommend_gpu_usage(self) -> bool:
        """
        Recommends whether to use GPU based on hardware and compatibility.

        Rules:
        1. GPU not available: do not recommend (obvious)
        2. macOS Monterey: do not recommend GPU (unstable with MPS)
        3. Windows/Linux with CUDA: recommend (less restrictive than macOS)
        4. macOS with MPS: recommend if it has 6+ GB RAM
        5. Fallback: do not recommend
        """
        if not self.gpu_available:
            return False

        if self.is_mac_monterey:
            # Monterey has known issues with MPS
            logger.info("Not recommending GPU for macOS Monterey due to stability issues")
            return False

        if self.is_mac:
            # macOS with MPS: be conservative with memory
            if self.memory_gb < 6.0:
                logger.info("Not recommending MPS for systems with < 6GB RAM")
                return False
            logger.info("MPS available on macOS with sufficient memory")
            return True
        else:
            # Windows/Linux with CUDA: less restrictive
            # CUDA can work with up to ~4GB, but 6GB+ is more comfortable
            if self.memory_gb < 4.0:
                logger.info("Not recommending CUDA for systems with < 4GB RAM")
                return False
            logger.info("CUDA recommended for Windows/Linux")
            return True

    def get_performance_profile(self) -> str:
        """
        Returns recommended performance profile.

        Returns:
            "low" - Very limited hardware (<= 2 cores, <= 4GB RAM)
            "medium" - Modest hardware (2-4 cores, 4-8GB RAM)
            "high" - Reasonable hardware (4+ cores, 8+ GB RAM)
        """
        if self.cpu_cores <= 2 or self.memory_gb <= 4.0:
            return "low"
        elif self.cpu_cores <= 4 or self.memory_gb <= 8.0:
            return "medium"
        else:
            return "high"

    def get_recommended_threads(self) -> int:
        """Returns recommended number of threads for processing."""
        profile = self.get_performance_profile()

        if profile == "low":
            return 1
        elif profile == "medium":
            return min(2, self.cpu_cores)
        else:  # high
            return min(4, max(2, self.cpu_cores - 2))

    def get_recommended_tile_size(self) -> int:
        """
        Returns recommended maximum tile size in pixels.

        Tiles larger use more memory. Adjust based on available RAM.
        """
        if self.memory_gb <= 4.0:
            return 1000  # 1000x1000 pixels
        elif self.memory_gb <= 8.0:
            return 1500  # 1500x1500 pixels
        elif self.memory_gb <= 16.0:
            return 2000  # 2000x2000 pixels
        else:
            return 2500  # 2500x2500 pixels

    def get_report(self) -> Dict[str, Any]:
        """Returns full hardware detection report."""
        return {
            "system": self.system,
            "is_mac": self.is_mac,
            "is_mac_monterey": self.is_mac_monterey,
            "mac_version": self.mac_version,
            "cpu_cores": self.cpu_cores,
            "memory_gb": self.memory_gb,
            "gpu_available": self.gpu_available,
            "gpu_recommended": self.gpu_recommended,
            "performance_profile": self.get_performance_profile(),
            "recommended_threads": self.get_recommended_threads(),
            "recommended_tile_size": self.get_recommended_tile_size(),
        }

    @classmethod
    def create_safe_detector(cls) -> "HardwareDetector":
        """
        Creates detector with safe fallbacks for when detection fails.

        Useful for initialization where exceptions are not acceptable.
        """
        try:
            return cls()
        except Exception as e:
            logger.error("Failed to create hardware detector: %s. Using safe defaults.", e)
            # Create instance with safe default values
            detector = cls.__new__(cls)
            detector.system = platform.system() if hasattr(platform, 'system') else "Unknown"
            detector.is_mac = detector.system == "Darwin"
            detector.is_mac_monterey = False
            detector.mac_version = None
            detector.cpu_cores = 2
            detector.memory_gb = 4.0
            detector.gpu_available = False
            detector.gpu_recommended = False
            return detector


# Singleton for use throughout the application
_hardware_detector_instance: Optional[HardwareDetector] = None

def get_hardware_detector() -> HardwareDetector:
    """Returns singleton instance of HardwareDetector."""
    global _hardware_detector_instance
    if _hardware_detector_instance is None:
        _hardware_detector_instance = HardwareDetector.create_safe_detector()
    return _hardware_detector_instance