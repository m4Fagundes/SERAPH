"""
Model Downloader — Automatically downloads required ML models on-demand.

Architecture: Infrastructure Layer
- Manages model downloads from remote storage
- Caches models in ~/.grid-analyzer/models/
- Falls back to bundled models if available
- Shows progress to user
- Handles network errors gracefully
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional, Callable
import urllib.request
import shutil

logger = logging.getLogger(__name__)


class ModelDownloader:
    """Manages downloading and caching ML models."""
    
    # Model URLs (configure before release)
    # Set to None to use bundled copy only (for development/testing)
    MODELS = {
        'nuclick.pth': {
            'url': 'https://huggingface.co/m4fagundes/grid-image-analyzer/resolve/main/nuclick.pth',
            'size_mb': 450,  # Approximate size
            'description': 'NuClick interactive segmentation model',
            'bundled_path': 'app/infrastructure/ml_models/nuclick_torch/weights/nuclick.pth',
        }
    }
    
    # Cache directory: ~/.grid-analyzer/models/
    MODELS_DIR = Path.home() / '.grid-analyzer' / 'models'
    
    def __init__(self):
        """Initialize downloader."""
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def get_model_path(cls, model_name: str) -> Path:
        """
        Get path to a model. Download if not exists, fall back to bundled.
        
        Args:
            model_name: Name of model (e.g., 'nuclick.pth')
            
        Returns:
            Path to model file (guaranteed to exist after return)
            
        Raises:
            FileNotFoundError: If model not found locally and download fails
            ValueError: If model_name not recognized
        """
        if model_name not in cls.MODELS:
            raise ValueError(f"Unknown model: {model_name}. Available: {list(cls.MODELS.keys())}")
        
        downloader = cls()
        return downloader._ensure_model_available(model_name)
    
    def _ensure_model_available(self, model_name: str) -> Path:
        """
        Ensure model exists locally. Try in order:
        1. Check cache directory
        2. Try to download (if URL configured)
        3. Fall back to bundled copy (if available)
        
        Args:
            model_name: Name of model file
            
        Returns:
            Path to available model
        """
        model_path = self.MODELS_DIR / model_name
        model_info = self.MODELS[model_name]
        
        # 1. Check if already cached
        if model_path.exists():
            logger.info(f"✅ Model {model_name} found in cache: {model_path}")
            return model_path
        
        # 2. Try to download (if URL configured)
        if model_info['url']:
            logger.info(f"Attempting to download {model_name}...")
            try:
                self._download_file(
                    url=model_info['url'],
                    dest=model_path,
                    size_mb=model_info['size_mb'],
                    description=model_info['description'],
                )
                return model_path
            except Exception as e:
                logger.warning(f"Download failed: {e}. Trying bundled copy...")
        
        # 3. Fall back to bundled copy
        bundled_path = Path(model_info['bundled_path'])
        if bundled_path.exists():
            logger.info(f"Using bundled model from: {bundled_path}")
            return bundled_path
        
        # Model not found anywhere
        raise FileNotFoundError(
            f"Model {model_name} not found!\n"
            f"  Cache: {model_path} (not found)\n"
            f"  Bundled: {bundled_path} (not found)\n"
            f"  Please check model_downloader.py configuration"
        )
    
    def _download_file(
        self,
        url: str,
        dest: Path,
        size_mb: float,
        description: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """
        Download file from URL with progress reporting.
        
        Args:
            url: File URL
            dest: Destination path
            size_mb: Expected file size in MB (for progress bar)
            description: Human-readable description
            progress_callback: Optional callback(downloaded_bytes, total_bytes)
        """
        try:
            # Create temporary file
            temp_path = dest.with_suffix('.tmp')
            
            def on_progress(block_num, block_size, total_size):
                """Progress callback for urllib."""
                downloaded = block_num * block_size
                if progress_callback:
                    progress_callback(downloaded, total_size)
                
                percent = (downloaded / total_size * 100) if total_size > 0 else 0
                logger.info(f"  {description}: {percent:.1f}% ({downloaded/1e6:.1f}MB / {total_size/1e6:.1f}MB)")
            
            # Download with progress
            logger.info(f"Starting download: {url}")
            urllib.request.urlretrieve(url, temp_path, reporthook=on_progress)
            
            # Move to final location
            shutil.move(str(temp_path), str(dest))
            logger.info(f"✅ Model downloaded successfully: {dest}")
            
        except Exception as e:
            # Clean up temp file
            if temp_path.exists():
                temp_path.unlink()
            
            logger.error(f"❌ Failed to download {description}: {e}")
            raise FileNotFoundError(
                f"Could not download {description} from {url}\n"
                f"Error: {e}\n"
                f"Please check your internet connection and try again."
            )


def get_model_with_progress(
    model_name: str,
    status_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    """
    Download model with status messages.
    
    Args:
        model_name: Name of model to download
        status_callback: Optional callback for UI status updates
        
    Returns:
        Path to model file
    """
    try:
        if status_callback:
            status_callback(f"Preparing to use {model_name}...")
        
        path = ModelDownloader.get_model_path(model_name)
        
        if status_callback:
            status_callback(f"✅ {model_name} ready")
        
        return path
        
    except Exception as e:
        error_msg = f"Failed to get {model_name}: {e}"
        logger.error(error_msg)
        if status_callback:
            status_callback(f"❌ Error: {error_msg}")
        raise
