#!/usr/bin/env python3
"""
GPU Monitoring durante Cellpose Segmentation.

Monitora em tempo real:
- GPU Memory (VRAM usado)
- GPU Utilization (%)
- Temperatura
- CPU Usage
- Tempo de inferência
"""

import subprocess
import json
import time
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class GPUMonitor:
    """Monitor GPU em tempo real usando nvidia-smi."""
    
    def __init__(self):
        self.samples = []
        self.start_time = None
        
    def get_gpu_stats(self) -> Dict[str, Any]:
        """Coleta stats da GPU via nvidia-smi."""
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=index,name,memory.used,memory.total,utilization.gpu,utilization.memory,temperature.gpu',
                 '--format=csv,nounits,noheader'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            lines = result.stdout.strip().split('\n')
            gpus = []
            
            for line in lines:
                if not line.strip():
                    continue
                    
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 7:
                    gpu_data = {
                        'index': parts[0],
                        'name': parts[1],
                        'memory_used': float(parts[2]),
                        'memory_total': float(parts[3]),
                        'utilization_gpu': float(parts[4]),
                        'utilization_memory': float(parts[5]),
                        'temperature': float(parts[6]),
                    }
                    gpus.append(gpu_data)
            
            return {'gpus': gpus, 'timestamp': time.time()}
            
        except Exception as e:
            logger.error(f"Failed to read GPU stats: {e}")
            return {}
    
    def get_cpu_stats(self) -> Dict[str, Any]:
        """Coleta CPU usage."""
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_gb': memory.used / (1024**3),
                'memory_total_gb': memory.total / (1024**3),
            }
        except:
            return {}
    
    def start_monitoring(self) -> None:
        """Inicia monitoramento."""
        self.start_time = time.time()
        logger.info("=" * 80)
        logger.info("GPU MONITORING START")
        logger.info("=" * 80)
        logger.info("\n📊 LIVE STATS (Ctrl+C para sair):\n")
        
        try:
            while True:
                elapsed = time.time() - self.start_time
                stats = self.get_gpu_stats()
                cpu_stats = self.get_cpu_stats()
                
                self.samples.append({
                    'elapsed': elapsed,
                    'gpu': stats,
                    'cpu': cpu_stats,
                })
                
                # Limpar console e imprimir stats
                print(f"\n⏱️ Tempo decorrido: {int(elapsed)}s\n")
                
                if stats.get('gpus'):
                    for gpu in stats['gpus']:
                        gpu_idx = gpu.get('index', 'N/A')
                        gpu_name = gpu.get('name', 'Unknown')
                        mem_used = gpu.get('memory_used', 0)
                        mem_total = gpu.get('memory_total', 0)
                        gpu_util = gpu.get('utilization_gpu', 0)
                        mem_util = gpu.get('utilization_memory', 0)
                        temp = gpu.get('temperature', 0)
                        
                        print(f"GPU {gpu_idx}: {gpu_name}")
                        print(f"  💾 Memory:  {mem_used:>6.0f}MB / {mem_total:>6.0f}MB ({mem_util:>5.1f}%)")
                        print(f"  🔧 Util:    {gpu_util:>5.1f}%")
                        print(f"  🌡️  Temp:     {temp:>5.1f}°C\n")
                
                if cpu_stats:
                    print(f"CPU:  {cpu_stats.get('cpu_percent', 0):>5.1f}%")
                    print(f"RAM:  {cpu_stats.get('memory_used_gb', 0):>5.1f}GB / {cpu_stats.get('memory_total_gb', 0):.1f}GB ({cpu_stats.get('memory_percent', 0):>5.1f}%)\n")
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.print_summary()
    
    def print_summary(self) -> None:
        """Imprime resumo do monitoramento."""
        if not self.samples:
            return
        
        total_time = self.samples[-1]['elapsed']
        
        logger.info("\n" + "=" * 80)
        logger.info("RESUMO DO MONITORAMENTO")
        logger.info("=" * 80)
        logger.info(f"\n⏱️ Tempo total: {int(total_time)}s\n")
        
        # Calcular médias de GPU
        if self.samples and self.samples[0]['gpu'].get('gpus'):
            for gpu_idx in range(len(self.samples[0]['gpu']['gpus'])):
                gpu_utils = [s['gpu']['gpus'][gpu_idx]['utilization_gpu'] 
                            for s in self.samples if len(s['gpu'].get('gpus', [])) > gpu_idx]
                gpu_mems = [s['gpu']['gpus'][gpu_idx]['memory_used'] 
                           for s in self.samples if len(s['gpu'].get('gpus', [])) > gpu_idx]
                
                if gpu_utils:
                    avg_util = sum(gpu_utils) / len(gpu_utils)
                    max_util = max(gpu_utils)
                    avg_mem = sum(gpu_mems) / len(gpu_mems)
                    max_mem = max(gpu_mems)
                    
                    print(f"GPU {gpu_idx}:")
                    print(f"  GPU Util:   {avg_util:>5.1f}% (avg) / {max_util:>5.1f}% (max)")
                    print(f"  Memory:     {avg_mem:>6.0f}MB (avg) / {max_mem:>6.0f}MB (max)\n")
        
        # Calcular médias de CPU
        if self.samples:
            cpu_utils = [s['cpu'].get('cpu_percent', 0) for s in self.samples if s['cpu']]
            if cpu_utils:
                avg_cpu = sum(cpu_utils) / len(cpu_utils)
                max_cpu = max(cpu_utils)
                
                print(f"CPU:")
                print(f"  Util:       {avg_cpu:>5.1f}% (avg) / {max_cpu:>5.1f}% (max)\n")
        
        # Recomendações
        if self.samples and self.samples[0]['gpu'].get('gpus'):
            gpu = self.samples[0]['gpu']['gpus'][0]
            gpu_utils = [s['gpu']['gpus'][0]['utilization_gpu'] 
                        for s in self.samples if len(s['gpu'].get('gpus', [])) > 0]
            
            if gpu_utils:
                avg_util = sum(gpu_utils) / len(gpu_utils)
                
                print("💡 RECOMENDAÇÕES:\n")
                if avg_util < 30:
                    print("  ❌ GPU subutilizada (<30%)")
                    print("     - Aumentar batch_size (atualmente 16)")
                    print("     - Aumentar max_tile_size (atualmente 3000px)")
                    print("     - Verificar se preprocessing está no CPU")
                elif avg_util < 70:
                    print("  🟡 GPU parcialmente utilizada (<70%)")
                    print("     - Considere aumentar batch_size para 24-32")
                elif avg_util < 90:
                    print("  🟢 GPU bem utilizada (70-90%)")
                    print("     - Otimização bem-sucedida!")
                else:
                    print("  🟢 GPU maximizada (>90%)")
                    print("     - Utilização excelente!")
        
        print("\n" + "=" * 80 + "\n")


def main():
    """Inicia monitoramento de GPU."""
    monitor = GPUMonitor()
    monitor.start_monitoring()


if __name__ == "__main__":
    main()
