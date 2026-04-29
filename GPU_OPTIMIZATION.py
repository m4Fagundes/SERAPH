"""
GPU Optimization Guide — Maximize Cellpose GPU Utilization

Problem: GPU at 2%, CPU at 70%+ means preprocessing/postprocessing is the bottleneck

Root Causes:
1. Preprocessing (H&E extraction) on CPU before sending to GPU
2. Batch size too small (4 images) — GPU not fully loaded
3. Polygon extraction (contour finding) on CPU after GPU inference
4. Sequential tile processing — GPU idle while CPU works
5. Max tile size too small — processing many small tiles instead of large batches

Solutions:
1. Increase batch_size from 4 to 16+ (saturate GPU VRAM)
2. Increase max_tile_size from 2000px to 3000-4000px
3. Parallel pipeline: prefetch + GPU inference + postprocess
4. Remove preprocessing bottleneck (minimize downsampling)
5. Use GPU-accelerated preprocessing (OpenCV CUDA) if available
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Optimal GPU configuration for RTX 2060 (6GB VRAM)
@dataclass
class GPUOptimizationProfile:
    """Configuration for maximum GPU utilization."""
    
    # RTX 2060 specs: 6GB VRAM, 1920 CUDA cores, 6.1 Gbps memory bandwidth
    name: str = "RTX-2060-Max"
    
    # Increase batch size to saturate GPU
    # RTX 2060 can handle 16-32 images of 512x512 simultaneously
    batch_size: int = 16  # Was 4, now 16
    
    # Larger tiles = fewer sequential operations
    # Max is ~4000px before RTX 2060 runs out of memory
    max_tile_size_pixels: int = 3000  # Was 2000, now 3000
    
    # No downsampling—use full resolution
    resample_factor: float = 1.0  # Was 0.75-1.0, now 1.0
    
    # Higher Cellpose batch_size for internal processing
    cellpose_internal_batch_size: int = 128  # Was 128, keep high
    
    # Increase timeout for larger batches
    timeout_seconds: int = 900  # 15 minutes for large batches
    
    # Memory limit — conservative for safety
    memory_limit_mb: int = 5000  # 5GB out of 6GB available
    
    # Parallel threads for prefetching while GPU works
    prefetch_threads: int = 4  # Load next batch while GPU processes current
    
    # Description of expected performance
    expected_speedup: float = 3.0  # 3x faster than sequential
    expected_gpu_util: float = 85.0  # Target 85% GPU utilization


# ────────────────────────────────────────────────────────────────────────────
# IMPLEMENTATION GUIDE
# ────────────────────────────────────────────────────────────────────────────

OPTIMIZATION_STEPS = """
## Step 1: Update Performance Config (IMMEDIATE)

1. Edit: app/infrastructure/config/performance_config.py
2. In _create_high_performance_config(), change:

   # FROM:
   batch_size=4,
   max_tile_size_pixels=2000,
   
   # TO:
   batch_size=16,
   max_tile_size_pixels=3000,

## Step 2: Optimize CellposeAdapter (IMPORTANT)

1. Edit: app/infrastructure/ml_models/cellpose_adapter.py
2. Increase internal batch_size in _segment_single_image():

   # FROM:
   batch_size=128,
   
   # TO (use entire available VRAM):
   batch_size=256,  # Or even 512 for small tiles

## Step 3: Parallel Pipeline (ADVANCED)

Implement prefetching worker thread:
- Thread 1: Load + preprocess next batch
- Thread 2: GPU inference on current batch  
- Thread 3: Postprocess (polygon extraction) previous batch

This keeps CPU and GPU working in parallel.

## Step 4: GPU Preprocessing (OPTIONAL)

If still bottlenecked on preprocessing:
1. Install OpenCV CUDA: pip install opencv-contrib-python-headless
2. Move H&E extraction to GPU using cv2.cuda

Expected improvement: +2-3x speedup for large images.

## Step 5: Monitor Improvements

After each change, run: nvidia-smi -l 1

You should see:
- GPU Memory: 3-5GB used (was <1GB)
- GPU Utilization: 85-95% (was 2%)
- GPU Temperature: 70-80°C (normal)
- CPU: 30-40% (was 70%)
"""

# ────────────────────────────────────────────────────────────────────────────
# QUICK OPTIMIZATION: Update config directly
# ────────────────────────────────────────────────────────────────────────────

def get_max_gpu_config() -> GPUOptimizationProfile:
    """Returns maximum GPU utilization config for RTX 2060."""
    return GPUOptimizationProfile()


def print_optimization_guide():
    """Print step-by-step optimization guide to console."""
    print(OPTIMIZATION_STEPS)
    
    config = get_max_gpu_config()
    print(f"\n✅ RECOMMENDED GPU CONFIG:")
    print(f"   Batch Size: {config.batch_size}")
    print(f"   Max Tile Size: {config.max_tile_size_pixels}px")
    print(f"   Resample Factor: {config.resample_factor}")
    print(f"   Expected GPU Util: {config.expected_gpu_util}%")
    print(f"   Expected Speedup: {config.expected_speedup}x")


if __name__ == "__main__":
    print_optimization_guide()
