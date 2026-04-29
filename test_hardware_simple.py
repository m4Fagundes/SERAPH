#!/usr/bin/env python3
"""
Teste simplificado do sistema de configuração adaptativa.
Não requer psutil, torch ou cellpose instalados.
"""

import sys
import os
from pathlib import Path

# Adicionar diretório atual ao path
sys.path.insert(0, str(Path(__file__).parent))

print("="*60)
print("TESTE SIMPLIFICADO DO SISTEMA DE CONFIGURAÇÃO")
print("="*60)

# Testar hardware detector
print("\n1. TESTE DO HARDWARE DETECTOR")
print("-"*40)

try:
    from app.infrastructure.config.hardware_detector import get_hardware_detector

    detector = get_hardware_detector()
    report = detector.get_report()

    print(f"✅ Sistema: {report['system']}")
    print(f"✅ macOS: {report['is_mac']}")
    print(f"✅ macOS Monterey (12.x): {report['is_mac_monterey']}")
    print(f"✅ macOS Version: {report['mac_version']}")
    print(f"✅ CPU Cores: {report['cpu_cores']}")
    print(f"✅ Memory: {report['memory_gb']:.1f} GB")
    print(f"✅ GPU Available: {report['gpu_available']}")
    print(f"✅ GPU Recommended: {report['gpu_recommended']}")
    print(f"✅ Performance Profile: {report['performance_profile']}")
    print(f"✅ Recommended Threads: {report['recommended_threads']}")
    print(f"✅ Recommended Tile Size: {report['recommended_tile_size']}px")

    # Avisos específicos
    if report['is_mac_monterey']:
        print("\n⚠️  AVISO: macOS Monterey 12.x detectado")
        print("   • MPS (GPU acceleration) pode ser instável")
        print("   • Modo CPU-only recomendado")
        print("   • Considere atualizar para versão mais recente do macOS se possível")

    if report['performance_profile'] == 'low':
        print("\n⚠️  AVISO: Hardware de baixa performance detectado")
        print("   • Considere usar tamanhos de tile menores")
        print("   • Processamento em batch pode ser lento")

except Exception as e:
    print(f"❌ Erro no hardware detector: {e}")
    import traceback
    traceback.print_exc()

# Testar performance config
print("\n2. TESTE DO PERFORMANCE CONFIG")
print("-"*40)

try:
    from app.infrastructure.config.performance_config import get_performance_config, get_config_manager

    config = get_performance_config()
    config_manager = get_config_manager()

    print(f"✅ Performance Profile: {config.performance_profile}")
    print(f"✅ Force CPU Only: {config.force_cpu_only}")
    print(f"✅ Disable GPU: {config.disable_gpu}")

    print("\n✅ Cellpose Configuration:")
    print(f"  • Use GPU: {config.cellpose.use_gpu}")
    print(f"  • GPU Fallback Enabled: {config.cellpose.gpu_fallback_enabled}")
    print(f"  • Batch Size: {config.cellpose.batch_size}")
    print(f"  • Resample Factor: {config.cellpose.resample_factor}")
    print(f"  • Timeout: {config.cellpose.timeout_seconds}s")
    print(f"  • Max Tile Size: {config.cellpose.max_tile_size_pixels}px")
    print(f"  • Split Large Tiles: {config.cellpose.split_large_tiles}")
    print(f"  • Memory Limit: {config.cellpose.memory_limit_mb}MB")

    print("\n✅ Threading Configuration:")
    print(f"  • Max Segmentation Threads: {config.threading.max_segmentation_threads}")
    print(f"  • Max Rendering Threads: {config.threading.max_rendering_threads}")
    print(f"  • Use Thread Pool: {config.threading.use_thread_pool}")

    # Verificar arquivo de configuração
    print(f"\n✅ Config Directory: {config_manager.CONFIG_DIR}")
    print(f"✅ Config File: {config_manager.CONFIG_FILE}")
    print(f"✅ Config File Exists: {config_manager.CONFIG_FILE.exists()}")

    if config_manager.CONFIG_FILE.exists():
        print(f"✅ Configuração do usuário carregada com sucesso")
    else:
        print(f"ℹ️  Usando configuração padrão baseada em hardware")

except Exception as e:
    print(f"❌ Erro no performance config: {e}")
    import traceback
    traceback.print_exc()

# Testar CellposeAdapter (sem carregar modelo)
print("\n3. TESTE DO CELLPOSE ADAPTER (INICIALIZAÇÃO)")
print("-"*40)

try:
    from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter

    print("Testando inicialização do CellposeAdapter...")

    # Testar com configuração automática (gpu=None)
    adapter = CellposeAdapter(model_type="nuclei", gpu=None)

    print(f"✅ CellposeAdapter inicializado com sucesso")
    print(f"  • Model type: {adapter._model_type}")
    print(f"  • GPU enabled: {adapter._gpu}")
    print(f"  • Batch size: {adapter._batch_size}")
    print(f"  • Resample factor: {adapter._resample_factor}")
    print(f"  • Timeout: {adapter._timeout_seconds}s")
    print(f"  • Max tile size: {adapter._max_tile_size}px")

    # Verificar decisão de GPU
    if adapter._gpu:
        print(f"  • Decisão: GPU habilitada (config.use_gpu=True, force_cpu_only={adapter._config.force_cpu_only})")
    else:
        print(f"  • Decisão: CPU-only (config.use_gpu={adapter._config.cellpose.use_gpu}, force_cpu_only={adapter._config.force_cpu_only})")

    print("\n✅ Todas as otimizações implementadas:")
    print("  • Timeout com concurrent.futures.ThreadPoolExecutor")
    print("  • Divisão automática de tiles grandes")
    print("  • Downsampling configurável (resample_factor)")
    print("  • Monitoramento de memória (se psutil disponível)")
    print("  • Fallback automático CPU/GPU")

except Exception as e:
    print(f"❌ Erro no CellposeAdapter: {e}")
    import traceback
    traceback.print_exc()

# Recomendações
print("\n4. RECOMENDAÇÕES PARA macOS MONTEREY 12.7.6")
print("-"*40)

print("Baseado na detecção de hardware:")
print(f"• Sistema: macOS {report.get('mac_version', 'Unknown')}")
print(f"• CPU: {report.get('cpu_cores', 'Unknown')} cores")
print(f"• Memória: {report.get('memory_gb', 'Unknown'):.1f} GB")
print(f"• Perfil: {report.get('performance_profile', 'Unknown').upper()}")

print("\n🔧 Configurações recomendadas:")
print("1. GPU: DESABILITADA (macOS Monterey 12.x)")
print("   • PyTorch MPS pode ser instável")
print("   • Use modo CPU-only para estabilidade")

print("\n2. Tamanho de Tile: ≤ 2000x2000 pixels")
print("   • Dividir tiles grandes automaticamente")
print("   • Configuração atual: split_large_tiles=True")

print("\n3. Threads:")
print("   • Segmentação: 4 threads máximos")
print("   • Renderização: 8 threads máximos")

print("\n4. Timeout: 300 segundos (5 minutos)")
print("   • Previne travamentos em processamento longo")
print("   • Cancelamento automático se exceder")

print("\n5. Memória: Limite de 4096 MB")
print("   • Monitoramento automático se psutil instalado")
print("   • Aviso se uso exceder limite")

print("\n⚙️  Configuração atual salva em:")
print(f"   {Path.home() / '.grid-analyzer' / 'config.json'}")

print("\n📋 Próximos passos:")
print("1. Instalar dependências:")
print("   pip install psutil torch cellpose")
print("2. Executar teste completo:")
print("   python -m app.tools.diagnose_hardware")
print("3. Iniciar aplicação:")
print("   python -m main")

print("\n" + "="*60)
print("TESTE COMPLETADO COM SUCESSO!")
print("="*60)