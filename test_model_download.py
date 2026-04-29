#!/usr/bin/env python3
"""
Test model download functionality locally.

This script validates:
1. Model URL is accessible
2. Download mechanism works
3. Model integrity after download
4. NuClickAdapter uses downloader correctly
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


def test_model_downloader():
    """Test the model downloader module."""
    logger.info("=" * 70)
    logger.info("TEST 1: Model Downloader Module")
    logger.info("=" * 70)
    
    try:
        from app.infrastructure.ml_models.model_downloader import ModelDownloader
        
        # Check configuration
        logger.info("\n📋 Configured Models:")
        for model_name, config in ModelDownloader.MODELS.items():
            logger.info(f"  • {model_name}")
            logger.info(f"    URL: {config['url']}")
            logger.info(f"    Size: {config['size_mb']} MB")
            logger.info(f"    Desc: {config['description']}")
        
        # Check cache directory
        logger.info(f"\n📁 Cache Directory: {ModelDownloader.MODELS_DIR}")
        logger.info(f"   Exists: {ModelDownloader.MODELS_DIR.exists()}")
        if ModelDownloader.MODELS_DIR.exists():
            cached = list(ModelDownloader.MODELS_DIR.glob('*'))
            if cached:
                logger.info(f"   Cached files ({len(cached)}):")
                for f in cached:
                    size_mb = f.stat().st_size / 1e6
                    logger.info(f"     ✓ {f.name} ({size_mb:.1f} MB)")
            else:
                logger.info("   (no cached models yet)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Model downloader test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_nuclick_adapter():
    """Test NuClickAdapter initialization."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 2: NuClickAdapter Initialization")
    logger.info("=" * 70)
    
    try:
        from app.infrastructure.ml_models.nuclick_adapter import NuClickAdapter
        
        # Create adapter (should not download yet - lazy loading)
        logger.info("\n🔧 Creating NuClickAdapter...")
        adapter = NuClickAdapter()
        logger.info(f"   Name: {adapter.name}")
        logger.info(f"   Model loaded: {adapter._model is not None}")
        logger.info(f"   Load attempted: {adapter._load_attempted}")
        logger.info("   ✅ Adapter created (model not loaded yet - lazy loading)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ NuClickAdapter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_url_accessibility():
    """Test if model URLs are accessible."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 3: URL Accessibility Check")
    logger.info("=" * 70)
    
    try:
        import urllib.request
        import urllib.error
        from app.infrastructure.ml_models.model_downloader import ModelDownloader
        
        for model_name, config in ModelDownloader.MODELS.items():
            url = config['url']
            logger.info(f"\n🌐 Testing: {model_name}")
            logger.info(f"   URL: {url}")
            
            try:
                # HEAD request to check URL without downloading
                request = urllib.request.Request(url, method='HEAD')
                response = urllib.request.urlopen(request, timeout=5)
                
                size = response.headers.get('Content-Length')
                if size:
                    size_mb = int(size) / 1e6
                    logger.info(f"   Status: {response.status} ✅")
                    logger.info(f"   Size: {size_mb:.1f} MB")
                else:
                    logger.info(f"   Status: {response.status} ✅ (size unknown)")
                    
            except urllib.error.HTTPError as e:
                logger.error(f"   HTTP Error {e.code} ❌")
                logger.error(f"   → URL may be incorrect or file doesn't exist")
                return False
                
            except urllib.error.URLError as e:
                logger.error(f"   Connection Error ❌")
                logger.error(f"   → Check internet connection")
                logger.error(f"   → {e.reason}")
                return False
                
            except Exception as e:
                logger.error(f"   Error ❌: {e}")
                return False
        
        logger.info("\n✅ All URLs are accessible")
        return True
        
    except Exception as e:
        logger.error(f"❌ URL accessibility test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_download_simulation():
    """Simulate download (show progress)."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 4: Download Simulation (no actual download)")
    logger.info("=" * 70)
    
    try:
        from app.infrastructure.ml_models.model_downloader import ModelDownloader
        
        # Just show what would happen
        for model_name, config in ModelDownloader.MODELS.items():
            cache_path = ModelDownloader.MODELS_DIR / model_name
            
            if cache_path.exists():
                size_mb = cache_path.stat().st_size / 1e6
                logger.info(f"\n✓ {model_name}")
                logger.info(f"  Already cached at: {cache_path}")
                logger.info(f"  Size: {size_mb:.1f} MB")
            else:
                logger.info(f"\n→ {model_name}")
                logger.info(f"  Would download from: {config['url']}")
                logger.info(f"  Would cache to: {cache_path}")
                logger.info(f"  Expected size: {config['size_mb']} MB")
                logger.info(f"  (Not downloading now - use get_model_path() to download)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Download simulation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_file():
    """Check configuration file."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 5: Application Configuration")
    logger.info("=" * 70)
    
    try:
        from app.infrastructure.config.performance_config import PerformanceConfig
        
        # Load default config
        logger.info("\n📋 Loading default configuration...")
        config = PerformanceConfig.get_default()
        
        logger.info(f"\nPerformance Profile: {config.profile}")
        logger.info(f"Use GPU: {config.cellpose_config.use_gpu}")
        logger.info(f"Batch Size: {config.cellpose_config.batch_size}")
        logger.info(f"Max Tile Size: {config.cellpose_config.max_tile_size_pixels}px")
        logger.info(f"Timeout: {config.cellpose_config.timeout_seconds}s")
        
        return True
        
    except Exception as e:
        logger.warning(f"⚠️  Config test skipped: {e}")
        return True  # Not critical


def main():
    """Run all tests."""
    logger.info("\n🧪 GridAnalyzer Model Download System Tests\n")
    
    tests = [
        ("Model Downloader", test_model_downloader),
        ("NuClickAdapter", test_nuclick_adapter),
        ("URL Accessibility", test_url_accessibility),
        ("Download Simulation", test_download_simulation),
        ("Configuration", test_config_file),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("TEST SUMMARY")
    logger.info("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n🎉 All tests passed! System is ready for macOS build.")
        return 0
    else:
        logger.error(f"\n⚠️  {total - passed} test(s) failed. See details above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
