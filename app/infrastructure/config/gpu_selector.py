"""
GPUSelector — Seleciona automaticamente a GPU compatível com PyTorch.

Problema: RTX 5060 não é suportada ainda em PyTorch.
Solução: Se houver múltiplas GPUs, usar a primeira compatível.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_best_cuda_device() -> Optional[int]:
    """
    Retorna o índice do melhor dispositivo CUDA compatível com PyTorch.
    
    Regras:
    1. Se CUDA não está disponível: retorna None
    2. Se há uma GPU compatível: retorna seu índice
    3. Se nenhuma GPU é compatível: retorna None (forçará CPU fallback)
    
    Returns:
        Índice da GPU (0, 1, ...) ou None se nenhuma compatível
    """
    try:
        import torch
    except ImportError:
        logger.warning("PyTorch not available - GPU selection disabled")
        return None
    
    if not torch.cuda.is_available():
        logger.debug("CUDA not available")
        return None
    
    # Compute capabilities suportadas pelo PyTorch atual
    # sm_50 (Maxwell), sm_60 (Pascal), sm_70 (Volta), sm_75 (Turing), sm_80 (Ampere), sm_86 (Ampere), sm_90 (Hopper)
    supported_capabilities = {(5, 0), (6, 0), (6, 1), (7, 0), (7, 5), (8, 0), (8, 6), (9, 0)}
    
    num_devices = torch.cuda.device_count()
    compatible_devices = []
    
    for device_id in range(num_devices):
        try:
            device_name = torch.cuda.get_device_name(device_id)
            device_cap = torch.cuda.get_device_capability(device_id)
            
            if device_cap in supported_capabilities:
                logger.info(
                    f"✅ GPU {device_id}: {device_name} (sm_{device_cap[0]}{device_cap[1]}) - SUPPORTED"
                )
                compatible_devices.append(device_id)
            else:
                logger.warning(
                    f"❌ GPU {device_id}: {device_name} (sm_{device_cap[0]}{device_cap[1]}) - NOT SUPPORTED"
                )
        except Exception as e:
            logger.warning(f"Failed to query GPU {device_id}: {e}")
    
    if compatible_devices:
        best_device = compatible_devices[0]
        logger.info(f"Selected GPU device {best_device} for CUDA operations")
        return best_device
    else:
        logger.warning("No compatible CUDA devices found - will use CPU")
        return None


def set_cuda_device(device_id: Optional[int]) -> None:
    """
    Define qual dispositivo CUDA será usado.
    
    Args:
        device_id: Índice do dispositivo ou None para CPU
    """
    try:
        import torch
        
        if device_id is None:
            logger.info("CUDA device set to None (will use CPU)")
            return
        
        if not torch.cuda.is_available():
            logger.warning("CUDA not available - ignoring device selection")
            return
        
        if device_id >= torch.cuda.device_count():
            logger.warning(f"Device {device_id} not available (only {torch.cuda.device_count()} devices)")
            return
        
        torch.cuda.set_device(device_id)
        device_name = torch.cuda.get_device_name(device_id)
        logger.info(f"CUDA device set to {device_id}: {device_name}")
        
    except Exception as e:
        logger.warning(f"Failed to set CUDA device: {e}")


# Auto-select best GPU on import
try:
    best_device = get_best_cuda_device()
    if best_device is not None:
        set_cuda_device(best_device)
        # Salvar para que o hardware_detector saiba qual GPU usar
        os.environ["CUDA_VISIBLE_DEVICES"] = str(best_device)
except Exception as e:
    logger.warning(f"GPU auto-selection failed: {e}")
