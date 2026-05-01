#!/usr/bin/env python3
"""
Test script to validate Cellpose 4.0 migration.
Checks compatibility with the CellposeAdapter class.
"""

import sys
import logging
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_cellpose_version():
    """Verify Cellpose version is 4.0+"""
    try:
        import cellpose
        version = cellpose.__version__
        major_version = int(version.split('.')[0])
        
        logger.info(f"✓ Cellpose version: {version}")
        assert major_version >= 4, f"Expected Cellpose 4.0+, got {version}"
        return True
    except Exception as e:
        logger.error(f"✗ Failed to verify Cellpose version: {e}")
        return False

def test_cellpose_model_loading():
    """Test loading CellposeModel (CP4 API)"""
    try:
        from cellpose import models
        
        logger.info("Testing CellposeModel instantiation...")
        model = models.CellposeModel(pretrained_model='nuclei', gpu=False)
        
        logger.info(f"✓ CellposeModel loaded successfully")
        logger.info(f"  - Model type: nuclei")
        logger.info(f"  - GPU: False")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to load CellposeModel: {e}")
        return False

def test_adapter_instantiation():
    """Test CellposeAdapter initialization with CP4"""
    try:
        from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
        
        logger.info("Testing CellposeAdapter instantiation...")
        adapter = CellposeAdapter(model_type='nuclei', gpu=False)
        
        logger.info(f"✓ CellposeAdapter initialized successfully")
        logger.info(f"  - Model type: nuclei")
        logger.info(f"  - GPU: False")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to initialize CellposeAdapter: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_adapter_with_sample_image():
    """Test CellposeAdapter.segment() with a sample image"""
    try:
        import numpy as np
        from PIL import Image
        from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter
        
        logger.info("Testing CellposeAdapter.segment() with sample image...")
        
        # Create a minimal test image (100x100 grayscale with a bright spot)
        test_image_array = np.zeros((100, 100), dtype=np.uint8)
        test_image_array[40:60, 40:60] = 200  # Add a bright nucleus-like region
        
        # Convert to PIL Image for consistency
        test_image = Image.fromarray(test_image_array, mode='L')
        
        adapter = CellposeAdapter(model_type='nuclei', gpu=False)
        polygons = adapter.segment(test_image, diameter=30.0)
        
        logger.info(f"✓ Segmentation completed")
        logger.info(f"  - Input image: 100x100 grayscale")
        logger.info(f"  - Detected objects: {len(polygons)}")
        if polygons:
            logger.info(f"  - First polygon vertices: {len(polygons[0])}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed segmentation test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_channels_compatibility():
    """Verify CP4 channel handling is compatible"""
    try:
        import numpy as np
        from cellpose import models
        
        logger.info("Testing CP4 channel handling...")
        model = models.CellposeModel(pretrained_model='nuclei', gpu=False)
        
        # Create test image
        test_img = np.random.randint(0, 256, (100, 100), dtype=np.uint8)
        
        # CP4 v4+ auto-detects channels (no channels parameter needed)
        masks, flows, styles = model.eval(
            test_img,
            diameter=None,  # CP4 doesn't require diameter
            flow_threshold=0.4,
            cellprob_threshold=0.0,
        )
        
        logger.info(f"✓ Channel handling compatible")
        logger.info(f"  - Masks shape: {masks.shape if hasattr(masks, 'shape') else type(masks)}")
        logger.info(f"  - Styles type: {type(styles)}")
        return True
    except Exception as e:
        logger.error(f"✗ Channel handling test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all migration tests"""
    logger.info("=" * 60)
    logger.info("Cellpose 4.0 Migration Test Suite")
    logger.info("=" * 60)
    
    tests = [
        ("Cellpose Version", test_cellpose_version),
        ("CellposeModel Loading", test_cellpose_model_loading),
        ("CellposeAdapter Init", test_adapter_instantiation),
        ("Channel Compatibility", test_channels_compatibility),
        ("Segmentation Test", test_adapter_with_sample_image),
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n[{len(results)+1}/{len(tests)}] {test_name}...")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"✗ Test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n🎉 All tests passed! Cellpose 4.0 migration successful.")
        return 0
    else:
        logger.error(f"\n❌ {total - passed} test(s) failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
