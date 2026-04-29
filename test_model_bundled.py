#!/usr/bin/env python3
"""Test model downloader with bundled fallback."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.infrastructure.ml_models.model_downloader import ModelDownloader

print('Testing Model Downloader with bundled fallback...\n')
print('MODELS configuration:')
for name, config in ModelDownloader.MODELS.items():
    print(f'  {name}:')
    print(f'    URL: {config["url"] or "(none - using bundled)"}')
    print(f'    Bundled: {config["bundled_path"]}')
    print()

try:
    path = ModelDownloader.get_model_path('nuclick.pth')
    print(f'✅ Model path: {path}')
    print(f'   Exists: {path.exists()}')
    print(f'   Size: {path.stat().st_size / 1e6:.1f} MB')
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
