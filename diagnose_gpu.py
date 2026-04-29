#!/usr/bin/env python3
"""
Script de diagnóstico para GPU - Cellpose Integration.

Testa:
1. PyTorch e CUDA availability
2. Hardware detection
3. Performance configuration
4. Cellpose adapter initialization com GPU
"""

import sys
import logging
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Adicionar diretório ao path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("GPU DIAGNOSIS SCRIPT - Cellpose Integration")
print("=" * 70)

# ========================================================================
# 1. PyTorch & CUDA Detection
# ========================================================================
print("\n1. PYTORCH & CUDA DETECTION")
print("-" * 70)

try:
    import torch
    print(f"✅ PyTorch installed: {torch.__version__}")
    print(f"   CUDA available: {torch.cuda.is_available()}")
    print(f"   CUDA version (PyTorch): {torch.version.cuda}")
    
    if torch.cuda.is_available():
        print(f"   Number of GPUs: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"   GPU {i}: {torch.cuda.get_device_name(i)}")
            print(f"           Compute Capability: {torch.cuda.get_device_capability(i)}")
        print(f"   Current GPU: {torch.cuda.current_device()}")
        
        # Test CUDA functionality
        try:
            test_tensor = torch.randn(2, 3, device='cuda')
            result = test_tensor * 2
            print("   ✅ CUDA functional test PASSED")
        except Exception as e:
            print(f"   ❌ CUDA functional test FAILED: {e}")
    else:
        print("   ⚠️  CUDA not available - this might limit GPU usage")
        
except ImportError:
    print("❌ PyTorch not installed - GPU acceleration not available")
    sys.exit(1)

# ========================================================================
# 2. Hardware Detection
# ========================================================================
print("\n2. HARDWARE DETECTION")
print("-" * 70)

try:
    from app.infrastructure.config.hardware_detector import HardwareDetector
    
    detector = HardwareDetector()
    
    print(f"✅ System: {detector.system}")
    print(f"   CPU Cores: {detector.cpu_cores}")
    print(f"   Memory: {detector.memory_gb:.1f} GB")
    print(f"   GPU Available: {detector.gpu_available}")
    print(f"   GPU Recommended: {detector.gpu_recommended}")
    
    if detector.is_mac:
        print(f"   macOS Version: {detector.mac_version}")
        print(f"   Is Monterey: {detector.is_mac_monterey}")
    
    profile = detector.get_performance_profile()
    print(f"   Performance Profile: {profile}")
    
    if not detector.gpu_available:
        print("\n   ⚠️  GPU NOT DETECTED!")
        print("      This is likely the issue. Check:")
        print("      • CUDA Toolkit is installed")
        print("      • cuDNN is installed")
        print("      • GPU drivers are up to date")
        print("      • Run 'nvidia-smi' in terminal to check NVIDIA GPU status")
    else:
        print("\n   ✅ GPU DETECTED AND RECOMMENDED")
        
except Exception as e:
    print(f"❌ Hardware detection failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ========================================================================
# 3. Performance Configuration
# ========================================================================
print("\n3. PERFORMANCE CONFIGURATION")
print("-" * 70)

try:
    from app.infrastructure.config.performance_config import get_performance_config
    
    config = get_performance_config()
    
    print(f"✅ Performance Config loaded")
    print(f"   Profile: {config.performance_profile}")
    print(f"   Force CPU Only: {config.force_cpu_only}")
    print(f"   Disable GPU: {config.disable_gpu}")
    print(f"\n   Cellpose Configuration:")
    print(f"      Use GPU: {config.cellpose.use_gpu}")
    print(f"      GPU Fallback: {config.cellpose.gpu_fallback_enabled}")
    print(f"      Batch Size: {config.cellpose.batch_size}")
    print(f"      Timeout: {config.cellpose.timeout_seconds}s")
    print(f"      Max Tile Size: {config.cellpose.max_tile_size_pixels}px")
    print(f"      Memory Limit: {config.cellpose.memory_limit_mb}MB")
    
    if not config.cellpose.use_gpu:
        print("\n   ⚠️  GPU NOT ENABLED IN CONFIG")
        print("      This will cause Cellpose to run on CPU only")
        if detector.gpu_available and detector.gpu_recommended:
            print("      BUT GPU is detected and recommended!")
            print("      This is a configuration issue - check hardware_detector")
    else:
        print("\n   ✅ GPU ENABLED IN CONFIG")
        
except Exception as e:
    print(f"❌ Performance config failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ========================================================================
# 4. Cellpose Adapter Initialization
# ========================================================================
print("\n4. CELLPOSE ADAPTER INITIALIZATION")
print("-" * 70)

try:
    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
    
    print("Creating CellposeAdapter with auto GPU detection (gpu=None)...")
    adapter = CellposeAdapter(model_type="nuclei", gpu=None)
    
    print(f"✅ CellposeAdapter created")
    print(f"   Model Type: {adapter._model_type}")
    print(f"   GPU Enabled: {adapter._gpu}")
    print(f"   Batch Size: {adapter._batch_size}")
    print(f"   Timeout: {adapter._timeout_seconds}s")
    print(f"   Max Tile Size: {adapter._max_tile_size}px")
    print(f"   Resample Factor: {adapter._resample_factor}")
    
    if adapter._gpu:
        print("\n   ✅ CELLPOSE WILL USE GPU")
    else:
        print("\n   ⚠️  CELLPOSE WILL USE CPU")
        if detector.gpu_available:
            print("      GPU is detected but not enabled in adapter")
            print("      Check CellposeAdapter initialization logic")
            
except Exception as e:
    print(f"❌ CellposeAdapter initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ========================================================================
# 5. Recommendations
# ========================================================================
print("\n5. RECOMMENDATIONS")
print("-" * 70)

if not detector.gpu_available:
    print("🔴 PRIMARY ISSUE: GPU not detected")
    print("\nTo enable GPU acceleration:")
    print("1. Install NVIDIA CUDA Toolkit:")
    print("   https://developer.nvidia.com/cuda-downloads")
    print("2. Install cuDNN:")
    print("   https://developer.nvidia.com/cudnn")
    print("3. Update NVIDIA GPU drivers:")
    print("   https://www.nvidia.com/Download/driverDetails.aspx")
    print("4. Verify installation with: nvidia-smi")
    print("5. Reinstall PyTorch with CUDA support:")
    print("   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")

elif not config.cellpose.use_gpu:
    print("🟡 SECONDARY ISSUE: GPU detected but not enabled in config")
    print("\nThe performance_config should enable GPU.")
    print("Check hardware_detector._recommend_gpu_usage() logic")
    
elif adapter._gpu:
    print("🟢 GPU READY!")
    print("\nCellpose is configured to use GPU acceleration.")
    print("You should see much faster segmentation performance.")
    print("\nExpected improvements:")
    print("• 5-10x faster nucleus segmentation")
    print("• Lower CPU usage (<50%)")
    print("• GPU usage 60-90%")

print("\n" + "=" * 70)
