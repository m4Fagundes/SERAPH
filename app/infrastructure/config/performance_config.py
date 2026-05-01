"""
PerformanceConfig — Adaptive performance settings based on hardware.

Architecture: Clean Architecture (Infrastructure Layer)
- Uses HardwareDetector to detect capabilities
- Provides optimized configurations for each hardware profile
- Allows manual user overrides
- Persists settings in ~/.grid-analyzer/config.json

Design Decision (python-patterns §3 — Configuration):
    Settings are hierarchical: default → hardware-based → user-override.
    Values are immutable after initialization to avoid race conditions.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, Optional

from .hardware_detector import get_hardware_detector

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CellposeConfig:
    """Cellpose specific settings."""

    # GPU/CPU
    use_gpu: bool = False
    gpu_fallback_enabled: bool = True

    # Performance
    batch_size: int = 1  # Number of images processed per batch
    timeout_seconds: int = 300  # 5 minutes maximum timeout

    # Cellpose Parameters
    flow_threshold: float = 0.4
    cellprob_threshold: float = 0.0
    min_size: int = 15

    # Memory
    max_tile_size_pixels: int = 2000  # Maximum tile size (width/height)
    split_large_tiles: bool = True  # Automatically split large tiles
    memory_limit_mb: int = 2048  # Memory limit per operation (MB)


@dataclass(frozen=True)
class ThreadingConfig:
    """Threading settings."""

    max_segmentation_threads: int = 2
    max_rendering_threads: int = 4
    use_thread_pool: bool = True


@dataclass(frozen=True)
class PerformanceConfig:
    """Complete performance configuration."""

    # Specific settings (no defaults first)
    cellpose: CellposeConfig
    threading: ThreadingConfig

    # Detected profile
    performance_profile: str = "medium"  # low, medium, high

    # Compatibility flags
    force_cpu_only: bool = False  # Override to force CPU
    disable_gpu: bool = False  # Disable GPU completely

    @classmethod
    def create_for_hardware(cls, hardware_detector=None) -> "PerformanceConfig":
        """Creates optimized configuration for detected hardware."""
        if hardware_detector is None:
            hardware_detector = get_hardware_detector()

        profile = hardware_detector.get_performance_profile()
        logger.info("Creating performance config for profile: %s", profile)

        # Settings based on profile
        if profile == "low":
            return cls._create_low_performance_config(hardware_detector)
        elif profile == "medium":
            return cls._create_medium_performance_config(hardware_detector)
        else:  # high
            return cls._create_high_performance_config(hardware_detector)

    @classmethod
    def _create_low_performance_config(cls, detector) -> "PerformanceConfig":
        """Configuration for very limited hardware."""
        # macOS Monterey: do not use GPU
        use_gpu = detector.gpu_recommended and not detector.is_mac_monterey

        return cls(
            cellpose=CellposeConfig(
                use_gpu=use_gpu,
                batch_size=1,  # Always 1 in low performance
                timeout_seconds=180,  # 3 minutes
                max_tile_size_pixels=1000,
                split_large_tiles=True,
                memory_limit_mb=1024,  # 1GB limit
            ),
            threading=ThreadingConfig(
                max_segmentation_threads=1,
                max_rendering_threads=2,
                use_thread_pool=True,
            ),
            performance_profile="low",
            force_cpu_only=detector.is_mac_monterey,  # Monterey forces CPU
        )

    @classmethod
    def _create_medium_performance_config(cls, detector) -> "PerformanceConfig":
        """Configuration for modest hardware."""
        use_gpu = detector.gpu_recommended and not detector.is_mac_monterey
        
        # Increase batch size if GPU is recommended
        batch_size = 2 if use_gpu else 1

        return cls(
            cellpose=CellposeConfig(
                use_gpu=use_gpu,
                batch_size=batch_size,  # 2 with GPU, 1 with CPU
                timeout_seconds=300,  # 5 minutes
                max_tile_size_pixels=1500,
                split_large_tiles=True,
                memory_limit_mb=2048,  # 2GB limit
            ),
            threading=ThreadingConfig(
                max_segmentation_threads=2,
                max_rendering_threads=4,
                use_thread_pool=True,
            ),
            performance_profile="medium",
            force_cpu_only=detector.is_mac_monterey,
        )

    @classmethod
    def _create_high_performance_config(cls, detector) -> "PerformanceConfig":
        """Configuration for reasonable hardware — OPTIMIZED FOR MAXIMUM GPU."""
        use_gpu = detector.gpu_recommended and not detector.is_mac_monterey

        # For macOS Monterey, splitting large tiles is recommended
        split_large_tiles = detector.is_mac_monterey
        
        # Increase batch size MASSIVELY to saturate GPU
        # RTX 2060 (6GB) can process 16+ images of 512x512 simultaneously
        batch_size = 16 if use_gpu else 2
        
        # Increase max_tile_size to process fewer tiles sequentially
        # RTX 2060 supports up to ~3000px without running out of memory
        max_tile_size = 3000 if use_gpu else 2000
        
        # Increase timeout for larger batches
        timeout = 900 if use_gpu else 600  # 15 min vs 10 min

        return cls(
            cellpose=CellposeConfig(
                use_gpu=use_gpu,
                batch_size=batch_size,  # 16 with GPU, 2 with CPU
                timeout_seconds=timeout,  # 15 minutes with GPU
                max_tile_size_pixels=max_tile_size,  # 3000 with GPU
                split_large_tiles=split_large_tiles,
                memory_limit_mb=4096,  # 4GB limit
            ),
            threading=ThreadingConfig(
                max_segmentation_threads=4,
                max_rendering_threads=8,
                use_thread_pool=True,
            ),
            performance_profile="high",
            force_cpu_only=detector.is_mac_monterey,  # Monterey forces CPU
        )

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary for serialization."""
        return {
            "performance_profile": self.performance_profile,
            "cellpose": asdict(self.cellpose),
            "threading": asdict(self.threading),
            "force_cpu_only": self.force_cpu_only,
            "disable_gpu": self.disable_gpu,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceConfig":
        """Creates from dictionary, ignoring unknown keys for forward compatibility."""
        import dataclasses

        cellpose_data = data.get("cellpose", {})
        threading_data = data.get("threading", {})

        # Filter out keys that are not fields of the dataclass
        # (handles old config files that may contain removed fields)
        cellpose_fields = {f.name for f in dataclasses.fields(CellposeConfig)}
        threading_fields = {f.name for f in dataclasses.fields(ThreadingConfig)}
        cellpose_data = {k: v for k, v in cellpose_data.items() if k in cellpose_fields}
        threading_data = {k: v for k, v in threading_data.items() if k in threading_fields}

        return cls(
            cellpose=CellposeConfig(**cellpose_data),
            threading=ThreadingConfig(**threading_data),
            performance_profile=data.get("performance_profile", "medium"),
            force_cpu_only=data.get("force_cpu_only", False),
            disable_gpu=data.get("disable_gpu", False),
        )


class ConfigManager:
    """Manages persistent user settings."""

    CONFIG_DIR = Path.home() / ".grid-analyzer"
    CONFIG_FILE = CONFIG_DIR / "config.json"

    def __init__(self):
        self._config: Optional[PerformanceConfig] = None
        self._user_overrides: Dict[str, Any] = {}

        # Ensure directory exists
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def load_or_create_config(self) -> PerformanceConfig:
        """Loads user configuration or creates a new one based on hardware."""
        # First, create hardware-based configuration
        hardware_config = PerformanceConfig.create_for_hardware()

        try:
            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, 'r', encoding='utf-8-sig') as f:
                    user_data = json.load(f)

                # Apply user overrides
                merged_config = self._merge_configs(hardware_config, user_data)
                logger.info("Loaded user config from %s", self.CONFIG_FILE)
                self._config = merged_config
                return merged_config
            else:
                # Save default configuration
                self._save_config(hardware_config)
                self._config = hardware_config
                return hardware_config

        except Exception as e:
            logger.warning("Failed to load user config: %s. Using hardware defaults.", e)
            self._config = hardware_config
            return hardware_config

    def save_user_overrides(self, overrides: Dict[str, Any]) -> None:
        """Saves user overrides and updates configuration."""
        self._user_overrides.update(overrides)

        # Reload base configuration with new overrides
        hardware_config = PerformanceConfig.create_for_hardware()
        merged_config = self._merge_configs(hardware_config, self._user_overrides)

        self._config = merged_config
        self._save_config(merged_config)
        logger.info("Saved user config overrides: %s", overrides)

    def get_config(self) -> PerformanceConfig:
        """Returns current configuration."""
        if self._config is None:
            self._config = self.load_or_create_config()
        return self._config

    def reset_to_defaults(self) -> PerformanceConfig:
        """Resets to hardware-based default settings."""
        self._user_overrides.clear()

        if self.CONFIG_FILE.exists():
            self.CONFIG_FILE.unlink()

        hardware_config = PerformanceConfig.create_for_hardware()
        self._config = hardware_config
        self._save_config(hardware_config)

        logger.info("Reset config to hardware defaults")
        return hardware_config

    def _merge_configs(self, base: PerformanceConfig, user_data: Dict[str, Any]) -> PerformanceConfig:
        """Merges base configuration with user overrides."""
        base_dict = base.to_dict()

        # Recursive merge
        def merge_dicts(base_dict, user_dict):
            result = base_dict.copy()
            for key, value in user_dict.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = merge_dicts(result[key], value)
                else:
                    result[key] = value
            return result

        merged_dict = merge_dicts(base_dict, user_data)
        return PerformanceConfig.from_dict(merged_dict)

    def _save_config(self, config: PerformanceConfig) -> None:
        """Saves configuration to file."""
        config_dict = config.to_dict()
        config_dict["_version"] = "1.0"
        config_dict["_timestamp"] = os.path.getmtime(__file__) if os.path.exists(__file__) else 0

        with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)


# Singleton for use throughout the application
_config_manager_instance: Optional[ConfigManager] = None

def get_config_manager() -> ConfigManager:
    """Returns singleton instance of ConfigManager."""
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = ConfigManager()
    return _config_manager_instance

def get_performance_config() -> PerformanceConfig:
    """Returns current performance configuration."""
    return get_config_manager().get_config()