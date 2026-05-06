#!/usr/bin/env python3
"""
Script Simples: Segmentar Imagem com Cellpose
==============================================
Carrega uma imagem TIF, segmenta com CellposeAdapter e salva resultados.

Uso:
    python segment_image_cellpose.py --image <path_to_tif> [--output-dir <dir>]
"""

import sys
from pathlib import Path
import numpy as np
import cv2
import matplotlib.pyplot as plt
from PIL import Image
from datetime import datetime
import argparse

# Importar CellposeAdapter
sys.path.insert(0, str(Path(__file__).parent))
from app.infrastructure.ml_models.cellpose_adapter import CellposeAdapter


def load_image_robust(file_path):
    """Carrega imagem TIF robustamente usando PIL (lida melhor com acentuação)"""
    print(f"\n📁 Carregando imagem: {file_path}")
    print(f"   Tamanho: {Path(file_path).stat().st_size / (1024**2):.1f} MB")
    
    try:
        # Usar PIL que lida melhor com caracteres especiais
        img_pil = Image.open(file_path)
        img = np.array(img_pil)
        
        if img.ndim == 2:
            # Grayscale -> RGB
            img = np.stack([img, img, img], axis=-1)
        elif img.ndim == 3:
            if img.shape[2] == 4:
                # RGBA -> RGB
                img = img[:, :, :3]
            elif img.shape[2] == 1:
                # Single channel -> RGB
                img = np.repeat(img, 3, axis=2)
        
        print(f"   Dimensões: {img.shape}")
        print(f"   Tipo: {img.dtype}")
        
        return img
    except Exception as e:
        raise ValueError(f"Erro ao carregar imagem: {e}")


def segment_with_cellpose(image_path):
    """Segmenta imagem com CellposeAdapter"""
    print("\n⚙️  Segmentando com CellposeAdapter...")
    print("   (Isso pode levar alguns minutos na primeira execução)")
    
    try:
        image = Image.open(image_path).convert('RGB')
        image_array = np.array(image)
        
        # Inicializar adapter
        adapter = CellposeAdapter()
        print("   ✓ Adapter inicializado")
        
        # Segmentar
        print("   ⏳ Executando Cellpose...")
        polygons = adapter.segment(image)
        
        print(f"   ✓ Segmentação concluída: {len(polygons)} núcleos detectados")
        
        # Converter polygons para máscara
        print("   📍 Convertendo contornos para máscara...")
        mask = np.zeros((image_array.shape[0], image_array.shape[1]), dtype=np.uint32)
        for nucleus_id, polygon in enumerate(polygons, start=1):
            pts = np.array(polygon, dtype=np.int32)
            cv2.fillPoly(mask, [pts], nucleus_id)
        
        print(f"   ✓ Máscara gerada: {mask.shape}")
        
        return mask, len(polygons), image_array
        
    except Exception as e:
        print(f"   ❌ Erro durante segmentação: {e}")
        import traceback
        traceback.print_exc()
        raise


def save_results(mask, image, image_path, output_dir):
    """Salva máscara e imagem com sobreposição"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Nome base
    stem = Path(image_path).stem
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Salvar máscara como NPY
    mask_npy = output_dir / f"{stem}_segmentation_{timestamp}.npy"
    np.save(mask_npy, {'masks': mask})
    print(f"\n💾 Máscara NPY salva: {mask_npy}")
    
    # Salvar máscara como PNG (visualização com colormap)
    try:
        mask_png = output_dir / f"{stem}_segmentation_{timestamp}.png"
        # Usar COLORMAP_JET que sempre existe
        mask_colored = cv2.applyColorMap((mask.astype(np.uint8) % 255), cv2.COLORMAP_JET)
        cv2.imwrite(str(mask_png), mask_colored)
        print(f"💾 Máscara PNG salva: {mask_png}")
    except Exception as e:
        print(f"⚠️  Aviso ao salvar PNG de máscara: {e}")
    
    # Salvar sobreposição
    try:
        overlay_path = output_dir / f"{stem}_overlay_{timestamp}.png"
        overlay = image.copy().astype(np.float32)
        mask_binary = (mask > 0).astype(np.float32)
        overlay[:,:,0] = overlay[:,:,0] * (1 - mask_binary * 0.3) + mask_binary * 255 * 0.7
        
        cv2.imwrite(str(overlay_path), cv2.cvtColor(overlay.astype(np.uint8), cv2.COLOR_RGB2BGR))
        print(f"💾 Overlay PNG salva: {overlay_path}")
    except Exception as e:
        print(f"⚠️  Aviso ao salvar overlay: {e}")
        overlay_path = None
    
    return mask_npy, mask_png if 'mask_png' in locals() else None, overlay_path


def visualize_segmentation(image, mask, num_nuclei):
    """Exibe visualização lado-a-lado"""
    print("\n📊 Gerando visualização...")
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    
    # Imagem original
    axes[0].imshow(image)
    axes[0].set_title("1️⃣ Imagem Original", fontsize=13, fontweight='bold')
    axes[0].axis('off')
    
    # Máscara colorida
    cmap = plt.cm.get_cmap('tab20')
    mask_colored = cmap(mask.astype(float) / (mask.max() + 1))
    axes[1].imshow(mask_colored)
    axes[1].set_title(f"2️⃣ Máscara Cellpose ({num_nuclei} objetos)", 
                      fontsize=13, fontweight='bold')
    axes[1].axis('off')
    
    # Sobreposição (contornos)
    image_contours = image.copy()
    contours, _ = cv2.findContours(
        (mask > 0).astype(np.uint8), 
        cv2.RETR_EXTERNAL, 
        cv2.CHAIN_APPROX_SIMPLE
    )
    cv2.drawContours(image_contours, contours, -1, (255, 0, 0), 2)
    
    axes[2].imshow(image_contours)
    axes[2].set_title(f"3️⃣ Contornos Sobrepostos", fontsize=13, fontweight='bold')
    axes[2].axis('off')
    
    plt.tight_layout()
    plt.show()
    
    return fig


def print_statistics(mask, num_nuclei):
    """Imprime estatísticas"""
    print("\n" + "="*70)
    print("📊 ESTATÍSTICAS DE SEGMENTAÇÃO".center(70))
    print("="*70)
    
    print(f"\n🔢 Detecção:")
    print(f"   Total de objetos:           {num_nuclei}")
    print(f"   Dimensões da máscara:       {mask.shape}")
    print(f"   Tipo de dados:              {mask.dtype}")
    
    unique_ids = np.unique(mask)
    print(f"\n📐 Medidas:")
    print(f"   IDs únicos na máscara:      {len(unique_ids)}")
    print(f"   Pixels da background:       {(mask == 0).sum():,}")
    print(f"   Pixels segmentados:         {(mask > 0).sum():,}")
    print(f"   Percentual de cobertura:    {100*(mask > 0).sum() / mask.size:.2f}%")
    
    # Tamanho dos núcleos
    sizes = [np.sum(mask == nuc_id) for nuc_id in unique_ids[1:]]
    if sizes:
        print(f"\n📏 Tamanho dos núcleos:")
        print(f"   Mínimo:                     {min(sizes):,} pixels")
        print(f"   Máximo:                     {max(sizes):,} pixels")
        print(f"   Média:                      {np.mean(sizes):,.0f} pixels")
        print(f"   Mediana:                    {np.median(sizes):,.0f} pixels")
    
    print("\n" + "="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='Caminho para imagem TIF')
    parser.add_argument('--output-dir', default='./cellpose_segmentations', 
                        help='Diretório para salvar resultados')
    parser.add_argument('--no-visualize', action='store_true', help='Não gerar visualização')
    
    args = parser.parse_args()
    image_path = Path(args.image)
    output_dir = Path(args.output_dir)
    
    # Validar
    if not image_path.exists():
        print(f"❌ Erro: Imagem não encontrada: {image_path}")
        sys.exit(1)
    
    try:
        print("\n" + "="*70)
        print("🔬 SEGMENTAÇÃO CELLPOSE".center(70))
        print("="*70)
        
        # Carregar
        image = load_image_robust(image_path)
        
        # Segmentar
        mask, num_nuclei, image_array = segment_with_cellpose(image_path)
        
        # Salvar
        mask_npy, mask_png, overlay_path = save_results(mask, image, image_path, output_dir)
        
        # Estatísticas
        print_statistics(mask, num_nuclei)
        
        # Visualizar
        if not args.no_visualize:
            fig = visualize_segmentation(image, mask, num_nuclei)
            png_output = output_dir / f"{image_path.stem}_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            fig.savefig(png_output, dpi=150, bbox_inches='tight')
            print(f"📸 Visualização salva: {png_output}")
        
        print("✅ Segmentação concluída com sucesso!")
        print(f"\n💡 Para comparar com outra segmentação:")
        print(f"   python compare_cellpose_segmentations.py \\")
        print(f"     --image '{image_path}' \\")
        print(f"     --mask '{mask_npy}' \\")
        print(f"     --visualize")
        
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
