#!/usr/bin/env python3
"""
Diagnostic tool for hardware detection and Cellpose compatibility testing.

Usage:
    python -m app.tools.diagnose_hardware

This tool helps diagnose compatibility issues with macOS Monterey 12.7.6
and hardware limitations for the grid-image-analyzer application.
"""

import sys
import os
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_hardware_detection():
    """Test hardware detection module."""
    print("\n" + "="*60)
    print("HARDWARE DETECTION TEST")
    print("="*60)

    try:
        from app.infrastructure.config.hardware_detector import get_hardware_detector
        detector = get_hardware_detector()
        report = detector.get_report()

        print(f"System: {report['system']}")
        print(f"macOS: {report['is_mac']}")
        print(f"macOS Monterey (12.x): {report['is_mac_monterey']}")
        print(f"macOS Version: {report['mac_version']}")
        print(f"CPU Cores: {report['cpu_cores']}")
        print(f"Memory: {report['memory_gb']:.1f} GB")
        print(f"GPU Available: {report['gpu_available']}")
        print(f"GPU Recommended: {report['gpu_recommended']}")
        print(f"Performance Profile: {report['performance_profile']}")
        print(f"Recommended Threads: {report['recommended_threads']}")
        print(f"Recommended Tile Size: {report['recommended_tile_size']}px")

        # Specific warnings for macOS Monterey
        if report['is_mac_monterey']:
            print("\n⚠️  WARNING: macOS Monterey 12.x detected")
            print("   - MPS (GPU acceleration) may be unstable")
            print("   - CPU-only mode recommended")
            print("   - Consider updating to newer macOS version if possible")

        if report['performance_profile'] == 'low':
            print("\n⚠️  WARNING: Low-performance hardware detected")
            print("   - Consider using smaller tile sizes")
            print("   - Batch processing may be slow")

        return True

    except Exception as e:
        print(f"❌ Hardware detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_performance_config():
    """Test performance configuration system."""
    print("\n" + "="*60)
    print("PERFORMANCE CONFIGURATION TEST")
    print("="*60)

    try:
        from app.infrastructure.config.performance_config import (
            get_performance_config, get_config_manager
        )

        config = get_performance_config()
        config_manager = get_config_manager()

        print(f"Performance Profile: {config.performance_profile}")
        print(f"Force CPU Only: {config.force_cpu_only}")
        print(f"Disable GPU: {config.disable_gpu}")

        print("\nCellpose Configuration:")
        print(f"  Use GPU: {config.cellpose.use_gpu}")
        print(f"  GPU Fallback Enabled: {config.cellpose.gpu_fallback_enabled}")
        print(f"  Batch Size: {config.cellpose.batch_size}")
        print(f"  Timeout: {config.cellpose.timeout_seconds}s")
        print(f"  Max Tile Size: {config.cellpose.max_tile_size_pixels}px")
        print(f"  Split Large Tiles: {config.cellpose.split_large_tiles}")
        print(f"  Memory Limit: {config.cellpose.memory_limit_mb}MB")

        print("\nThreading Configuration:")
        print(f"  Max Segmentation Threads: {config.threading.max_segmentation_threads}")
        print(f"  Max Rendering Threads: {config.threading.max_rendering_threads}")
        print(f"  Use Thread Pool: {config.threading.use_thread_pool}")

        # Test config persistence
        config_dir = config_manager.CONFIG_DIR
        config_file = config_manager.CONFIG_FILE
        print(f"\nConfig Directory: {config_dir}")
        print(f"Config File: {config_file}")
        print(f"Config File Exists: {config_file.exists()}")

        return True

    except Exception as e:
        print(f"❌ Performance config test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cellpose_import():
    """Test Cellpose library import and basic functionality."""
    print("\n" + "="*60)
    print("CELLPOSE IMPORT TEST")
    print("="*60)

    try:
        print("Testing Cellpose import...")
        import cellpose
        print(f"✅ Cellpose version: {cellpose.__version__}")

        # Test PyTorch availability
        import torch
        print(f"✅ PyTorch version: {torch.__version__}")

        # Test MPS availability
        if hasattr(torch.backends, 'mps'):
            mps_available = torch.backends.mps.is_available()
            mps_built = torch.backends.mps.is_built()
            print(f"✅ MPS Available: {mps_available}")
            print(f"✅ MPS Built: {mps_built}")

            if mps_available and mps_built:
                # Test simple MPS operation
                try:
                    device = torch.device("mps")
                    test_tensor = torch.randn(2, 3, device=device)
                    _ = test_tensor * 2
                    print("✅ MPS simple operation test passed")
                except Exception as e:
                    print(f"⚠️  MPS operation test failed: {e}")
        else:
            print("ℹ️  MPS not available in this PyTorch build")

        # Test Cellpose model loading
        print("\nTesting Cellpose model loading...")
        from cellpose import models

        # Try to load model with GPU=False first (more reliable)
        try:
            model = models.CellposeModel(pretrained_model='cpsam', gpu=False)
            print("✅ Cellpose CPU model loaded successfully")
            del model
        except Exception as e:
            print(f"❌ Cellpose CPU model loading failed: {e}")

        return True

    except ImportError as e:
        print(f"❌ Import failed: {e}")
        print("\nInstallation instructions:")
        print("1. Install PyTorch: https://pytorch.org/get-started/locally/")
        print("2. Install Cellpose: pip install cellpose>=3.0")
        return False
    except Exception as e:
        print(f"❌ Cellpose test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cellpose_adapter():
    """Test CellposeAdapter with performance configuration."""
    print("\n" + "="*60)
    print("CELLPOSE ADAPTER TEST")
    print("="*60)

    try:
        from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter

        print("Testing CellposeAdapter initialization...")

        # Test with auto-config (gpu=None)
        adapter = CellposeAdapter(model_type="cpsam", gpu=None)
        print(f"✅ CellposeAdapter initialized")
        print(f"   Model type: {adapter._model_type}")
        print(f"   GPU enabled: {adapter._gpu}")
        print(f"   Batch size: {adapter._batch_size}")
        print(f"   Timeout: {adapter._timeout_seconds}s")
        print(f"   Max tile size: {adapter._max_tile_size}px")

        # Test memory check (if psutil available)
        try:
            memory_ok = adapter._check_memory_usage()
            print(f"   Memory check: {'OK' if memory_ok else 'Warning'}")
        except:
            print("   Memory check: psutil not available")

        return True

    except Exception as e:
        print(f"❌ CellposeAdapter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def generate_recommendations():
    """Generate recommendations based on test results."""
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)

    try:
        from app.infrastructure.config.hardware_detector import get_hardware_detector
        detector = get_hardware_detector()
        profile = detector.get_performance_profile()

        print(f"Based on your hardware profile: {profile.upper()}")

        if profile == "low":
            print("\n🔧 For LOW performance hardware:")
            print("   • Use tile size ≤ 1000x1000 pixels")
            print("   • Enable 'Split large tiles' option")
            print("   • Use CPU-only mode (disable GPU)")
            print("   • Set batch size to 1")
            print("   • Expect longer processing times")

        elif profile == "medium":
            print("\n🔧 For MEDIUM performance hardware:")
            print("   • Use tile size ≤ 1500x1500 pixels")
            print("   • Enable 'Split large tiles' for images > 2000px")
            print("   • GPU acceleration depends on macOS version")
            print("   • Monterey (12.x): Use CPU-only")
            print("   • Newer macOS: Try GPU with fallback")
            print("   • Batch size: 1")

        else:  # high
            print("\n🔧 For HIGH performance hardware:")
            print("   • Tile size up to 2000x2000 pixels")
            print("   • GPU acceleration recommended")
            print("   • Batch size: 2 for multiple images")
            print("   • No need to split tiles")
            print("   • Can process larger images efficiently")

        # macOS Monterey specific
        if detector.is_mac_monterey:
            print("\n🍎 macOS Monterey 12.x specific:")
            print("   • PyTorch MPS may be unstable")
            print("   • Recommended: CPU-only mode")
            print("   • If GPU needed: PyTorch 2.2.2 or newer")
            print("   • Monitor for 'BFloat16' errors")

        print("\n⚙️  Configuration file:")
        config_path = Path.home() / ".grid-analyzer" / "config.json"
        print(f"   • Location: {config_path}")
        print("   • Edit manually for custom settings")
        print("   • Delete to reset to defaults")

    except Exception as e:
        print(f"❌ Could not generate recommendations: {e}")


def main():
    """Main diagnostic function."""
    print("="*60)
    print("GRID-IMAGE-ANALYZER HARDWARE DIAGNOSTIC TOOL")
    print("="*60)
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Working directory: {os.getcwd()}")
    print("="*60)

    tests_passed = 0
    tests_total = 4

    # Run tests
    if test_hardware_detection():
        tests_passed += 1

    if test_performance_config():
        tests_passed += 1

    if test_cellpose_import():
        tests_passed += 1

    if test_cellpose_adapter():
        tests_passed += 1

    # Generate recommendations
    generate_recommendations()

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Tests passed: {tests_passed}/{tests_total}")

    if tests_passed == tests_total:
        print("✅ All tests passed! Your system should work well.")
    elif tests_passed >= 2:
        print("⚠️  Some tests passed. System may work with limitations.")
    else:
        print("❌ Multiple tests failed. Check installation and compatibility.")

    print("\nNext steps:")
    print("1. Run the application: python -m main")
    print("2. Check logs for any warnings or errors")
    print("3. Adjust settings in ~/.grid-analyzer/config.json if needed")
    print("="*60)

    return 0 if tests_passed >= 2 else 1


if __name__ == "__main__":
    sys.exit(main())