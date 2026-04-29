"""
HardwareDetector — Detecta capacidades de hardware e compatibilidade.

Arquitetura: Clean Architecture (Infrastructure Layer)
- Detecta CPU cores, memória, GPU/MPS disponibilidade
- Verifica compatibilidade com macOS Monterey 12.7.6
- Fornece recomendações para configuração de performance
- Auto-seleciona melhor GPU compatível com PyTorch

Design Decision (python-patterns §8 — Error Handling):
    Todas as detecções têm fallbacks seguros. Se uma detecção falhar,
    retorna valores conservadores apropriados para hardware antigo.
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
    Detecta capacidades de hardware e fornece recomendações
    para configuração de performance.

    Focado em compatibilidade com macOS Monterey 12.7.6 e hardware limitado.
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
        """Detecta versão do macOS e se é Monterey (12.x)."""
        try:
            mac_ver = platform.mac_ver()[0]  # e.g., "12.7.6"
            self.mac_version = mac_ver

            # Parse major version
            try:
                major_version = int(mac_ver.split('.')[0])
                # Monterey é versão 12
                self.is_mac_monterey = major_version == 12
            except (ValueError, IndexError):
                self.is_mac_monterey = False

            logger.debug("macOS version detected: %s (Monterey: %s)",
                        mac_ver, self.is_mac_monterey)
        except Exception as e:
            logger.warning("Failed to detect macOS version: %s", e)
            self.is_mac_monterey = False

    def _detect_cpu_cores(self) -> int:
        """Detecta número de cores CPU disponíveis."""
        try:
            import multiprocessing
            cores = multiprocessing.cpu_count()

            # Para hardware muito antigo, limitar threads
            if cores <= 2:
                logger.info("Low core count detected: %d cores", cores)
                return max(1, cores)
            elif cores <= 4:
                # CPUs modestas - usar 75% dos cores para não sobrecarregar
                return max(2, cores - 1)
            else:
                # CPUs modernas - usar todos os cores menos 2 para sistema
                return max(4, cores - 2)

        except Exception as e:
            logger.warning("Failed to detect CPU cores: %s. Using conservative default (2).", e)
            return 2  # Default conservador

    def _detect_memory(self) -> float:
        """Detecta memória RAM disponível em GB."""
        try:
            if self.is_mac:
                # macOS: usar sysctl
                result = subprocess.run(
                    ['sysctl', 'hw.memsize'],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode == 0:
                    # hw.memsize está em bytes
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
            return 4.0  # Default conservador

    def _detect_gpu_availability(self) -> bool:
        """
        Detecta se GPU/MPS/CUDA está disponível e funcional.

        Detecta:
        - macOS: MPS (Metal Performance Shaders)
        - Windows/Linux: CUDA (NVIDIA GPUs)
        """
        try:
            import torch
        except ImportError:
            logger.debug("PyTorch not installed - GPU detection unavailable")
            return False

        if self.is_mac:
            # macOS: Detectar MPS
            # macOS Monterey 12.x tem problemas conhecidos com MPS
            if self.is_mac_monterey:
                logger.info("macOS Monterey detected - MPS may be unstable")

                # Testar PyTorch MPS se disponível
                if hasattr(torch.backends, 'mps'):
                    mps_available = torch.backends.mps.is_available()
                    mps_built = torch.backends.mps.is_built()

                    logger.debug("PyTorch MPS: available=%s, built=%s",
                                mps_available, mps_built)

                    # Em Monterey, mesmo se disponível, pode ser instável
                    if mps_available and mps_built:
                        # Testar operação simples para verificar estabilidade
                        try:
                            # Teste leve de MPS
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
                # macOS mais novo - confiar na detecção do PyTorch
                if hasattr(torch.backends, 'mps'):
                    is_available = torch.backends.mps.is_available() and torch.backends.mps.is_built()
                    if is_available:
                        logger.info("PyTorch MPS available on macOS")
                    return is_available
                return False
        else:
            # Windows/Linux: Detectar CUDA
            logger.debug("Detecting CUDA availability on %s", self.system)
            
            try:
                # Verificar se CUDA está disponível no PyTorch
                cuda_available = torch.cuda.is_available()
                
                if not cuda_available:
                    logger.debug("CUDA not detected by PyTorch")
                    return False
                
                # Verificar número de GPUs
                num_gpus = torch.cuda.device_count()
                if num_gpus == 0:
                    logger.debug("PyTorch reports CUDA available but no GPUs found")
                    return False
                
                logger.info("CUDA available with %d GPU(s)", num_gpus)
                
                # Procurar por GPU compatível (mesmo que não seja a primeira)
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
                    # Há pelo menos uma GPU compatível
                    logger.info(f"Found {len(compatible_gpus)} compatible GPU(s)")
                    # Testar operação simples em GPU compatível para verificar funcionalidade
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
                    # Nenhuma GPU compatível encontrada
                    logger.warning(f"CUDA available but no compatible GPUs found (found {num_gpus} total)")
                    return False
                    
            except Exception as e:
                logger.warning("CUDA detection error: %s", e)
                return False

    def _recommend_gpu_usage(self) -> bool:
        """
        Recomenda se deve usar GPU baseado em hardware e compatibilidade.

        Regras:
        1. GPU não disponível: não recomendar (óbvio)
        2. macOS Monterey: não recomendar GPU (instável com MPS)
        3. Windows/Linux com CUDA: recomendar (menos restritivo que macOS)
        4. macOS com MPS: recomendar se tiver 6+ GB RAM
        5. Fallback: não recomendar
        """
        if not self.gpu_available:
            return False

        if self.is_mac_monterey:
            # Monterey tem problemas conhecidos com MPS
            logger.info("Not recommending GPU for macOS Monterey due to stability issues")
            return False

        if self.is_mac:
            # macOS com MPS: ser conservador com memória
            if self.memory_gb < 6.0:
                logger.info("Not recommending MPS for systems with < 6GB RAM")
                return False
            logger.info("MPS available on macOS with sufficient memory")
            return True
        else:
            # Windows/Linux com CUDA: menos restritivo
            # CUDA pode funcionar com até ~4GB, mas 6GB+ é mais confortável
            if self.memory_gb < 4.0:
                logger.info("Not recommending CUDA for systems with < 4GB RAM")
                return False
            logger.info("CUDA recommended for Windows/Linux")
            return True

    def get_performance_profile(self) -> str:
        """
        Retorna perfil de performance recomendado.

        Returns:
            "low" - Hardware muito limitado (<= 2 cores, <= 4GB RAM)
            "medium" - Hardware modesto (2-4 cores, 4-8GB RAM)
            "high" - Hardware razoável (4+ cores, 8+ GB RAM)
        """
        if self.cpu_cores <= 2 or self.memory_gb <= 4.0:
            return "low"
        elif self.cpu_cores <= 4 or self.memory_gb <= 8.0:
            return "medium"
        else:
            return "high"

    def get_recommended_threads(self) -> int:
        """Retorna número recomendado de threads para processamento."""
        profile = self.get_performance_profile()

        if profile == "low":
            return 1
        elif profile == "medium":
            return min(2, self.cpu_cores)
        else:  # high
            return min(4, max(2, self.cpu_cores - 2))

    def get_recommended_tile_size(self) -> int:
        """
        Retorna tamanho máximo recomendado para tiles em pixels.

        Tiles maiores usam mais memória. Ajustar baseado em RAM disponível.
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
        """Retorna relatório completo de detecção de hardware."""
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
        Cria detector com fallbacks seguros para quando a detecção falha.

        Útil para inicialização onde exceções não são aceitáveis.
        """
        try:
            return cls()
        except Exception as e:
            logger.error("Failed to create hardware detector: %s. Using safe defaults.", e)
            # Criar instância com valores padrão seguros
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


# Singleton para uso em toda a aplicação
_hardware_detector_instance: Optional[HardwareDetector] = None

def get_hardware_detector() -> HardwareDetector:
    """Retorna instância singleton do HardwareDetector."""
    global _hardware_detector_instance
    if _hardware_detector_instance is None:
        _hardware_detector_instance = HardwareDetector.create_safe_detector()
    return _hardware_detector_instance