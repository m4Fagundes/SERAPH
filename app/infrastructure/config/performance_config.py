"""
PerformanceConfig — Configurações de performance adaptativas baseadas em hardware.

Arquitetura: Clean Architecture (Infrastructure Layer)
- Usa HardwareDetector para detectar capacidades
- Fornece configurações otimizadas para cada perfil de hardware
- Permite override manual pelo usuário
- Persiste configurações em ~/.grid-analyzer/config.json

Design Decision (python-patterns §3 — Configuration):
    Configurações são hierárquicas: default → hardware-based → user-override.
    Valores são imutáveis após inicialização para evitar race conditions.
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
    """Configurações específicas para o Cellpose."""

    # GPU/CPU
    use_gpu: bool = False
    gpu_fallback_enabled: bool = True

    # Performance
    batch_size: int = 1  # Número de imagens processadas por batch
    resample_factor: float = 1.0  # Downsampling (0.5 = metade do tamanho)
    timeout_seconds: int = 300  # 5 minutos timeout máximo

    # Parâmetros Cellpose
    flow_threshold: float = 0.4
    cellprob_threshold: float = 0.0
    min_size: int = 15

    # Memória
    max_tile_size_pixels: int = 2000  # Tamanho máximo de tile (largura/altura)
    split_large_tiles: bool = True  # Dividir tiles grandes automaticamente
    memory_limit_mb: int = 2048  # Limite de memória por operação (MB)


@dataclass(frozen=True)
class ThreadingConfig:
    """Configurações de threading."""

    max_segmentation_threads: int = 2
    max_rendering_threads: int = 4
    use_thread_pool: bool = True


@dataclass(frozen=True)
class PerformanceConfig:
    """Configuração completa de performance."""

    # Configurações específicas (sem valores padrão primeiro)
    cellpose: CellposeConfig
    threading: ThreadingConfig

    # Perfil detectado
    performance_profile: str = "medium"  # low, medium, high

    # Flags de compatibilidade
    force_cpu_only: bool = False  # Override para forçar CPU
    disable_gpu: bool = False  # Desabilitar GPU completamente

    @classmethod
    def create_for_hardware(cls, hardware_detector=None) -> "PerformanceConfig":
        """Cria configuração otimizada para hardware detectado."""
        if hardware_detector is None:
            hardware_detector = get_hardware_detector()

        profile = hardware_detector.get_performance_profile()
        logger.info("Creating performance config for profile: %s", profile)

        # Configurações baseadas no perfil
        if profile == "low":
            return cls._create_low_performance_config(hardware_detector)
        elif profile == "medium":
            return cls._create_medium_performance_config(hardware_detector)
        else:  # high
            return cls._create_high_performance_config(hardware_detector)

    @classmethod
    def _create_low_performance_config(cls, detector) -> "PerformanceConfig":
        """Configuração para hardware muito limitado."""
        # macOS Monterey: não usar GPU
        use_gpu = detector.gpu_recommended and not detector.is_mac_monterey

        return cls(
            cellpose=CellposeConfig(
                use_gpu=use_gpu,
                batch_size=1,  # Sempre 1 em low performance
                resample_factor=0.75,  # Downsample para economizar memória
                timeout_seconds=180,  # 3 minutos
                max_tile_size_pixels=1000,
                split_large_tiles=True,
                memory_limit_mb=1024,  # 1GB limite
            ),
            threading=ThreadingConfig(
                max_segmentation_threads=1,
                max_rendering_threads=2,
                use_thread_pool=True,
            ),
            performance_profile="low",
            force_cpu_only=detector.is_mac_monterey,  # Monterey força CPU
        )

    @classmethod
    def _create_medium_performance_config(cls, detector) -> "PerformanceConfig":
        """Configuração para hardware modesto."""
        use_gpu = detector.gpu_recommended and not detector.is_mac_monterey
        
        # Aumentar batch size se GPU for recomendada
        batch_size = 2 if use_gpu else 1

        return cls(
            cellpose=CellposeConfig(
                use_gpu=use_gpu,
                batch_size=batch_size,  # 2 com GPU, 1 com CPU
                resample_factor=1.0,  # Sem downsampling
                timeout_seconds=300,  # 5 minutos
                max_tile_size_pixels=1500,
                split_large_tiles=True,
                memory_limit_mb=2048,  # 2GB limite
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
        """Configuração para hardware razoável — OTIMIZADO PARA GPU MÁXIMA."""
        use_gpu = detector.gpu_recommended and not detector.is_mac_monterey

        # Para macOS Monterey, dividir tiles grandes é recomendado
        split_large_tiles = detector.is_mac_monterey
        
        # Aumentar batch size MASSIVAMENTE para saturar GPU
        # RTX 2060 (6GB) pode processar 16+ imagens de 512x512 simultaneamente
        batch_size = 16 if use_gpu else 2
        
        # Aumentar max_tile_size para processar menos tiles sequencialmente
        # RTX 2060 suporta até ~3000px sem ficar sem memória
        max_tile_size = 3000 if use_gpu else 2000
        
        # Aumentar timeout para batches maiores
        timeout = 900 if use_gpu else 600  # 15 min vs 10 min

        return cls(
            cellpose=CellposeConfig(
                use_gpu=use_gpu,
                batch_size=batch_size,  # 16 com GPU, 2 com CPU
                resample_factor=1.0,
                timeout_seconds=timeout,  # 15 minutos com GPU
                max_tile_size_pixels=max_tile_size,  # 3000 com GPU
                split_large_tiles=split_large_tiles,
                memory_limit_mb=4096,  # 4GB limite
            ),
            threading=ThreadingConfig(
                max_segmentation_threads=4,
                max_rendering_threads=8,
                use_thread_pool=True,
            ),
            performance_profile="high",
            force_cpu_only=detector.is_mac_monterey,  # Monterey força CPU
        )

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário para serialização."""
        return {
            "performance_profile": self.performance_profile,
            "cellpose": asdict(self.cellpose),
            "threading": asdict(self.threading),
            "force_cpu_only": self.force_cpu_only,
            "disable_gpu": self.disable_gpu,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceConfig":
        """Cria a partir de dicionário."""
        cellpose_data = data.get("cellpose", {})
        threading_data = data.get("threading", {})

        return cls(
            cellpose=CellposeConfig(**cellpose_data),
            threading=ThreadingConfig(**threading_data),
            performance_profile=data.get("performance_profile", "medium"),
            force_cpu_only=data.get("force_cpu_only", False),
            disable_gpu=data.get("disable_gpu", False),
        )


class ConfigManager:
    """Gerencia configurações persistentes do usuário."""

    CONFIG_DIR = Path.home() / ".grid-analyzer"
    CONFIG_FILE = CONFIG_DIR / "config.json"

    def __init__(self):
        self._config: Optional[PerformanceConfig] = None
        self._user_overrides: Dict[str, Any] = {}

        # Garantir que diretório existe
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def load_or_create_config(self) -> PerformanceConfig:
        """Carrega configuração do usuário ou cria nova baseada em hardware."""
        # Primeiro, criar configuração baseada em hardware
        hardware_config = PerformanceConfig.create_for_hardware()

        try:
            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    user_data = json.load(f)

                # Aplicar overrides do usuário
                merged_config = self._merge_configs(hardware_config, user_data)
                logger.info("Loaded user config from %s", self.CONFIG_FILE)
                self._config = merged_config
                return merged_config
            else:
                # Salvar configuração padrão
                self._save_config(hardware_config)
                self._config = hardware_config
                return hardware_config

        except Exception as e:
            logger.warning("Failed to load user config: %s. Using hardware defaults.", e)
            self._config = hardware_config
            return hardware_config

    def save_user_overrides(self, overrides: Dict[str, Any]) -> None:
        """Salva overrides do usuário e atualiza configuração."""
        self._user_overrides.update(overrides)

        # Recarregar configuração base com novos overrides
        hardware_config = PerformanceConfig.create_for_hardware()
        merged_config = self._merge_configs(hardware_config, self._user_overrides)

        self._config = merged_config
        self._save_config(merged_config)
        logger.info("Saved user config overrides: %s", overrides)

    def get_config(self) -> PerformanceConfig:
        """Retorna configuração atual."""
        if self._config is None:
            self._config = self.load_or_create_config()
        return self._config

    def reset_to_defaults(self) -> PerformanceConfig:
        """Reseta para configurações padrão baseadas em hardware."""
        self._user_overrides.clear()

        if self.CONFIG_FILE.exists():
            self.CONFIG_FILE.unlink()

        hardware_config = PerformanceConfig.create_for_hardware()
        self._config = hardware_config
        self._save_config(hardware_config)

        logger.info("Reset config to hardware defaults")
        return hardware_config

    def _merge_configs(self, base: PerformanceConfig, user_data: Dict[str, Any]) -> PerformanceConfig:
        """Mescla configuração base com overrides do usuário."""
        base_dict = base.to_dict()

        # Merge recursivo
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
        """Salva configuração em arquivo."""
        config_dict = config.to_dict()
        config_dict["_version"] = "1.0"
        config_dict["_timestamp"] = os.path.getmtime(__file__) if os.path.exists(__file__) else 0

        with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)


# Singleton para uso em toda a aplicação
_config_manager_instance: Optional[ConfigManager] = None

def get_config_manager() -> ConfigManager:
    """Retorna instância singleton do ConfigManager."""
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = ConfigManager()
    return _config_manager_instance

def get_performance_config() -> PerformanceConfig:
    """Retorna configuração de performance atual."""
    return get_config_manager().get_config()